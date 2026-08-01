"""receipt recovery/retention/create-state 전이 (CHANNEL-INBOUND-ORDER-01).

3 개 receipt OPS-APPROVAL operation 의 상태 전이(승인 토큰 소비는 consume_same_db 가 담당):

* ``CHANNEL_RECOVERY_CREATE``  — RECOVERY_REQUIRED receipt 를 승인 후 create_order 로 생성(1회·멱등).
* ``CHANNEL_RECOVERY_IGNORE``  — RECOVERY_REQUIRED receipt 를 IGNORED 로(legal hold 면 거부).
* ``CHANNEL_RETENTION_EXTEND`` — retention deadline 을 **명시·유계** 미래로 연장(무기한 금지).

그리고 worker/cron 이 쓰는 비OPS 스캔:

* :func:`scan_retention_expired` — deadline 경과·미생성·비 legal_hold receipt 를 RETENTION_EXPIRED
  visible incident 로(조용한 삭제 아님). legal_hold 는 승인된 보존이므로 만료 제외.
* :func:`retention_alerts` — deadline 7d/24h/6h 전 경고 후보(중복 알림 방지 stage 기록).

**accepted silent clear/DEAD 금지**: 어떤 전이도 ACCEPTED receipt 를 조용히 없애지 않는다.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from sqlalchemy.orm import Session

from foms.services.security.channel_order.creation import (
    ChannelOwnerAbsenceError,
    create_order_from_receipt,
    resolve_channel_owner,
)
from foms.services.datetime_kst import now_utc_naive
from models import ChannelInboundEventLog

PACKET_ID = "CHANNEL-INBOUND-ORDER-01"

ALERT_WINDOWS_SECONDS = (("7d", 7 * 86400), ("24h", 86400), ("6h", 6 * 3600))
_ALERT_ORDER = {"7d": 1, "24h": 2, "6h": 3}


class ChannelReceiptOpError(RuntimeError):
    """receipt 전이 전 조건/legal hold/무기한 retention 위반(호출자는 mutation 0)."""


def build_scope(
    operation_id: str, phase: str, artifact_sha256: str, receipt_id: int,
) -> "dict[str, Any]":
    """OPS-APPROVAL scope object(exact fields). target 은 대상 receipt id 로 바인딩."""
    return {
        "schema_version": 1,
        "operation_id": operation_id,
        "packet_id": PACKET_ID,
        "target_ids_or_family": [int(receipt_id)],
        "phase": phase,
        "artifact_sha256": artifact_sha256,
        "expected_version": 0,
        "expected_generation": 0,
    }


def _load_receipt_for_update(session: Session, receipt_id: int) -> ChannelInboundEventLog:
    row = (
        session.query(ChannelInboundEventLog)
        .filter(ChannelInboundEventLog.id == receipt_id)
        .with_for_update()
        .one_or_none()
    )
    if row is None:
        raise ChannelReceiptOpError(f"receipt {receipt_id} not found.")
    return row


def _canonical(operation_id: str, receipt: ChannelInboundEventLog, extra: dict) -> bytes:
    return json.dumps(
        {"operation": operation_id, "receipt_id": receipt.id,
         "receipt_state": receipt.receipt_state, **extra},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")


def recovery_create(
    session: Session, *,
    receipt_id: int,
    owner_user_id: int,
    actor_user_id: Optional[int] = None,
    now: Optional[Any] = None,
) -> bytes:
    """RECOVERY_REQUIRED receipt 를 승인 후 create_order 로 생성한다(1회·멱등).

    :raises ChannelReceiptOpError: receipt 가 RECOVERY_REQUIRED 아님.
    :raises ChannelOwnerAbsenceError: owner 가 활성 SALES 아님.
    """
    now = now or now_utc_naive()
    receipt = _load_receipt_for_update(session, receipt_id)
    if receipt.receipt_state not in ("RECOVERY_REQUIRED",):
        raise ChannelReceiptOpError(
            f"recovery create requires RECOVERY_REQUIRED (got {receipt.receipt_state})."
        )
    owner = resolve_channel_owner(session, explicit_owner_user_id=owner_user_id)
    order = create_order_from_receipt(
        session, receipt, owner_user_id=owner, actor_user_id=actor_user_id, now=now
    )
    return _canonical("CHANNEL_RECOVERY_CREATE", receipt, {"order_id": order.id})


def recovery_ignore(
    session: Session, *,
    receipt_id: int,
    actor_user_id: Optional[int] = None,
    now: Optional[Any] = None,
) -> bytes:
    """RECOVERY_REQUIRED receipt 를 IGNORED 로 전이한다(legal hold 면 거부).

    :raises ChannelReceiptOpError: 상태 불일치 또는 legal_hold(조용한 clear 금지).
    """
    now = now or now_utc_naive()
    receipt = _load_receipt_for_update(session, receipt_id)
    if receipt.receipt_state not in ("RECOVERY_REQUIRED",):
        raise ChannelReceiptOpError(
            f"recovery ignore requires RECOVERY_REQUIRED (got {receipt.receipt_state})."
        )
    if receipt.legal_hold:
        raise ChannelReceiptOpError("receipt is under legal hold; ignore is forbidden.")
    receipt.receipt_state = "IGNORED"
    receipt.status = "ignored_recovery"
    receipt.processed_at = now
    session.flush()
    return _canonical("CHANNEL_RECOVERY_IGNORE", receipt, {})


def retention_extend(
    session: Session, *,
    receipt_id: int,
    new_deadline: Any,
    actor_user_id: Optional[int] = None,
    now: Optional[Any] = None,
) -> bytes:
    """retention deadline 을 명시·유계 미래로 연장한다(무기한 보관 금지).

    :raises ChannelReceiptOpError: new_deadline 이 없거나(무기한) 과거.
    """
    now = now or now_utc_naive()
    if new_deadline is None:
        raise ChannelReceiptOpError("retention extend requires a bounded deadline (indefinite 0).")
    if new_deadline <= now:
        raise ChannelReceiptOpError("retention deadline must be in the future.")
    receipt = _load_receipt_for_update(session, receipt_id)
    receipt.retention_deadline = new_deadline
    receipt.retention_alert_stage = None  # 새 window → 경고 재개.
    if receipt.receipt_state == "RETENTION_EXPIRED":
        receipt.receipt_state = "RECOVERY_REQUIRED"  # 재연장 → 다시 처리 가능.
    session.flush()
    return _canonical("CHANNEL_RETENTION_EXTEND", receipt, {"deadline": str(new_deadline)})


def place_legal_hold(
    session: Session, *, receipt_id: int, hold: bool, now: Optional[Any] = None
) -> None:
    """receipt 에 legal hold 를 걸거나 해제한다(hold 중엔 ignore/expire 금지)."""
    receipt = _load_receipt_for_update(session, receipt_id)
    receipt.legal_hold = bool(hold)
    session.flush()


def scan_retention_expired(
    session: Session, *, now: Optional[Any] = None, limit: int = 1000
) -> int:
    """deadline 경과·미생성·비 legal_hold receipt 를 RETENTION_EXPIRED(visible incident)로.

    CREATED/IGNORED/이미 RETENTION_EXPIRED 는 제외. legal_hold 는 승인된 보존이라 만료하지
    않는다. 조용한 삭제가 아니라 상태 전이(가시 incident)만 한다. 호출자가 commit.

    :returns: 이번 스캔에서 만료 처리한 receipt 수.
    """
    now = now or now_utc_naive()
    rows = (
        session.query(ChannelInboundEventLog)
        .filter(
            ChannelInboundEventLog.retention_deadline.isnot(None),
            ChannelInboundEventLog.retention_deadline <= now,
            ChannelInboundEventLog.legal_hold.is_(False),
            ChannelInboundEventLog.receipt_state.notin_(
                ("CREATED", "IGNORED", "RETENTION_EXPIRED")
            ),
        )
        .order_by(ChannelInboundEventLog.id.asc())
        .limit(limit)
        .all()
    )
    for receipt in rows:
        receipt.receipt_state = "RETENTION_EXPIRED"
        receipt.processed_at = now
    session.flush()
    return len(rows)


def _due_alert_stage(seconds_left: float, sent: Optional[str]) -> Optional[str]:
    """남은 시간에 해당하는 가장 임박한 미발송 경고 stage(없으면 None)."""
    sent_rank = _ALERT_ORDER.get(sent or "", 0)
    due = None
    for stage, window in ALERT_WINDOWS_SECONDS:
        if seconds_left <= window and _ALERT_ORDER[stage] > sent_rank:
            due = stage  # 더 임박한 stage 로 계속 갱신(6h 가 최우선).
    return due


def retention_alerts(
    session: Session, *, now: Optional[Any] = None, limit: int = 1000
) -> "list[dict]":
    """deadline 7d/24h/6h 전 경고 후보를 산출하고 발송 stage 를 기록한다(중복 알림 방지).

    :returns: ``[{"receipt_id", "stage", "deadline"}]`` — 실제 전송은 상류 알림 채널 몫.
    """
    now = now or now_utc_naive()
    rows = (
        session.query(ChannelInboundEventLog)
        .filter(
            ChannelInboundEventLog.retention_deadline.isnot(None),
            ChannelInboundEventLog.legal_hold.is_(False),
            ChannelInboundEventLog.receipt_state.notin_(
                ("CREATED", "IGNORED", "RETENTION_EXPIRED")
            ),
        )
        .order_by(ChannelInboundEventLog.retention_deadline.asc())
        .limit(limit)
        .all()
    )
    out: "list[dict]" = []
    for receipt in rows:
        seconds_left = (receipt.retention_deadline - now).total_seconds()
        stage = _due_alert_stage(seconds_left, receipt.retention_alert_stage)
        if stage is None:
            continue
        receipt.retention_alert_stage = stage
        out.append({"receipt_id": receipt.id, "stage": stage,
                    "deadline": str(receipt.retention_deadline)})
    session.flush()
    return out
