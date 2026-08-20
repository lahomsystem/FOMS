"""ERP 공통첨부(AS) 암시적 결합 앵커 (AS-BIND-01).

빈 ``as_log_id`` 업로드는 현재 회차 접수 줄에 붙인다. 접수가 없으면 주차 메모
(``as_upload_park``)를 만들고, 이후 ``as/register`` 가 그 파일을 접수 줄로 옮긴다.
방안/통화 줄에는 붙이지 않는다.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text

from foms.services.attachment_sort import attachment_sort_key, next_attachment_sort_order
from foms.services.datetime_kst import now_utc_naive
from foms.services.orders.as_log import append_client_log, current_as_round

logger = logging.getLogger(__name__)

AS_UPLOAD_PARK_FLAG = "as_upload_park"
AS_UPLOAD_PARK_TEXT = "첨부 파일"

__all__ = [
    "AS_UPLOAD_PARK_FLAG",
    "AS_UPLOAD_PARK_TEXT",
    "append_as_upload_park",
    "lock_as_upload_anchor",
    "peek_as_upload_anchor",
    "promote_parked_as_attachments",
]


def _entry_round(entry: dict) -> int:
    """항목 소속 회차. round 없는 구항목은 1회차."""
    raw = entry.get("round")
    return raw if isinstance(raw, int) and raw >= 1 else 1


def _live_entries(sd: Any) -> list[dict]:
    """삭제되지 않은 as_log 항목."""
    entries = ((sd or {}).get("shipment") or {}).get("as_log")
    if not isinstance(entries, list):
        return []
    return [
        entry for entry in entries
        if isinstance(entry, dict) and entry.get("deleted") is not True
    ]


def _entry_id(entry: dict) -> str:
    """항목 id 문자열. 없으면 빈 문자열."""
    return str(entry.get("id") or "")


def peek_as_upload_anchor(sd: Any) -> str | None:
    """현재 회차 접수, 없으면 주차 메모 id. 없으면 None.

    전역 첫 접수가 아니라 **현재 회차** reception 만 본다. 2회차 사진을 1회차
    접수 칸에 섞지 않기 위함이다.

    Args:
        sd: 주문 structured_data.

    Returns:
        결합할 ``as_log_id`` 또는 None.
    """
    current = current_as_round(sd or {})
    reception_id = None
    park_id = None
    for entry in _live_entries(sd):
        if _entry_round(entry) != current:
            continue
        eid = _entry_id(entry)
        if not eid:
            continue
        if entry.get("type") == "reception":
            reception_id = eid
        elif entry.get(AS_UPLOAD_PARK_FLAG) is True:
            park_id = eid
    return reception_id or park_id


def append_as_upload_park(sd: dict, user: Any) -> str:
    """현재 회차에 주차 메모를 append 하고 id 를 돌려준다.

    호출자가 이미 빈 앵커를 확인한 뒤에만 쓴다. sd 를 in-place 로 바꾼다.

    Args:
        sd: mutate 대상 structured_data.
        user: 업로드 직원(name/id). 없으면 빈 표기.

    Returns:
        새 주차 메모 id.
    """
    entry = append_client_log(
        sd,
        log_type="memo",
        text=AS_UPLOAD_PARK_TEXT,
        by=(getattr(user, "name", None) or ""),
        by_id=getattr(user, "id", None),
    )
    entry[AS_UPLOAD_PARK_FLAG] = True
    return str(entry["id"])


def lock_as_upload_anchor(db: Any, order_id: int) -> None:
    """PostgreSQL 에서 주문 단위 xact 락. SQLite 테스트는 no-op.

    Args:
        db: SQLAlchemy 세션.
        order_id: 주문 PK.
    """
    try:
        bind = db.get_bind()
        dialect_name = getattr(getattr(bind, "dialect", None), "name", "")
        if dialect_name != "postgresql":
            return
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
            {"k": f"as-upload-anchor:{int(order_id)}"},
        )
    except Exception:
        logger.warning("as-upload-anchor lock failed (order_id=%s)", order_id, exc_info=True)


def _park_ids_for_round(sd: Any, round_no: int) -> list[str]:
    """그 회차의 살아 있는 주차 메모 id 목록."""
    found: list[str] = []
    for entry in _live_entries(sd):
        if _entry_round(entry) != round_no:
            continue
        if entry.get(AS_UPLOAD_PARK_FLAG) is not True:
            continue
        eid = _entry_id(entry)
        if eid:
            found.append(eid)
    return found


def _soft_delete_park_memos(sd: Any, park_ids: list[str], deleted_by: str) -> None:
    """주차 메모를 as_log 소프트 삭제로 감춘다(빈 줄이 차트에 남지 않게)."""
    wanted = set(park_ids)
    now = now_utc_naive().isoformat()
    entries = ((sd or {}).get("shipment") or {}).get("as_log")
    if not isinstance(entries, list):
        return
    for entry in entries:
        if not isinstance(entry, dict) or _entry_id(entry) not in wanted:
            continue
        entry["deleted"] = True
        entry["deleted_at"] = now
        entry["deleted_by"] = deleted_by


def promote_parked_as_attachments(
    db: Any,
    order: Any,
    sd: dict,
    reception_log_id: str,
    *,
    deleted_by: str,
) -> int:
    """현재 회차 주차 첨부를 접수 줄로 옮기고 주차 메모를 소프트 삭제한다.

    레거시 ``as_log_id IS NULL`` 은 건드리지 않는다. reception_log_id 가 비면 no-op.

    Args:
        db: 세션.
        order: 주문 ORM.
        sd: register 가 mutate 중인 structured_data.
        reception_log_id: 방금 확보한 접수 항목 id.
        deleted_by: 주차 메모 삭제 표기.

    Returns:
        옮긴 첨부 수.
    """
    target = str(reception_log_id or "").strip()
    if not target:
        return 0
    round_no = None
    for entry in _live_entries(sd):
        if _entry_id(entry) == target:
            round_no = _entry_round(entry)
            break
    if round_no is None:
        return 0
    park_ids = _park_ids_for_round(sd, round_no)
    if not park_ids:
        return 0

    from models import OrderAttachment

    rows = (
        db.query(OrderAttachment)
        .filter(
            OrderAttachment.order_id == order.id,
            OrderAttachment.category == "as",
            OrderAttachment.as_log_id.in_(park_ids),
        )
        .all()
    )
    rows.sort(key=attachment_sort_key)
    next_sort = next_attachment_sort_order(db, order.id, target)
    for index, attachment in enumerate(rows):
        attachment.as_log_id = target
        attachment.sort_order = next_sort + index
    _soft_delete_park_memos(sd, park_ids, deleted_by)
    return len(rows)
