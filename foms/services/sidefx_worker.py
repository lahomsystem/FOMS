"""domain side-effect outbox worker mechanics + handler registry (SIDEFX-WORKER-01).

SIDEFX-00 이 만든 ``domain_side_effect_outbox`` / ``side_effect_worker_heartbeats``
스키마를 소비하는 **consumer mechanics** 다. 실제 side effect I/O(notification 전송,
cache invalidate, geocode, storage delete 등)는 각 도메인 handler(하류 CHANNEL-WRITER-01·
URGENT-CALL-01·NOTIFICATION 몫)가 수행한다 — 이 모듈은 그 handler 를 ``effect_type`` 으로
찾아 호출하는 registry 와, claim/lease/retry/DEAD/heartbeat/reclaim/retention 같은
**오케스트레이션 기계장치**만 소유한다. 스키마·마이그레이션은 건드리지 않는다.

세 개의 loop kind 로 나뉜다(``side_effect_worker_heartbeats.worker_kind`` 정본):

* ``DELIVERY`` — ``FOR UPDATE SKIP LOCKED`` 로 PENDING(available_at<=now) 행을 claim →
  PROCESSING+lease → registry dispatch → 성공 DONE / 실패 attempts++·backoff·max attempts DEAD.
* ``EXPIRY_SCAN`` — 만료 lease(죽은 worker)를 회수(PROCESSING lease_expires_at<now → PENDING
  backoff, 단 attempts 소진이면 DEAD). advisory lock 으로 replica 간 직렬화.
* ``RETENTION`` — :func:`foms.services.sidefx_outbox.purge_retention` 를 반복 호출(DONE 30d /
  DEAD 180d). advisory lock 으로 직렬화.

registry 는 하류 handler 가 채운다 — 이 packet 은 인터페이스만 제공하고 실 handler 를
등록하지 않는다(등록 0 이면 dispatch 가 :class:`NoHandlerError` → 재시도/DEAD 로 fail-closed).
"""
from __future__ import annotations

import datetime
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Sequence

from sqlalchemy import create_engine, func, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from foms.services.datetime_kst import now_utc_naive
from foms.services.sidefx_outbox import purge_retention
from models import DomainSideEffectOutbox, SideEffectWorkerHeartbeat

_LOGGER = logging.getLogger("sidefx_worker")

# worker_kind 정본(heartbeat PK 값). readiness gate 가 이 세 kind 를 요구한다.
WORKER_KIND_DELIVERY = "DELIVERY"
WORKER_KIND_EXPIRY_SCAN = "EXPIRY_SCAN"
WORKER_KIND_RETENTION = "RETENTION"
WORKER_KINDS = (WORKER_KIND_DELIVERY, WORKER_KIND_EXPIRY_SCAN, WORKER_KIND_RETENTION)

# outbox worker 밖에서 같은 표에 하트비트를 쓰는 loop kind 들(OPS-HEARTBEAT-01).
# 이 표에 없으면 판정 대상이 될 수 없다 — 하트비트를 쓰기만 하고 아무도 안 읽는 상태가
# 정확히 그렇게 생겼다(2026-09-07 F-9).
WORKER_KIND_NAVER_AUTO_DISPATCH = "NAVER_AUTO_DISPATCH"
WORKER_KIND_GEOCODE_SWEEP = "GEOCODE_SWEEP"
WORKER_KIND_NOTIFICATION_ESCALATION = "NOTIFICATION_ESCALATION"
WORKER_KIND_NAVER_ORDER_SYNC = "NAVER_ORDER_SYNC"
WORKER_KIND_NAVER_SETTLE_SYNC = "NAVER_SETTLE_SYNC"
WORKER_KIND_RQ_WORKER = "RQ_WORKER"


@dataclass(frozen=True)
class WorkerKindSpec:
    """loop kind 하나의 readiness 판정 규약.

    Attributes:
        kind: ``side_effect_worker_heartbeats.worker_kind`` 값.
        max_heartbeat_age: 하트비트 신선도 예산(초). 이 이상 묵으면 not-ready.
        scan_lag_limit: ``oldest_lag_seconds`` 한도(초). ``None`` 이면 그 검사를 안 한다
            (scan 루프가 아닌 kind — 하트비트 신선도만 본다).
        outbox_scoped: outbox 표(PENDING lag·DEAD)를 함께 판정해야 하는 kind 인지.
    """

    kind: str
    max_heartbeat_age: int
    scan_lag_limit: Optional[int] = None
    outbox_scoped: bool = False


# kind 등록부. outbox 3종의 임계는 CLI flag 가 정본이라 여기 값은 그 기본값과 같게 둔다
# (:class:`ReadinessThresholds` 가 kind 별로 다시 풀어 준다). 나머지 loop 는 자기 tick 을
# 근거로 예산을 갖는다 — 두 루프 다 tick 60초라 3틱(180초)을 죽음의 기준으로 삼는다.
WORKER_KIND_SPECS: dict[str, "WorkerKindSpec"] = {
    WORKER_KIND_DELIVERY: WorkerKindSpec(
        WORKER_KIND_DELIVERY, max_heartbeat_age=30, outbox_scoped=True),
    WORKER_KIND_EXPIRY_SCAN: WorkerKindSpec(
        WORKER_KIND_EXPIRY_SCAN, max_heartbeat_age=30, scan_lag_limit=360, outbox_scoped=True),
    WORKER_KIND_RETENTION: WorkerKindSpec(
        WORKER_KIND_RETENTION, max_heartbeat_age=30, scan_lag_limit=90000, outbox_scoped=True),
    WORKER_KIND_NAVER_AUTO_DISPATCH: WorkerKindSpec(
        WORKER_KIND_NAVER_AUTO_DISPATCH, max_heartbeat_age=180),
    WORKER_KIND_GEOCODE_SWEEP: WorkerKindSpec(
        WORKER_KIND_GEOCODE_SWEEP, max_heartbeat_age=180),
    WORKER_KIND_NOTIFICATION_ESCALATION: WorkerKindSpec(
        WORKER_KIND_NOTIFICATION_ESCALATION, max_heartbeat_age=180),
    # 수집 루프는 기본 간격이 300초(네이버 HTTP 쿼터 때문에 더 못 줄인다) → 3틱.
    WORKER_KIND_NAVER_ORDER_SYNC: WorkerKindSpec(
        WORKER_KIND_NAVER_ORDER_SYNC, max_heartbeat_age=900),
    WORKER_KIND_NAVER_SETTLE_SYNC: WorkerKindSpec(
        WORKER_KIND_NAVER_SETTLE_SYNC, max_heartbeat_age=180),
    # rq worker 는 놀 때 dequeue 블로킹이 405초(worker_ttl 420 - 15)라 그 주기로만
    # 하트비트를 남긴다. 2주기 + 여유 = 900초.
    WORKER_KIND_RQ_WORKER: WorkerKindSpec(
        WORKER_KIND_RQ_WORKER, max_heartbeat_age=900),
}

DEFAULT_LEASE_SECONDS = 60
DEFAULT_MAX_ATTEMPTS = 10
DEFAULT_BATCH_SIZE = 100
DEFAULT_BACKOFF_BASE_SECONDS = 5
DEFAULT_BACKOFF_CAP_SECONDS = 3600
HEARTBEAT_INTERVAL_SECONDS = 10

# advisory lock 키(문자열 → hashtext). purge tool 의 관용을 재사용해 replica 간 scan 을 직렬화.
_EXPIRY_LOCK_KEY = "foms:sidefx_expiry_scan"
_RETENTION_LOCK_KEY = "foms:sidefx_retention_scan"


def make_engine_from_env() -> Engine:
    """``DATABASE_URL``(없으면 ``FOMS_TEST_DATABASE_URL``)로 bare 엔진을 만든다.

    Flask app 을 import 하지 않는다 — 전체 app 초기화(gevent patch, auto-init/migrate)는
    Railway heartbeat timeout 의 원인이므로 worker/readiness CLI 는 직접 엔진을 만든다
    (``tools/ops/purge_order_mutation_receipts.py`` 와 동일 규율).

    Raises:
        RuntimeError: 두 env 모두 미설정.
    """
    url = os.environ.get("DATABASE_URL") or os.environ.get("FOMS_TEST_DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL (or FOMS_TEST_DATABASE_URL) is not set")
    if url.startswith("postgres://"):  # Railway 표기 → SQLAlchemy 표기
        url = "postgresql://" + url[len("postgres://"):]
    engine_kwargs: dict = {"pool_pre_ping": True}
    if "sqlite" not in url:
        engine_kwargs["connect_args"] = {"connect_timeout": 10}
    return create_engine(url, **engine_kwargs)


# --------------------------------------------------------------------------- #
# handler registry (인터페이스만 — 실 handler 는 하류 도메인 packet 몫)
# --------------------------------------------------------------------------- #
# handler 는 outbox 행 하나를 받아 실제 side effect 를 수행한다. 성공하면 정상 반환,
# 실패하면 예외를 raise 한다(worker 가 예외를 attempts++/backoff/DEAD 로 처리). idempotency
# 는 handler 가 ``row.provider_idempotency_key`` 로 보장한다(중복 배달 방지).
Handler = Callable[[DomainSideEffectOutbox], None]

_HANDLERS: dict[str, Handler] = {}


class NoHandlerError(LookupError):
    """``effect_type`` 에 등록된 handler 가 없다(배포 누락 — 재시도 후 DEAD 로 fail-closed)."""


def register_handler(effect_type: str, handler: Handler, *, replace: bool = False) -> None:
    """도메인 handler 를 ``effect_type`` 으로 registry 에 등록한다(하류 packet 호출).

    Args:
        effect_type: outbox 행의 effect_type(예: NOTIFICATION/STORAGE_DELETE/GEOCODE).
        handler: 행 1개를 받아 side effect 를 수행하고 실패 시 예외를 raise 하는 callable.
        replace: True 면 기존 등록을 덮어쓴다. 기본 False 는 중복 등록을 거부(오배선 방지).

    Raises:
        ValueError: effect_type 이 비었거나, replace 없이 이미 등록된 effect_type 재등록.
    """
    if not effect_type:
        raise ValueError("effect_type must be a non-empty string")
    if not replace and effect_type in _HANDLERS:
        raise ValueError(f"handler for {effect_type!r} already registered")
    _HANDLERS[effect_type] = handler


def get_handler(effect_type: str) -> Optional[Handler]:
    """등록된 handler 를 반환한다(없으면 None)."""
    return _HANDLERS.get(effect_type)


def clear_handlers() -> None:
    """registry 를 비운다(테스트 격리용)."""
    _HANDLERS.clear()


def dispatch(row: DomainSideEffectOutbox) -> None:
    """행의 effect_type 에 맞는 handler 를 찾아 호출한다.

    Raises:
        NoHandlerError: 등록된 handler 가 없다(재시도/DEAD 로 fail-closed).
        Exception: handler 가 raise 한 실패는 그대로 전파(worker 가 재시도 처리).
    """
    handler = _HANDLERS.get(row.effect_type)
    if handler is None:
        raise NoHandlerError(f"no handler registered for effect_type {row.effect_type!r}")
    handler(row)


# --------------------------------------------------------------------------- #
# expiry-scan provider registry (인터페이스만 — 실 provider 는 도메인 packet 몫)
# --------------------------------------------------------------------------- #
# EXPIRY_SCAN loop 은 outbox lease reclaim 뒤 등록된 도메인 bounded-scan provider 를
# 호출한다(예: UPLOAD-02 upload_cleanup 이 만료 ticket/draft 를 EXPIRED 로 claim 하고
# STORAGE_DELETE outbox 를 만든다). provider 는 engine 을 받아 자기 advisory lock/세션/
# commit 을 소유하는 bounded scan 을 1회 수행하고 카운트 dict 를 돌려준다. 이 registry 로
# worker mechanics 를 도메인 로직과 분리한다(별도 scheduler/loop 를 만들지 않기 위함).
ExpiryScanProvider = Callable[[Engine], dict]

_EXPIRY_SCAN_PROVIDERS: dict[str, ExpiryScanProvider] = {}


def register_expiry_scan_provider(
    name: str, provider: ExpiryScanProvider, *, replace: bool = False
) -> None:
    """도메인 bounded-scan provider 를 300s expiry scan 에 등록한다(하류 packet 호출).

    Args:
        name: provider 식별자(결과 dict 키·중복 등록 판정).
        provider: engine 을 받아 bounded scan 1회를 수행하고 카운트 dict 를 반환하는 callable.
        replace: True 면 기존 등록을 덮어쓴다. 기본 False 는 중복 등록 거부(오배선 방지).

    Raises:
        ValueError: name 이 비었거나, replace 없이 이미 등록된 name 재등록.
    """
    if not name:
        raise ValueError("provider name must be a non-empty string")
    if not replace and name in _EXPIRY_SCAN_PROVIDERS:
        raise ValueError(f"expiry-scan provider {name!r} already registered")
    _EXPIRY_SCAN_PROVIDERS[name] = provider


def clear_expiry_scan_providers() -> None:
    """expiry-scan provider registry 를 비운다(테스트 격리용)."""
    _EXPIRY_SCAN_PROVIDERS.clear()


# --------------------------------------------------------------------------- #
# claim / finalize (delivery core — caller 가 commit 소유)
# --------------------------------------------------------------------------- #
def backoff_seconds(
    attempts: int,
    *,
    base: int = DEFAULT_BACKOFF_BASE_SECONDS,
    cap: int = DEFAULT_BACKOFF_CAP_SECONDS,
) -> int:
    """attempts 회 실패 뒤 재시도까지의 지수 backoff 초(cap 상한).

    attempts 1 → base, 2 → base*2, 3 → base*4 … cap 에서 포화. attempts<=0 은 base.
    """
    if attempts <= 1:
        return base
    return min(base * (2 ** (attempts - 1)), cap)


def claim_batch(
    session: Session,
    *,
    owner_hash: str,
    lease_token: str,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    batch_size: int = DEFAULT_BATCH_SIZE,
    now: Optional[datetime.datetime] = None,
) -> list[DomainSideEffectOutbox]:
    """PENDING(available_at<=now) 행을 ``FOR UPDATE SKIP LOCKED`` 로 claim 한다.

    claim 된 행을 PROCESSING 으로 전이하고 lease(owner/token/expires_at)를 걸며 attempts 를
    1 증가시킨다(크래시가 시도로 계수되도록 claim 시점 증가). **commit 은 caller 소유** —
    두 worker 세션이 commit 전까지 lock 을 잡고 있으므로 SKIP LOCKED 가 서로 다른 행을
    보장한다(중복 처리 0).

    Args:
        session: worker 세션(caller 가 commit/rollback 소유).
        owner_hash: 이 worker 인스턴스 식별 해시(String(64)).
        lease_token: 이 claim 배치의 lease token(uuid str).
        lease_seconds: lease 유효기간(초). 만료 시 expiry scan 이 회수.
        batch_size: 한 번에 claim 할 최대 행 수.
        now: 기준 시각(기본 now_utc_naive()).

    Returns:
        claim 되어 PROCESSING 으로 전이된 행 리스트(빈 리스트 가능).
    """
    now = now or now_utc_naive()
    rows = (
        session.query(DomainSideEffectOutbox)
        .filter(
            DomainSideEffectOutbox.status == "PENDING",
            DomainSideEffectOutbox.available_at <= now,
        )
        .order_by(DomainSideEffectOutbox.available_at.asc())
        .limit(batch_size)
        .with_for_update(skip_locked=True)
        .all()
    )
    expires_at = now + datetime.timedelta(seconds=lease_seconds)
    for row in rows:
        row.status = "PROCESSING"
        row.lease_owner_hash = owner_hash
        row.lease_token = lease_token
        row.lease_expires_at = expires_at
        row.attempts = (row.attempts or 0) + 1
    return rows


def finalize_success(
    session: Session,
    row: DomainSideEffectOutbox,
    *,
    now: Optional[datetime.datetime] = None,
) -> None:
    """handler 성공 → DONE 전이(lease 해제, completed_at 기록). caller 가 commit."""
    now = now or now_utc_naive()
    row.status = "DONE"
    row.completed_at = now
    row.last_error = None
    row.lease_owner_hash = None
    row.lease_token = None
    row.lease_expires_at = None


def finalize_failure(
    session: Session,
    row: DomainSideEffectOutbox,
    *,
    error: str,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    backoff_base: int = DEFAULT_BACKOFF_BASE_SECONDS,
    backoff_cap: int = DEFAULT_BACKOFF_CAP_SECONDS,
    now: Optional[datetime.datetime] = None,
) -> str:
    """handler 실패 → attempts 소진이면 DEAD, 아니면 backoff 후 PENDING 재시도.

    attempts 는 claim 시점에 이미 증가했으므로 여기서는 그 값으로 판정만 한다.

    Returns:
        전이한 최종 상태 문자열("DEAD" 또는 "PENDING").
    """
    now = now or now_utc_naive()
    row.last_error = (error or "")[:2000]
    row.lease_owner_hash = None
    row.lease_token = None
    row.lease_expires_at = None
    if (row.attempts or 0) >= max_attempts:
        row.status = "DEAD"
        row.dead_at = now
        return "DEAD"
    row.status = "PENDING"
    row.available_at = now + datetime.timedelta(
        seconds=backoff_seconds(row.attempts or 0, base=backoff_base, cap=backoff_cap)
    )
    return "PENDING"


# --------------------------------------------------------------------------- #
# loop-once primitives (worker 가 반복 호출; 각자 session 소유·commit)
# --------------------------------------------------------------------------- #
def run_delivery_once(
    engine: Engine,
    *,
    owner_hash: str,
    lease_token_fn: Callable[[], str],
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    batch_size: int = DEFAULT_BATCH_SIZE,
    backoff_base: int = DEFAULT_BACKOFF_BASE_SECONDS,
    backoff_cap: int = DEFAULT_BACKOFF_CAP_SECONDS,
    dispatch_fn: Callable[[DomainSideEffectOutbox], None] = dispatch,
    now_fn: Callable[[], datetime.datetime] = now_utc_naive,
) -> dict[str, int]:
    """한 배치를 claim(즉시 commit)한 뒤 행별로 dispatch 하고 결과를 개별 commit 한다.

    claim 을 먼저 commit 해 lease 를 durable 하게 만들고 lock 을 해제한다(handler I/O 를
    lock 밖에서 수행). handler 성공은 DONE, 실패/NoHandler 는 backoff PENDING 또는 DEAD.

    Returns:
        ``{"claimed", "done", "retried", "dead"}`` 카운트.
    """
    session_local = sessionmaker(bind=engine)
    claimed_ids: list[int] = []
    s = session_local()
    try:
        claimed = claim_batch(
            s, owner_hash=owner_hash, lease_token=lease_token_fn(),
            lease_seconds=lease_seconds, batch_size=batch_size, now=now_fn(),
        )
        claimed_ids = [r.id for r in claimed]
        s.commit()
    finally:
        s.close()

    result = {"claimed": len(claimed_ids), "done": 0, "retried": 0, "dead": 0}
    for row_id in claimed_ids:
        s = session_local()
        try:
            row = s.get(DomainSideEffectOutbox, row_id)
            if row is None or row.status != "PROCESSING":
                continue
            try:
                dispatch_fn(row)
            except Exception as exc:  # handler 실패는 poison 이 아니라 재시도 대상(로그+durable last_error)
                _LOGGER.warning(
                    "[sidefx] delivery handler failed effect_type=%s id=%s: %r",
                    row.effect_type, row.id, exc,
                )
                outcome = finalize_failure(
                    s, row, error=repr(exc), max_attempts=max_attempts,
                    backoff_base=backoff_base, backoff_cap=backoff_cap, now=now_fn(),
                )
                result["dead" if outcome == "DEAD" else "retried"] += 1
            else:
                finalize_success(s, row, now=now_fn())
                result["done"] += 1
            s.commit()
        finally:
            s.close()
    return result


def reclaim_expired_once(
    engine: Engine,
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    batch_size: int = DEFAULT_BATCH_SIZE,
    backoff_base: int = DEFAULT_BACKOFF_BASE_SECONDS,
    backoff_cap: int = DEFAULT_BACKOFF_CAP_SECONDS,
    now_fn: Callable[[], datetime.datetime] = now_utc_naive,
) -> dict[str, int]:
    """만료 lease(죽은 worker)를 회수한다: PROCESSING lease_expires_at<now → PENDING/DEAD.

    advisory lock 으로 replica 간 scan 을 직렬화(못 잡으면 benign skip). 회수 행은 실패와
    동일 규칙(attempts 소진 DEAD, 아니면 backoff PENDING).

    Returns:
        ``{"reclaimed", "requeued", "dead", "skipped"}``.
    """
    session_local = sessionmaker(bind=engine)
    s = session_local()
    try:
        got = s.execute(
            text("SELECT pg_try_advisory_lock(hashtext(:k))"), {"k": _EXPIRY_LOCK_KEY}
        ).scalar()
        if not got:
            return {"reclaimed": 0, "requeued": 0, "dead": 0, "skipped": 1}
        try:
            now = now_fn()
            rows = (
                s.query(DomainSideEffectOutbox)
                .filter(
                    DomainSideEffectOutbox.status == "PROCESSING",
                    DomainSideEffectOutbox.lease_expires_at < now,
                )
                .order_by(DomainSideEffectOutbox.lease_expires_at.asc())
                .limit(batch_size)
                .with_for_update(skip_locked=True)
                .all()
            )
            result = {"reclaimed": len(rows), "requeued": 0, "dead": 0, "skipped": 0}
            for row in rows:
                outcome = finalize_failure(
                    s, row, error="lease expired (worker crash/timeout)",
                    max_attempts=max_attempts, backoff_base=backoff_base,
                    backoff_cap=backoff_cap, now=now,
                )
                result["dead" if outcome == "DEAD" else "requeued"] += 1
            s.commit()
            return result
        finally:
            s.execute(
                text("SELECT pg_advisory_unlock(hashtext(:k))"), {"k": _EXPIRY_LOCK_KEY}
            )
            s.commit()
    finally:
        s.close()


def run_expiry_scan_once(
    engine: Engine,
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    batch_size: int = DEFAULT_BATCH_SIZE,
    backoff_base: int = DEFAULT_BACKOFF_BASE_SECONDS,
    backoff_cap: int = DEFAULT_BACKOFF_CAP_SECONDS,
    now_fn: Callable[[], datetime.datetime] = now_utc_naive,
) -> dict:
    """EXPIRY_SCAN 1회: outbox lease reclaim + 등록된 도메인 bounded-scan provider dispatch.

    worker 의 300s expiry scan step 이 (구) ``reclaim_expired_once`` 대신 이 함수를 호출한다.
    먼저 만료 lease 를 회수한 뒤, 등록된 provider(예: UPLOAD-02 upload_cleanup)를 순서대로
    호출한다. **별도 scheduler/loop 를 만들지 않고** 기존 300s scan 에 provider 를 배선하는
    유일 지점이다. 한 provider 실패는 로그로 남기고 다음 provider·다음 주기로 넘긴다(한
    provider 오류가 lease reclaim 이나 다른 provider 를 막지 않음).

    Args:
        engine: 대상 DB 엔진.
        max_attempts: reclaim 시 attempts 소진 판정 상한.
        batch_size: reclaim 배치 크기.
        backoff_base: reclaim 재큐 backoff base(초).
        backoff_cap: reclaim 재큐 backoff cap(초).
        now_fn: 기준 시각 factory.

    Returns:
        ``{"reclaim": <reclaim_expired_once 결과>, "providers": {name: <provider 결과>}}``.
    """
    reclaim = reclaim_expired_once(
        engine, max_attempts=max_attempts, batch_size=batch_size,
        backoff_base=backoff_base, backoff_cap=backoff_cap, now_fn=now_fn,
    )
    providers: dict[str, Any] = {}
    for name, provider in list(_EXPIRY_SCAN_PROVIDERS.items()):
        try:
            providers[name] = provider(engine)
        except Exception as exc:  # provider 실패는 삼키지 않고 로그(다음 주기 재시도)
            _LOGGER.exception("[sidefx] expiry-scan provider %s failed", name)
            providers[name] = {"error": repr(exc)}
    return {"reclaim": reclaim, "providers": providers}


def run_retention_once(
    engine: Engine,
    *,
    limit: int = 1000,
    now_fn: Callable[[], datetime.datetime] = now_utc_naive,
) -> dict[str, int]:
    """retention 배치를 0 반환까지 반복해 terminal 행을 purge(DONE 30d / DEAD 180d).

    advisory lock 으로 직렬화(못 잡으면 skip). SIDEFX-00 ``purge_retention`` 을 재사용만 한다.

    Returns:
        ``{"done_purged", "dead_purged", "skipped"}``.
    """
    session_local = sessionmaker(bind=engine)
    s = session_local()
    try:
        got = s.execute(
            text("SELECT pg_try_advisory_lock(hashtext(:k))"), {"k": _RETENTION_LOCK_KEY}
        ).scalar()
        if not got:
            return {"done_purged": 0, "dead_purged": 0, "skipped": 1}
        try:
            total = {"done_purged": 0, "dead_purged": 0, "skipped": 0}
            while True:
                batch = purge_retention(s, now=now_fn(), limit=limit)
                s.commit()
                total["done_purged"] += batch["done_purged"]
                total["dead_purged"] += batch["dead_purged"]
                if batch["done_purged"] == 0 and batch["dead_purged"] == 0:
                    break
            return total
        finally:
            s.execute(
                text("SELECT pg_advisory_unlock(hashtext(:k))"), {"k": _RETENTION_LOCK_KEY}
            )
            s.commit()
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# heartbeat + readiness
# --------------------------------------------------------------------------- #
def upsert_heartbeat(
    engine: Engine,
    worker_kind: str,
    *,
    oldest_lag_seconds: Optional[int] = None,
    metadata: Optional[dict[str, Any]] = None,
    now: Optional[datetime.datetime] = None,
) -> None:
    """worker_kind heartbeat 를 upsert 한다(PK worker_kind, ON CONFLICT DO UPDATE)."""
    now = now or now_utc_naive()
    table = SideEffectWorkerHeartbeat.__table__
    values = dict(
        worker_kind=worker_kind, last_heartbeat_at=now,
        oldest_lag_seconds=oldest_lag_seconds, metadata_json=metadata, updated_at=now,
    )
    stmt = pg_insert(table).values(**values).on_conflict_do_update(
        index_elements=["worker_kind"],
        set_=dict(
            last_heartbeat_at=now, oldest_lag_seconds=oldest_lag_seconds,
            metadata_json=metadata, updated_at=now,
        ),
    )
    session_local = sessionmaker(bind=engine)
    s = session_local()
    try:
        s.execute(stmt)
        s.commit()
    finally:
        s.close()


def oldest_pending_lag_seconds(
    session: Session, *, now: Optional[datetime.datetime] = None
) -> Optional[int]:
    """지금 처리 가능한 가장 오래된 PENDING 행의 지연 초(없으면 None).

    available_at<=now 인 PENDING 만 센다(미래 예약 backoff 행은 lag 아님).
    """
    now = now or now_utc_naive()
    oldest = (
        session.query(func.min(DomainSideEffectOutbox.available_at))
        .filter(
            DomainSideEffectOutbox.status == "PENDING",
            DomainSideEffectOutbox.available_at <= now,
        )
        .scalar()
    )
    if oldest is None:
        return None
    return max(0, int((now - oldest).total_seconds()))


def dead_count(session: Session) -> int:
    """현재 DEAD 상태 행 수(readiness 는 이것이 임계 초과면 fail-closed)."""
    return int(
        session.query(func.count(DomainSideEffectOutbox.id))
        .filter(DomainSideEffectOutbox.status == "DEAD")
        .scalar()
        or 0
    )


@dataclass
class ReadinessThresholds:
    """readiness 판정 임계값(§8.2 check template 의 flag 와 1:1)."""

    max_heartbeat_age: Optional[int] = None
    max_oldest_pending_lag: int = 60
    max_expiry_scan_lag: int = 360
    max_retention_scan_lag: int = 90000
    max_dead: int = 0

    def heartbeat_age_limit(self, kind: str) -> int:
        """kind 의 하트비트 신선도 예산(초).

        ``max_heartbeat_age`` 를 주면 그 값이 모든 대상 kind 에 적용되고(운영자가 간격을
        env 로 바꿨을 때의 탈출구), 안 주면 등록부의 kind 별 예산을 쓴다. loop 마다 tick 이
        달라서 한 값을 씌우면 살아 있는 루프를 죽었다고 판정한다.
        """
        if self.max_heartbeat_age is not None:
            return self.max_heartbeat_age
        return WORKER_KIND_SPECS[kind].max_heartbeat_age

    def scan_lag_limit(self, kind: str) -> Optional[int]:
        """kind 의 ``oldest_lag_seconds`` 한도(초). ``None`` 이면 그 검사를 안 한다."""
        if kind == WORKER_KIND_EXPIRY_SCAN:
            return self.max_expiry_scan_lag
        if kind == WORKER_KIND_RETENTION:
            return self.max_retention_scan_lag
        return WORKER_KIND_SPECS[kind].scan_lag_limit


@dataclass
class ReadinessReport:
    """readiness 판정 결과. ``ready`` 가 False 면 CLI 가 nonzero 로 fail-closed."""

    ready: bool
    failures: list[dict] = field(default_factory=list)
    observations: dict = field(default_factory=dict)


def collect_readiness_observations(
    session: Session, *, now: Optional[datetime.datetime] = None
) -> dict:
    """readiness 판정에 필요한 관측치를 DB 에서 수집한다(heartbeat·pending lag·dead).

    Returns:
        ``{"now", "heartbeats": {kind: {"age_seconds", "oldest_lag_seconds"}},
        "oldest_pending_lag": int|None, "dead_count": int}``. heartbeat 미존재 kind 는
        딕트에서 누락(=fail-closed 로 판정된다).
    """
    now = now or now_utc_naive()
    heartbeats: dict[str, dict] = {}
    for hb in session.query(SideEffectWorkerHeartbeat).all():
        heartbeats[hb.worker_kind] = {
            "age_seconds": max(0, int((now - hb.last_heartbeat_at).total_seconds())),
            "oldest_lag_seconds": hb.oldest_lag_seconds,
        }
    return {
        "now": now.isoformat(),
        "heartbeats": heartbeats,
        "oldest_pending_lag": oldest_pending_lag_seconds(session, now=now),
        "dead_count": dead_count(session),
    }


def evaluate_readiness(
    observations: dict,
    thresholds: ReadinessThresholds,
    kinds: Optional[Sequence[str]] = None,
) -> ReadinessReport:
    """관측치를 임계값과 대조해 fail-closed 판정한다(순수 함수 — DB 접근 없음).

    fail 규칙: 판정 대상 worker_kind heartbeat 중 하나라도 누락/stale, scan 한도가 있는
    kind 의 scan lag 누락/초과, oldest PENDING lag 초과, DEAD count 가 max_dead 초과.

    Args:
        observations: :func:`collect_readiness_observations` 결과.
        thresholds: 임계값 묶음.
        kinds: 판정 대상 worker_kind. 생략하면 outbox worker 3종(:data:`WORKER_KINDS`) —
            기존 release gate 의 뜻을 그대로 둔다. 등록부에 없는 kind 는 판정할 수 없다.

    Raises:
        ValueError: 선택이 비었거나(빈 판정 = fail-open), 등록부
            (:data:`WORKER_KIND_SPECS`)에 없는 kind 를 지정한 경우.
    """
    selected = tuple(kinds) if kinds is not None else WORKER_KINDS
    if not selected:  # 빈 선택은 볼 게 없어 무조건 ready — fail-open 이라 거부한다
        raise ValueError("no worker kind selected")
    unknown = [k for k in selected if k not in WORKER_KIND_SPECS]
    if unknown:
        raise ValueError(f"unknown worker kind(s): {', '.join(unknown)}")

    failures: list[dict] = []
    heartbeats = observations.get("heartbeats", {})

    for kind in selected:
        limit = thresholds.heartbeat_age_limit(kind)
        hb = heartbeats.get(kind)
        if hb is None:
            failures.append({"check": "heartbeat_present", "kind": kind,
                             "detail": "no heartbeat row (worker not running?)"})
            continue
        if hb["age_seconds"] >= limit:
            failures.append({"check": "heartbeat_fresh", "kind": kind,
                             "detail": hb["age_seconds"], "limit": limit})

    for kind in selected:
        scan_limit = thresholds.scan_lag_limit(kind)
        if scan_limit is not None:
            _check_scan_lag(failures, heartbeats, kind, scan_limit)

    # PENDING lag·DEAD 는 outbox 표의 상태다. outbox worker 를 하나도 안 고른 판정
    # (예: --kinds GEOCODE_SWEEP)에서 이것까지 세면 무관한 이유로 not-ready 가 된다.
    if any(WORKER_KIND_SPECS[k].outbox_scoped for k in selected):
        pending_lag = observations.get("oldest_pending_lag")
        if pending_lag is not None and pending_lag >= thresholds.max_oldest_pending_lag:
            failures.append({"check": "oldest_pending_lag", "detail": pending_lag,
                             "limit": thresholds.max_oldest_pending_lag})

        dead = observations.get("dead_count", 0)
        if dead > thresholds.max_dead:
            failures.append({"check": "dead_count", "detail": dead, "limit": thresholds.max_dead})

    return ReadinessReport(ready=not failures, failures=failures, observations=observations)


def _check_scan_lag(
    failures: list[dict], heartbeats: dict, kind: str, limit: int
) -> None:
    """scan kind 의 oldest_lag_seconds(마지막 scan 이후 경과)를 임계와 대조한다."""
    hb = heartbeats.get(kind)
    if hb is None:
        return  # heartbeat_present 에서 이미 fail 처리됨
    lag = hb.get("oldest_lag_seconds")
    if lag is None or lag >= limit:
        failures.append({"check": "scan_lag", "kind": kind,
                         "detail": lag, "limit": limit})
