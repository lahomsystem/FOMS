"""dedicated 채널 수신 주문 worker (CHANNEL-INBOUND-ORDER-01, SIDEFX-WORKER-01 패턴).

ACCEPTED receipt 를 ``FOR UPDATE SKIP LOCKED`` 로 claim 해 canonical ``create_order`` 로
정본 생성한다. mechanics 는 SIDEFX-WORKER-01 과 동형이되 대상 테이블이
``channel_inbound_event_logs`` 이고 side-effect 가 아니라 **주문 생성**이라는 점만 다르다.

핵심 불변식:

* **global flag 우회 0**: 매 배치·매 receipt 마다 :func:`create_flag.is_create_enabled` 로
  전역 flag 를 확인한다. DISABLED 면 새 주문을 만들지 않는다.
* **max attempts → RECOVERY_REQUIRED**: ``create_attempts`` 는 claim 시점에 durable 하게
  증가한다(크래시가 시도로 계수). 소진되면 무한 재시도 대신 RECOVERY_REQUIRED + retention
  deadline 을 걸어 운영자 recovery 로 넘긴다.
* **exact conservation**: :func:`create_order_from_receipt` 가 ``created_order_id`` 로 멱등이라
  receipt 1개 = 주문 1개(중복 0). key rotation·크래시(lease 만료 재claim) 후에도 1회 생성.
* **owner absence pause**: SALES owner 를 해석할 수 없으면 receipt 를 PAUSED_ACCEPTED 로 보존.
* **two commit 0**: receipt CREATED 전이와 order 생성이 같은 tx 에서 commit.

``lease_expires_at`` 은 (a) 처리 중 lease, (b) 실패 backoff 재시도 gate 를 겸한다.
ponytail: lease_expires_at 이 next-attempt gate 를 겸함 — 별도 available_at 컬럼을 만들지 않음.
"""
from __future__ import annotations

import datetime
import logging
from typing import Any, Callable, Optional

from sqlalchemy import func, or_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from foms.services.security.channel_order import create_flag
from foms.services.security.channel_order.creation import (
    ChannelOwnerAbsenceError,
    ChannelReceiptParseError,
    create_order_from_receipt,
    resolve_channel_owner,
)
from foms.services.datetime_kst import now_utc_naive
from foms.services.sidefx_worker import backoff_seconds, make_engine_from_env  # 재사용
from models import ChannelInboundEventLog, ChannelInboundWorkerHeartbeat

_LOGGER = logging.getLogger("channel_order_worker")

WORKER_KIND = "CHANNEL_CREATE"
DEFAULT_LEASE_SECONDS = 60
DEFAULT_MAX_ATTEMPTS = 10
DEFAULT_BATCH_SIZE = 100
DEFAULT_BACKOFF_BASE_SECONDS = 5
DEFAULT_BACKOFF_CAP_SECONDS = 3600
DEFAULT_RETENTION_DAYS = 30


def _claimable_filter(now: datetime.datetime):
    """claim 가능 조건: ACCEPTED 이고 lease/backoff gate 가 지났다."""
    return (
        ChannelInboundEventLog.receipt_state == "ACCEPTED",
        or_(
            ChannelInboundEventLog.lease_expires_at.is_(None),
            ChannelInboundEventLog.lease_expires_at <= now,
        ),
    )


def claim_batch(
    session: Session, *,
    owner_hash: str,
    lease_token: str,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    batch_size: int = DEFAULT_BATCH_SIZE,
    now: Optional[datetime.datetime] = None,
) -> "list[ChannelInboundEventLog]":
    """ACCEPTED receipt 를 ``FOR UPDATE SKIP LOCKED`` 로 claim 한다(create_attempts++·lease).

    commit 은 호출자 소유 — 두 worker 세션이 commit 전까지 lock 을 잡아 SKIP LOCKED 가 서로
    다른 receipt 를 보장한다(중복 처리 0). attempts 는 claim 시점에 증가해 크래시도 시도로 센다.
    """
    now = now or now_utc_naive()
    rows = (
        session.query(ChannelInboundEventLog)
        .filter(*_claimable_filter(now))
        .order_by(ChannelInboundEventLog.received_at.asc())
        .limit(batch_size)
        .with_for_update(skip_locked=True)
        .all()
    )
    expires_at = now + datetime.timedelta(seconds=lease_seconds)
    for row in rows:
        row.lease_owner_hash = owner_hash
        row.lease_token = lease_token
        row.lease_expires_at = expires_at
        row.create_attempts = (row.create_attempts or 0) + 1
    return rows


def _pause_owner_absence(receipt: ChannelInboundEventLog, now: datetime.datetime) -> None:
    """owner 부재 → PAUSED_ACCEPTED 로 보존(유실 0, 재개 가능). lease 해제."""
    receipt.receipt_state = "PAUSED_ACCEPTED"
    receipt.lease_owner_hash = None
    receipt.lease_token = None
    receipt.lease_expires_at = None


def _to_recovery_required(
    receipt: ChannelInboundEventLog, now: datetime.datetime, retention_days: int
) -> None:
    """attempts 소진 → RECOVERY_REQUIRED + retention deadline(무한 재시도 0)."""
    receipt.receipt_state = "RECOVERY_REQUIRED"
    if receipt.retention_deadline is None:
        receipt.retention_deadline = now + datetime.timedelta(days=retention_days)
    receipt.lease_owner_hash = None
    receipt.lease_token = None
    receipt.lease_expires_at = None


def _backoff_retry(
    receipt: ChannelInboundEventLog, now: datetime.datetime, base: int, cap: int
) -> None:
    """attempts 미소진 → backoff 후 재claim(lease_expires_at 을 next-attempt gate 로)."""
    receipt.lease_owner_hash = None
    receipt.lease_token = None
    receipt.lease_expires_at = now + datetime.timedelta(
        seconds=backoff_seconds(receipt.create_attempts or 0, base=base, cap=cap)
    )


def _process_one(
    session: Session,
    receipt_id: int,
    *,
    max_attempts: int,
    retention_days: int,
    backoff_base: int,
    backoff_cap: int,
    now_fn: Callable[[], datetime.datetime],
) -> str:
    """claim 된 receipt 하나를 create_order 로 처리한다(호출자가 commit). 결과 문자열 반환.

    반환: ``created`` / ``paused`` / ``recovery_required`` / ``retried`` / ``skipped``.
    """
    now = now_fn()
    receipt = (
        session.query(ChannelInboundEventLog)
        .filter(ChannelInboundEventLog.id == receipt_id)
        .with_for_update()
        .one_or_none()
    )
    if receipt is None or receipt.receipt_state != "ACCEPTED":
        return "skipped"  # 다른 op(pause/recovery)이 선점
    if not create_flag.is_create_enabled(session):
        _pause_owner_absence(receipt, now)  # flag off → 보존(재enable 시 ACCEPTED 복귀)
        return "skipped"
    try:
        owner = resolve_channel_owner(session)
    except ChannelOwnerAbsenceError:
        _pause_owner_absence(receipt, now)
        return "paused"
    try:
        create_order_from_receipt(session, receipt, owner_user_id=owner, now=now)
        return "created"
    except ChannelReceiptParseError as exc:
        _LOGGER.warning("[channel] receipt %s create failed: %r", receipt_id, exc)
        if (receipt.create_attempts or 0) >= max_attempts:
            _to_recovery_required(receipt, now, retention_days)
            return "recovery_required"
        _backoff_retry(receipt, now, backoff_base, backoff_cap)
        return "retried"


def run_create_once(
    engine: Engine, *,
    owner_hash: str,
    lease_token_fn: Callable[[], str],
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    batch_size: int = DEFAULT_BATCH_SIZE,
    retention_days: int = DEFAULT_RETENTION_DAYS,
    backoff_base: int = DEFAULT_BACKOFF_BASE_SECONDS,
    backoff_cap: int = DEFAULT_BACKOFF_CAP_SECONDS,
    now_fn: Callable[[], datetime.datetime] = now_utc_naive,
) -> "dict[str, int]":
    """한 배치를 claim(즉시 commit)한 뒤 receipt 별로 create_order 를 개별 commit 한다.

    전역 flag 가 DISABLED 면 claim 자체를 하지 않는다(global flag 우회 0). claim 을 먼저 commit 해
    lease 를 durable 하게 만들고 lock 을 해제한 뒤 각 receipt 를 처리한다.

    Returns:
        ``{"claimed","created","paused","recovery_required","retried","skipped"}`` 카운트.
    """
    session_local = sessionmaker(bind=engine)
    result = {"claimed": 0, "created": 0, "paused": 0,
              "recovery_required": 0, "retried": 0, "skipped": 0}

    s = session_local()
    try:
        if not create_flag.is_create_enabled(s):
            return result  # disabled → 아무것도 claim 하지 않음(우회 0)
        claimed = claim_batch(
            s, owner_hash=owner_hash, lease_token=lease_token_fn(),
            lease_seconds=lease_seconds, batch_size=batch_size, now=now_fn(),
        )
        claimed_ids = [r.id for r in claimed]
        result["claimed"] = len(claimed_ids)
        s.commit()
    finally:
        s.close()

    for receipt_id in claimed_ids:
        s = session_local()
        try:
            outcome = _process_one(
                s, receipt_id, max_attempts=max_attempts, retention_days=retention_days,
                backoff_base=backoff_base, backoff_cap=backoff_cap, now_fn=now_fn,
            )
            result[outcome] += 1
            s.commit()
        except Exception:  # 예기치 못한 오류는 rollback(claim 의 attempt++ 는 유지) 후 로그
            s.rollback()
            _LOGGER.exception("[channel] receipt %s processing crashed", receipt_id)
        finally:
            s.close()
    return result


# --------------------------------------------------------------------------- #
# heartbeat + readiness
# --------------------------------------------------------------------------- #
def upsert_heartbeat(
    engine: Engine, *,
    oldest_lag_seconds: Optional[int] = None,
    metadata: Optional[dict] = None,
    now: Optional[datetime.datetime] = None,
) -> None:
    """CHANNEL_CREATE heartbeat 를 upsert 한다(PK worker_kind, ON CONFLICT DO UPDATE)."""
    now = now or now_utc_naive()
    table = ChannelInboundWorkerHeartbeat.__table__
    stmt = pg_insert(table).values(
        worker_kind=WORKER_KIND, last_heartbeat_at=now,
        oldest_lag_seconds=oldest_lag_seconds, metadata_json=metadata, updated_at=now,
    ).on_conflict_do_update(
        index_elements=["worker_kind"],
        set_=dict(last_heartbeat_at=now, oldest_lag_seconds=oldest_lag_seconds,
                  metadata_json=metadata, updated_at=now),
    )
    session_local = sessionmaker(bind=engine)
    s = session_local()
    try:
        s.execute(stmt)
        s.commit()
    finally:
        s.close()


def oldest_accepted_lag_seconds(
    session: Session, *, now: Optional[datetime.datetime] = None
) -> Optional[int]:
    """지금 claim 가능한 가장 오래된 ACCEPTED receipt 의 지연 초(없으면 None)."""
    now = now or now_utc_naive()
    oldest = (
        session.query(func.min(ChannelInboundEventLog.received_at))
        .filter(*_claimable_filter(now))
        .scalar()
    )
    if oldest is None:
        return None
    return max(0, int((now - oldest).total_seconds()))


def recovery_required_count(session: Session) -> int:
    """현재 RECOVERY_REQUIRED receipt 수(readiness 는 임계 초과면 fail-closed)."""
    return int(
        session.query(func.count(ChannelInboundEventLog.id))
        .filter(ChannelInboundEventLog.receipt_state == "RECOVERY_REQUIRED")
        .scalar()
        or 0
    )


def evaluate_readiness(
    session: Session, *,
    max_heartbeat_age: int = 30,
    max_oldest_lag: int = 300,
    max_recovery_required: int = 0,
    now: Optional[datetime.datetime] = None,
) -> "dict[str, Any]":
    """heartbeat 신선도·oldest lag·RECOVERY_REQUIRED count 로 fail-closed readiness 판정.

    Returns:
        ``{"ready": bool, "failures": [...], "observations": {...}}``.
    """
    now = now or now_utc_naive()
    hb = session.get(ChannelInboundWorkerHeartbeat, WORKER_KIND)
    lag = oldest_accepted_lag_seconds(session, now=now)
    stuck = recovery_required_count(session)
    failures: "list[dict]" = []
    if hb is None:
        failures.append({"check": "heartbeat_present", "detail": "no heartbeat row"})
    else:
        age = max(0, int((now - hb.last_heartbeat_at).total_seconds()))
        if age >= max_heartbeat_age:
            failures.append({"check": "heartbeat_fresh", "detail": age, "limit": max_heartbeat_age})
    if lag is not None and lag >= max_oldest_lag:
        failures.append({"check": "oldest_lag", "detail": lag, "limit": max_oldest_lag})
    if stuck > max_recovery_required:
        failures.append({"check": "recovery_required", "detail": stuck,
                         "limit": max_recovery_required})
    return {"ready": not failures, "failures": failures,
            "observations": {"lag": lag, "recovery_required": stuck}}
