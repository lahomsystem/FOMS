"""전역 채널 주문 생성 flag + cutoff pause/resume (CHANNEL-INBOUND-ORDER-01).

``CHANNEL_CREATE_ENABLE`` / ``CHANNEL_CREATE_DISABLE`` 두 OPS operation 의 상태 전이를
제공한다. 기본 DISABLED(명시 승인 전 자동 생성 0). worker 는 매 배치마다
:func:`is_create_enabled` 로 이 flag 를 읽어 DISABLED 면 새 주문을 만들지 않는다(**global flag
우회 worker 0**).

disable(cutoff)는 ACCEPTED receipt 를 조용히 버리지 않고 **PAUSED_ACCEPTED** 로 보존한다
(job PAUSED·유실 0). enable 은 PAUSED_ACCEPTED 를 ACCEPTED 로 되살린다. 전이는 approval 토큰
소비(consume_same_db)와 한 tx 로 묶여 mutation 이 승인 없이 일어나지 않는다.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from sqlalchemy.orm import Session

from foms.services.datetime_kst import now_utc_naive
from models import ChannelCreateFlag, ChannelInboundEventLog

PACKET_ID = "CHANNEL-INBOUND-ORDER-01"
SCOPE_TARGET = "CHANNEL_CREATE_FLAG"


class ChannelCreateFlagError(RuntimeError):
    """flag 전이 전 조건/mode/version 위반(호출자는 mutation 0 으로 처리)."""


def build_scope(
    operation_id: str, phase: str, artifact_sha256: str, expected_version: int,
) -> "dict[str, Any]":
    """OPS-APPROVAL scope object(exact fields). flag 는 generation 개념이 없어 0 고정."""
    return {
        "schema_version": 1,
        "operation_id": operation_id,
        "packet_id": PACKET_ID,
        "target_ids_or_family": SCOPE_TARGET,
        "phase": phase,
        "artifact_sha256": artifact_sha256,
        "expected_version": expected_version,
        "expected_generation": 0,
    }


def load_flag_for_update(session: Session) -> ChannelCreateFlag:
    """create flag singleton(id=1)을 ``FOR UPDATE`` 로 잠가 반환."""
    row = (
        session.query(ChannelCreateFlag)
        .filter(ChannelCreateFlag.id == 1)
        .with_for_update()
        .one_or_none()
    )
    if row is None:
        raise ChannelCreateFlagError("channel_create_flag singleton (id=1) is missing (unseeded).")
    return row


def read_flag(session: Session) -> ChannelCreateFlag:
    """flag singleton 을 잠금 없이 읽는다(expected_version 확인용)."""
    row = session.query(ChannelCreateFlag).filter(ChannelCreateFlag.id == 1).one_or_none()
    if row is None:
        raise ChannelCreateFlagError("channel_create_flag singleton (id=1) is missing (unseeded).")
    return row


def is_create_enabled(session: Session) -> bool:
    """worker gate: 전역 flag 가 ENABLED 인가(우회 금지 — worker 가 매 배치 확인)."""
    return read_flag(session).state == "ENABLED"


def _canonical(operation_id: str, row: ChannelCreateFlag, paused_or_resumed: int) -> bytes:
    """approval result_sha256 용 canonical 결과 bytes."""
    return json.dumps(
        {
            "operation": operation_id,
            "state": row.state,
            "version": row.version,
            "affected_receipts": paused_or_resumed,
        },
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")


def enable(
    session: Session, *,
    expected_version: int,
    updated_by_admin_user_id: Optional[int],
    now: Optional[Any] = None,
) -> bytes:
    """DISABLED→ENABLED. PAUSED_ACCEPTED receipt 를 ACCEPTED 로 되살린다(resume)."""
    now = now or now_utc_naive()
    row = load_flag_for_update(session)
    if row.version != expected_version:
        raise ChannelCreateFlagError(
            f"flag version {row.version} != expected {expected_version} (concurrent change)."
        )
    if row.state != "DISABLED":
        raise ChannelCreateFlagError(f"enable requires state DISABLED (got {row.state}).")

    resumed = (
        session.query(ChannelInboundEventLog)
        .filter(ChannelInboundEventLog.receipt_state == "PAUSED_ACCEPTED")
        .update({ChannelInboundEventLog.receipt_state: "ACCEPTED"}, synchronize_session=False)
    )
    row.state = "ENABLED"
    row.version = (row.version or 1) + 1
    row.updated_at = now
    row.updated_by_admin_user_id = updated_by_admin_user_id
    session.flush()
    return _canonical("CHANNEL_CREATE_ENABLE", row, int(resumed or 0))


def disable(
    session: Session, *,
    expected_version: int,
    updated_by_admin_user_id: Optional[int],
    now: Optional[Any] = None,
) -> bytes:
    """ENABLED→DISABLED(cutoff). ACCEPTED receipt 를 PAUSED_ACCEPTED 로 보존한다(유실 0)."""
    now = now or now_utc_naive()
    row = load_flag_for_update(session)
    if row.version != expected_version:
        raise ChannelCreateFlagError(
            f"flag version {row.version} != expected {expected_version} (concurrent change)."
        )
    if row.state != "ENABLED":
        raise ChannelCreateFlagError(f"disable requires state ENABLED (got {row.state}).")

    paused = (
        session.query(ChannelInboundEventLog)
        .filter(ChannelInboundEventLog.receipt_state == "ACCEPTED")
        .update({ChannelInboundEventLog.receipt_state: "PAUSED_ACCEPTED"}, synchronize_session=False)
    )
    row.state = "DISABLED"
    row.version = (row.version or 1) + 1
    row.updated_at = now
    row.updated_by_admin_user_id = updated_by_admin_user_id
    session.flush()
    return _canonical("CHANNEL_CREATE_DISABLE", row, int(paused or 0))
