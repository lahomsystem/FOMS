"""OrderDraft persistence for mobile new-order wizard (P1-03)."""

from __future__ import annotations

import copy
import datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models import OrderDraft

_DRAFT_V1_REQUIRED = frozenset({"schema_version", "step", "data"})
_NEW_DRAFT_TTL_DAYS = 7
_EDIT_DRAFT_TTL_HOURS = 24


class OrderDraftConflictError(Exception):
    """Raised when X-If-Match does not match the stored draft."""

    def __init__(self, current: dict[str, Any]) -> None:
        super().__init__("CONFLICT")
        self.current = current


def format_updated_at(value: datetime.datetime | None) -> str:
    """Serialize updated_at for API responses and If-Match headers."""
    if value is None:
        return ""
    return value.strftime("%Y-%m-%d %H:%M:%S")


def parse_updated_at(value: str | None) -> datetime.datetime | None:
    """Parse If-Match header value back to datetime."""
    if not value or not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def _expires_at_for_key(draft_key: str, now: datetime.datetime | None = None) -> datetime.datetime:
    """Return TTL expiry for new.* (7d) vs edit.* (24h) draft keys."""
    base = now or datetime.datetime.now()
    if draft_key.startswith("edit."):
        return base + datetime.timedelta(hours=_EDIT_DRAFT_TTL_HOURS)
    return base + datetime.timedelta(days=_NEW_DRAFT_TTL_DAYS)


def validate_draft_payload(payload: Any) -> dict[str, Any]:
    """Minimal draft_v1 shape check (full JSON Schema deferred to client)."""
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    missing = _DRAFT_V1_REQUIRED - set(payload.keys())
    if missing:
        raise ValueError(f"missing keys: {', '.join(sorted(missing))}")
    step = payload.get("step")
    if not isinstance(step, int) or step < 1 or step > 4:
        raise ValueError("step must be integer 1..4")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("data must be an object")
    return copy.deepcopy(payload)


def get_draft(db: Session, user_id: int, draft_key: str) -> OrderDraft | None:
    """Load a draft owned by user_id or None."""
    if not draft_key or not draft_key.strip():
        return None
    return (
        db.query(OrderDraft)
        .filter(
            OrderDraft.user_id == user_id,
            OrderDraft.draft_key == draft_key.strip(),
        )
        .one_or_none()
    )


def draft_to_api_dict(row: OrderDraft) -> dict[str, Any]:
    """Serialize OrderDraft row for GET responses."""
    return {
        "draft_key": row.draft_key,
        "step": row.step,
        "payload": row.payload if isinstance(row.payload, dict) else {},
        "schema_version": row.schema_version,
        "updated_at": format_updated_at(row.updated_at),
        "order_id": row.order_id,
    }


def _is_user_key_unique_violation(exc: IntegrityError) -> bool:
    """True when flush hit uq_order_drafts_user_key (PG name or SQLite columns)."""
    raw = str(getattr(exc, "orig", None) or exc).lower()
    if "uq_order_drafts_user_key" in raw:
        return True
    return "unique" in raw and "draft_key" in raw


def _apply_draft_fields(
    row: OrderDraft,
    *,
    step: int,
    validated: dict[str, Any],
    now: datetime.datetime,
    draft_key: str,
    order_id: int | None,
) -> None:
    """Write upsert fields onto an existing OrderDraft row."""
    row.step = step
    row.payload = validated
    row.schema_version = int(validated.get("schema_version") or 1)
    row.updated_at = now
    row.expires_at = _expires_at_for_key(draft_key, now)
    if order_id is not None:
        row.order_id = order_id


def _insert_or_recover_draft(
    db: Session,
    *,
    user_id: int,
    key: str,
    step: int,
    validated: dict[str, Any],
    now: datetime.datetime,
    order_id: int | None,
) -> OrderDraft:
    """INSERT a draft; on (user_id, draft_key) race, UPDATE the winner row."""
    row = OrderDraft(
        user_id=user_id,
        order_id=order_id,
        draft_key=key,
        step=step,
        payload=validated,
        schema_version=int(validated.get("schema_version") or 1),
        expires_at=_expires_at_for_key(key, now),
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError as exc:
        if not _is_user_key_unique_violation(exc):
            raise
        if row in db:
            db.expunge(row)
        raced = get_draft(db, user_id, key)
        if raced is None:
            raise
        _apply_draft_fields(
            raced,
            step=step,
            validated=validated,
            now=now,
            draft_key=key,
            order_id=order_id,
        )
        db.flush()
        return raced
    return row


def upsert_draft(
    db: Session,
    *,
    user_id: int,
    draft_key: str,
    step: int,
    payload: dict[str, Any],
    if_match: str | None = None,
    order_id: int | None = None,
) -> OrderDraft:
    """Create or update draft with optional optimistic concurrency (If-Match).

    Concurrent first-saves of the same key (iOS keepalive overlap, two web
    workers) can miss the SELECT and both INSERT. UniqueViolation is absorbed
    as an UPDATE of the winner row — last write wins, same as a later autosave.
    """
    key = draft_key.strip()
    if not key:
        raise ValueError("draft_key required")

    validated = validate_draft_payload(payload)
    validated["step"] = step
    now = datetime.datetime.now()

    existing = get_draft(db, user_id, key)
    if existing is not None:
        expected = parse_updated_at(if_match)
        if if_match and expected is not None and existing.updated_at:
            stored = existing.updated_at.replace(microsecond=0)
            if stored != expected.replace(microsecond=0):
                raise OrderDraftConflictError(draft_to_api_dict(existing))
        _apply_draft_fields(
            existing,
            step=step,
            validated=validated,
            now=now,
            draft_key=key,
            order_id=order_id,
        )
        db.flush()
        return existing

    return _insert_or_recover_draft(
        db,
        user_id=user_id,
        key=key,
        step=step,
        validated=validated,
        now=now,
        order_id=order_id,
    )


def delete_draft(db: Session, user_id: int, draft_key: str) -> bool:
    """Delete draft for user. Returns True when a row was removed."""
    row = get_draft(db, user_id, draft_key)
    if row is None:
        return False
    db.delete(row)
    db.flush()
    return True
