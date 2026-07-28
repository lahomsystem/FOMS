"""SIDEFX-WORKER-01 PostgreSQL 계약 테스트 (PGTEST-00 lane).

SIDEFX-00 outbox 를 소비하는 worker mechanics 를 실 PostgreSQL 다중 커밋 세션으로 고정한다:

* claim — ``FOR UPDATE SKIP LOCKED`` 로 동시 worker 2개가 서로 다른 행을 claim(중복 0),
  PROCESSING+lease 전이.
* retry/DEAD — handler 실패 시 attempts++·backoff·재큐, max attempts 소진 시 DEAD.
* expiry — 만료 lease 회수(죽은 worker 회복), attempts 소진 시 DEAD.
* delivery — 성공 handler → DONE, handler 가 provider_idempotency_key 를 본다.
* heartbeat — upsert(PK worker_kind) idempotent.
* readiness — heartbeat 신선도·scan lag·PENDING lag·DEAD count fail-closed 판정.
* retention — scan 이 purge_retention 을 호출(DONE 30d / DEAD 180d).

``FOMS_TEST_DATABASE_URL`` 미설정이면 conftest 가 lane 을 skip 한다. 커밋 파일에는
비밀번호를 넣지 않는다(env 로 주입). 세션 공유 pg_engine 이라 전역 카운트에 의존하는
테스트는 ``_quiesce`` 로 PENDING/PROCESSING/DEAD 를 중립화한 뒤 시작한다.

실 도메인 handler 는 하류(CHANNEL/URGENT/NOTIFICATION) 몫 — 이 테스트는 fake handler 로
worker mechanics 만 검증한다.
"""
from __future__ import annotations

import datetime
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from foms.services.datetime_kst import now_utc_naive
from foms.services.sidefx_worker import (
    ReadinessThresholds,
    WORKER_KIND_DELIVERY,
    WORKER_KIND_EXPIRY_SCAN,
    WORKER_KIND_RETENTION,
    claim_batch,
    clear_handlers,
    collect_readiness_observations,
    dead_count,
    evaluate_readiness,
    oldest_pending_lag_seconds,
    reclaim_expired_once,
    register_handler,
    run_delivery_once,
    run_retention_once,
    upsert_heartbeat,
)
from models import DomainSideEffectOutbox, Order, OrderEvent, SideEffectWorkerHeartbeat


@pytest.fixture(autouse=True)
def _clear_registry():
    """각 테스트 전후로 handler registry 격리."""
    clear_handlers()
    yield
    clear_handlers()


def _session(pg_engine):
    return sessionmaker(bind=pg_engine)()


def _now():
    return now_utc_naive()


def _marker() -> str:
    return "TW_" + uuid.uuid4().hex


def _quiesce(pg_engine) -> None:
    """다른 테스트가 남긴 PENDING/PROCESSING/DEAD 를 recent DONE 으로 중립화한다.

    claim/reclaim/pending-lag/dead 카운트가 전역이므로, 정확한 population 이 필요한
    테스트는 시작 시 이것으로 깨끗한 상태를 만든다(throwaway DB, xdist 워커별 격리).
    """
    now = _now()
    with pg_engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE domain_side_effect_outbox "
                "SET status='DONE', completed_at=:now, dead_at=NULL, "
                "    lease_owner_hash=NULL, lease_token=NULL, lease_expires_at=NULL "
                "WHERE status IN ('PENDING','PROCESSING','DEAD')"
            ),
            {"now": now},
        )


def _order_event_id(session) -> int:
    """order_event_id FK 를 만족할 실 Order+OrderEvent 를 만들어 id 를 반환한다.

    worker mechanics 는 도메인 정체성과 무관하므로(브리프 A급 처방) FK 부모가 실존하는
    ORDER_EVENT 를 재사용한다(WIZARD_PENDING 은 drawing_wizard_pending 부모 필요).
    """
    order = Order(received_date="2026-07-27", customer_name="TR", phone="010-0000-0000",
                 address="서울", product="테스트")
    session.add(order)
    session.flush()
    event = OrderEvent(order_id=order.id, event_type="TEST_MARKER", payload={})
    session.add(event)
    session.flush()
    return event.id


def _pending(pg_engine, effect_type, *, count=1, offset=0, **over):
    """실 ORDER_EVENT 부모 기준 PENDING 행 count 개를 commit 하고 id 리스트 반환."""
    s = _session(pg_engine)
    ids = []
    try:
        base = _now()
        event_id = _order_event_id(s)
        for i in range(count):
            row = DomainSideEffectOutbox(
                source_domain="ORDER_EVENT", order_event_id=event_id,
                effect_type=effect_type, payload={"i": i},
                status="PENDING", attempts=0,
                available_at=base - datetime.timedelta(seconds=offset + count - i),
                created_at=base,
            )
            for k, v in over.items():
                setattr(row, k, v)
            s.add(row)
            s.commit()
            ids.append(row.id)
    finally:
        s.close()
    return ids


# --------------------------------------------------------------------------- #
# 1. claim — SKIP LOCKED 동시성
# --------------------------------------------------------------------------- #
def test_skip_locked_concurrent_claim_disjoint(pg_engine):
    """동시 worker 2개가 서로 다른 행을 claim(중복 처리 0). lock 을 commit 전까지 유지."""
    _quiesce(pg_engine)
    et = _marker()
    created = set(_pending(pg_engine, et, count=4))

    s1, s2 = _session(pg_engine), _session(pg_engine)
    try:
        now = _now()
        claim1 = claim_batch(s1, owner_hash="a" * 64, lease_token=str(uuid.uuid4()),
                             batch_size=2, now=now)  # lock 잡고 미커밋
        claim2 = claim_batch(s2, owner_hash="b" * 64, lease_token=str(uuid.uuid4()),
                             batch_size=2, now=now)  # s1 잠금 행은 SKIP
        ids1 = {r.id for r in claim1}
        ids2 = {r.id for r in claim2}

        assert len(ids1) == 2 and len(ids2) == 2
        assert ids1.isdisjoint(ids2)          # 중복 claim 0
        assert ids1 | ids2 == created         # 4행 정확히 분할
        for r in claim1 + claim2:
            assert r.status == "PROCESSING"
            assert r.lease_owner_hash and r.lease_expires_at and r.attempts == 1
        s1.commit()
        s2.commit()
    finally:
        s1.close()
        s2.close()


# --------------------------------------------------------------------------- #
# 2. delivery — 성공 DONE + provider idempotency
# --------------------------------------------------------------------------- #
def test_delivery_success_marks_done(pg_engine):
    """성공 handler → DONE, handler 가 provider_idempotency_key 를 관찰한다."""
    _quiesce(pg_engine)
    et = _marker()
    (row_id,) = _pending(pg_engine, et, count=1, provider_idempotency_key="prov-xyz")

    seen = []
    register_handler(et, lambda r: seen.append(r.provider_idempotency_key))

    result = run_delivery_once(
        pg_engine, owner_hash="w" * 64, lease_token_fn=lambda: str(uuid.uuid4()))

    assert result["done"] >= 1
    assert seen == ["prov-xyz"]
    s = _session(pg_engine)
    try:
        r = s.get(DomainSideEffectOutbox, row_id)
        assert r.status == "DONE" and r.completed_at is not None
        assert r.lease_owner_hash is None and r.lease_token is None
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 3. retry / backoff / DEAD
# --------------------------------------------------------------------------- #
def test_delivery_failure_retries_with_backoff(pg_engine):
    """handler 실패 → PENDING 재큐, attempts++, available_at 이 backoff 만큼 미래로."""
    _quiesce(pg_engine)
    et = _marker()
    (row_id,) = _pending(pg_engine, et, count=1)

    def boom(_r):
        raise RuntimeError("provider down")

    register_handler(et, boom)
    now = _now()
    result = run_delivery_once(
        pg_engine, owner_hash="w" * 64, lease_token_fn=lambda: str(uuid.uuid4()),
        max_attempts=5, now_fn=lambda: now)

    assert result["retried"] == 1 and result["dead"] == 0
    s = _session(pg_engine)
    try:
        r = s.get(DomainSideEffectOutbox, row_id)
        assert r.status == "PENDING" and r.attempts == 1
        assert r.available_at > now           # backoff 로 미래 예약
        assert r.last_error and "provider down" in r.last_error
        assert r.lease_owner_hash is None
    finally:
        s.close()


def test_delivery_reaches_dead_after_max_attempts(pg_engine):
    """max attempts 소진하면 DEAD 로 전이(dead_at 기록)."""
    _quiesce(pg_engine)
    et = _marker()
    (row_id,) = _pending(pg_engine, et, count=1)
    register_handler(et, lambda _r: (_ for _ in ()).throw(RuntimeError("nope")))

    clock = [_now()]
    max_attempts = 3
    for _ in range(max_attempts):
        run_delivery_once(
            pg_engine, owner_hash="w" * 64, lease_token_fn=lambda: str(uuid.uuid4()),
            max_attempts=max_attempts, now_fn=lambda: clock[0])
        clock[0] = clock[0] + datetime.timedelta(hours=1)  # backoff 넘겨 재claim 가능하게

    s = _session(pg_engine)
    try:
        r = s.get(DomainSideEffectOutbox, row_id)
        assert r.status == "DEAD" and r.attempts == max_attempts
        assert r.dead_at is not None and r.lease_owner_hash is None
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 4. expiry scan — 만료 lease 회수
# --------------------------------------------------------------------------- #
def test_reclaim_expired_lease_requeues(pg_engine):
    """만료 lease PROCESSING 행을 PENDING 으로 회수(attempts 여유). 소진 시 DEAD."""
    _quiesce(pg_engine)
    et = _marker()
    now = _now()
    s = _session(pg_engine)
    try:
        event_id = _order_event_id(s)
        alive = DomainSideEffectOutbox(
            source_domain="ORDER_EVENT", order_event_id=event_id, effect_type=et,
            payload={}, status="PROCESSING", attempts=1,
            available_at=now, created_at=now, lease_owner_hash="d" * 64,
            lease_token=str(uuid.uuid4()),
            lease_expires_at=now - datetime.timedelta(seconds=5))  # 만료
        maxed = DomainSideEffectOutbox(
            source_domain="ORDER_EVENT", order_event_id=event_id, effect_type=et,
            payload={}, status="PROCESSING", attempts=5,
            available_at=now, created_at=now, lease_owner_hash="d" * 64,
            lease_token=str(uuid.uuid4()),
            lease_expires_at=now - datetime.timedelta(seconds=5))
        s.add(alive)
        s.add(maxed)
        s.commit()
        alive_id, maxed_id = alive.id, maxed.id
    finally:
        s.close()

    result = reclaim_expired_once(pg_engine, max_attempts=5, now_fn=lambda: now)
    assert result["reclaimed"] == 2
    assert result["requeued"] == 1 and result["dead"] == 1

    s = _session(pg_engine)
    try:
        assert s.get(DomainSideEffectOutbox, alive_id).status == "PENDING"
        assert s.get(DomainSideEffectOutbox, alive_id).lease_owner_hash is None
        assert s.get(DomainSideEffectOutbox, maxed_id).status == "DEAD"
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 5. heartbeat upsert
# --------------------------------------------------------------------------- #
def test_heartbeat_upsert_idempotent(pg_engine):
    """worker_kind PK upsert — 두 번 써도 한 행, 최신 값 유지."""
    upsert_heartbeat(pg_engine, WORKER_KIND_DELIVERY, oldest_lag_seconds=3)
    upsert_heartbeat(pg_engine, WORKER_KIND_DELIVERY, oldest_lag_seconds=7,
                     metadata={"n": 1})
    s = _session(pg_engine)
    try:
        rows = s.query(SideEffectWorkerHeartbeat).filter_by(
            worker_kind=WORKER_KIND_DELIVERY).all()
        assert len(rows) == 1
        assert rows[0].oldest_lag_seconds == 7
        assert rows[0].metadata_json == {"n": 1}
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 6. readiness — 순수 판정 + 관측 수집 배선
# --------------------------------------------------------------------------- #
def _obs(**over):
    base = {
        "heartbeats": {
            WORKER_KIND_DELIVERY: {"age_seconds": 5, "oldest_lag_seconds": 2},
            WORKER_KIND_EXPIRY_SCAN: {"age_seconds": 5, "oldest_lag_seconds": 30},
            WORKER_KIND_RETENTION: {"age_seconds": 5, "oldest_lag_seconds": 100},
        },
        "oldest_pending_lag": 4,
        "dead_count": 0,
    }
    base.update(over)
    return base


def test_readiness_ready_when_all_healthy():
    report = evaluate_readiness(_obs(), ReadinessThresholds())
    assert report.ready and report.failures == []


def test_readiness_fails_on_missing_heartbeat():
    hb = _obs()["heartbeats"]
    del hb[WORKER_KIND_RETENTION]
    report = evaluate_readiness(_obs(heartbeats=hb), ReadinessThresholds())
    assert not report.ready
    assert any(f["check"] == "heartbeat_present" for f in report.failures)


def test_readiness_fails_on_stale_and_lag_and_dead():
    stale = evaluate_readiness(
        _obs(heartbeats={**_obs()["heartbeats"],
                         WORKER_KIND_DELIVERY: {"age_seconds": 99, "oldest_lag_seconds": 2}}),
        ReadinessThresholds())
    assert not stale.ready and any(f["check"] == "heartbeat_fresh" for f in stale.failures)

    scan = evaluate_readiness(
        _obs(heartbeats={**_obs()["heartbeats"],
                         WORKER_KIND_EXPIRY_SCAN: {"age_seconds": 5, "oldest_lag_seconds": 999}}),
        ReadinessThresholds())
    assert not scan.ready and any(f["check"] == "scan_lag" for f in scan.failures)

    pend = evaluate_readiness(_obs(oldest_pending_lag=120), ReadinessThresholds())
    assert not pend.ready and any(f["check"] == "oldest_pending_lag" for f in pend.failures)

    dead = evaluate_readiness(_obs(dead_count=2), ReadinessThresholds())
    assert not dead.ready and any(f["check"] == "dead_count" for f in dead.failures)


def test_collect_readiness_observations_reflects_db(pg_engine):
    """collect 가 DB 의 dead count·pending lag·heartbeat 를 실제로 읽는다."""
    _quiesce(pg_engine)
    et = _marker()
    now = _now()
    _pending(pg_engine, et, count=1, offset=30)  # available_at ~30s 과거
    s = _session(pg_engine)
    try:
        event_id = _order_event_id(s)
        dead = DomainSideEffectOutbox(
            source_domain="ORDER_EVENT", order_event_id=event_id, effect_type=et,
            payload={}, status="DEAD", attempts=10,
            available_at=now, created_at=now,
            dead_at=now - datetime.timedelta(seconds=1))
        s.add(dead)
        s.commit()
    finally:
        s.close()
    upsert_heartbeat(pg_engine, WORKER_KIND_DELIVERY, oldest_lag_seconds=1)

    s = _session(pg_engine)
    try:
        obs = collect_readiness_observations(s, now=now)
        assert obs["dead_count"] >= 1
        assert obs["oldest_pending_lag"] is not None and obs["oldest_pending_lag"] >= 20
        assert WORKER_KIND_DELIVERY in obs["heartbeats"]
        # 직접 헬퍼도 동일 신호.
        assert dead_count(s) >= 1
        assert oldest_pending_lag_seconds(s, now=now) >= 20
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 7. retention scan → purge_retention
# --------------------------------------------------------------------------- #
def test_retention_scan_purges_terminal(pg_engine):
    """retention scan 이 오래된 DONE(30d)/DEAD(180d)만 purge, 최근 terminal 보존."""
    _quiesce(pg_engine)
    et = _marker()
    now = _now()
    s = _session(pg_engine)
    try:
        event_id = _order_event_id(s)
        old_done = DomainSideEffectOutbox(
            source_domain="ORDER_EVENT", order_event_id=event_id, effect_type=et,
            payload={}, status="DONE", available_at=now, created_at=now,
            completed_at=now - datetime.timedelta(days=31))
        old_dead = DomainSideEffectOutbox(
            source_domain="ORDER_EVENT", order_event_id=event_id, effect_type=et,
            payload={}, status="DEAD", available_at=now, created_at=now,
            dead_at=now - datetime.timedelta(days=181))
        recent_done = DomainSideEffectOutbox(
            source_domain="ORDER_EVENT", order_event_id=event_id, effect_type=et,
            payload={}, status="DONE", available_at=now, created_at=now,
            completed_at=now - datetime.timedelta(days=1))
        for r in (old_done, old_dead, recent_done):
            s.add(r)
        s.commit()
        ids = (old_done.id, old_dead.id, recent_done.id)
    finally:
        s.close()

    result = run_retention_once(pg_engine, now_fn=lambda: now)
    assert result["done_purged"] >= 1 and result["dead_purged"] >= 1

    s = _session(pg_engine)
    try:
        assert s.get(DomainSideEffectOutbox, ids[0]) is None   # old_done purged
        assert s.get(DomainSideEffectOutbox, ids[1]) is None   # old_dead purged
        assert s.get(DomainSideEffectOutbox, ids[2]) is not None  # recent 보존
    finally:
        s.close()
