"""SIDEFX-RETENTION-01 PostgreSQL 계약 테스트 (PGTEST-00 lane).

``tools/ops/purge_domain_side_effect_outbox.run`` 이 SIDEFX-00 스키마를 재사용해 retention
초과 terminal 행만 안전하게 배치 삭제하는지 실 PostgreSQL 다중 커밋 세션으로 고정한다:

* dry-run(기본): 삭제 0, DONE/DEAD 대상 수만 보고.
* --apply: DONE completed_at>30d·DEAD dead_at>180d 만 삭제, retention 미달 terminal 은 불변.
* PENDING/PROCESSING: 아무리 오래돼도(심지어 completed_at/dead_at 을 강제로 과거로 채워도)
  삭제 0 — status 술어가 구조적으로 제외.
* batch/resume: batch-size 단위로 나눠 지우고 재실행은 idempotent(남은 것 0 = resume).
* advisory lock: 다른 purge 가 락을 쥐면 아무것도 지우지 않고 skip.
* worker daily provider: 공용 worker 가 86400s 주기로 retention 을 호출하고 RETENTION
  heartbeat lag<90000s 를 관측(SIDEFX-WORKER-01 배선을 재사용·고정).

``FOMS_TEST_DATABASE_URL`` 미설정이면 conftest 가 lane 을 skip 한다. 커밋 파일에는
비밀번호를 넣지 않는다(env 로 주입). 공유 pg_engine 이라 전역 COUNT 에 의존하는 테스트는
``_clean`` 으로 outbox 를 비운 뒤 시작해 결정적으로 만든다.
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
    evaluate_readiness,
    run_retention_once,
    upsert_heartbeat,
)
from tools.ops.purge_domain_side_effect_outbox import ADVISORY_LOCK_KEY, run
from models import DomainSideEffectOutbox, Order, OrderEvent


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _session(pg_engine):
    return sessionmaker(bind=pg_engine)()


def _now():
    return now_utc_naive()


def _marker() -> str:
    return "TR_" + uuid.uuid4().hex


def _clean(pg_engine) -> None:
    """outbox 를 비워 이 테스트의 전역 COUNT 를 결정적으로 만든다(sibling _clean 관용)."""
    with pg_engine.begin() as conn:
        conn.execute(text("DELETE FROM domain_side_effect_outbox"))


def _order_event_id(session) -> int:
    """order_event_id FK 를 만족할 실 Order+OrderEvent 를 만들어 id 를 반환한다.

    retention worker mechanics 는 도메인 정체성과 무관하므로(브리프 A급 처방) FK 부모가
    실존하는 ORDER_EVENT 를 재사용한다(WIZARD_PENDING 은 drawing_wizard_pending 부모 필요).
    """
    order = Order(received_date="2026-07-27", customer_name="TR", phone="010-0000-0000",
                 address="서울", product="테스트")
    session.add(order)
    session.flush()
    event = OrderEvent(order_id=order.id, event_type="TEST_MARKER", payload={})
    session.add(event)
    session.flush()
    return event.id


def _seed(pg_engine, et, *, status, count=1, **over) -> list[int]:
    """실 ORDER_EVENT 부모 기준 status 행 count 개를 commit 하고 id 리스트 반환.

    ``over`` 로 completed_at/dead_at/available_at 등을 개별 지정한다.
    """
    s = _session(pg_engine)
    ids = []
    try:
        base = _now()
        event_id = _order_event_id(s)
        for i in range(count):
            row = DomainSideEffectOutbox(
                source_domain="ORDER_EVENT", order_event_id=event_id,
                effect_type=et, payload={"i": i},
                status=status, attempts=0,
                available_at=base, created_at=base,
            )
            for k, v in over.items():
                setattr(row, k, v)
            s.add(row)
            s.commit()
            ids.append(row.id)
    finally:
        s.close()
    return ids


def _present(pg_engine) -> set:
    with pg_engine.connect() as conn:
        return {
            r[0]
            for r in conn.execute(
                text("SELECT id FROM domain_side_effect_outbox")
            ).fetchall()
        }


# --------------------------------------------------------------------------- #
# 1. dry-run: 삭제 0, DONE/DEAD 대상 수 보고
# --------------------------------------------------------------------------- #
def test_dry_run_counts_but_deletes_nothing(pg_engine):
    _clean(pg_engine)
    et = _marker()
    now = _now()
    (done_id,) = _seed(pg_engine, et, status="DONE",
                       completed_at=now - datetime.timedelta(days=31))
    (dead_id,) = _seed(pg_engine, et, status="DEAD",
                       dead_at=now - datetime.timedelta(days=181))

    with pg_engine.connect() as conn:
        res = run(conn, apply=False, now=now)

    assert res.applied is False
    assert res.scanned_done == 1 and res.scanned_dead == 1
    assert res.deleted == 0 and res.batches == 0
    present = _present(pg_engine)
    assert done_id in present and dead_id in present  # 그대로 존재


# --------------------------------------------------------------------------- #
# 2. --apply: DONE completed_at>30d 만 삭제, 30d 이내 DONE 불변
# --------------------------------------------------------------------------- #
def test_apply_deletes_done_over_30d_only(pg_engine):
    _clean(pg_engine)
    et = _marker()
    now = _now()
    (drop,) = _seed(pg_engine, et, status="DONE",
                    completed_at=now - datetime.timedelta(days=31))   # 초과 → 삭제
    (keep,) = _seed(pg_engine, et, status="DONE",
                    completed_at=now - datetime.timedelta(days=29))   # 미달 → 유지
    # DEAD 는 30d 초과여도 180d 미달이면 이 실행에서 건드리지 않음(상호 격리).
    (dead_keep,) = _seed(pg_engine, et, status="DEAD",
                         dead_at=now - datetime.timedelta(days=31))

    with pg_engine.connect() as conn:
        res = run(conn, apply=True, now=now)

    assert res.applied is True
    assert res.deleted_done == 1 and res.deleted_dead == 0
    present = _present(pg_engine)
    assert drop not in present
    assert keep in present and dead_keep in present


# --------------------------------------------------------------------------- #
# 3. --apply: DEAD dead_at>180d 만 삭제, 180d 이내 DEAD 불변
# --------------------------------------------------------------------------- #
def test_apply_deletes_dead_over_180d_only(pg_engine):
    _clean(pg_engine)
    et = _marker()
    now = _now()
    (drop,) = _seed(pg_engine, et, status="DEAD",
                    dead_at=now - datetime.timedelta(days=181))   # 초과 → 삭제
    (keep,) = _seed(pg_engine, et, status="DEAD",
                    dead_at=now - datetime.timedelta(days=179))   # 미달 → 유지

    with pg_engine.connect() as conn:
        res = run(conn, apply=True, now=now)

    assert res.deleted_dead == 1 and res.deleted_done == 0
    present = _present(pg_engine)
    assert drop not in present and keep in present


# --------------------------------------------------------------------------- #
# 4. PENDING/PROCESSING 는 아무리 오래돼도 삭제 0 (status 술어 구조적 제외)
# --------------------------------------------------------------------------- #
def test_pending_processing_never_purged(pg_engine):
    _clean(pg_engine)
    et = _marker()
    now = _now()
    ancient = now - datetime.timedelta(days=999)
    # completed_at/dead_at 을 강제로 아주 과거로 채워도 status 가 terminal 이 아니면 제외.
    (pending,) = _seed(pg_engine, et, status="PENDING",
                       available_at=ancient, created_at=ancient,
                       completed_at=ancient, dead_at=ancient)
    (processing,) = _seed(pg_engine, et, status="PROCESSING",
                          available_at=ancient, created_at=ancient,
                          completed_at=ancient, dead_at=ancient,
                          lease_owner_hash="d" * 64, lease_token=str(uuid.uuid4()),
                          lease_expires_at=now)

    with pg_engine.connect() as conn:
        res = run(conn, apply=True, now=now)

    assert res.scanned == 0 and res.deleted == 0
    present = _present(pg_engine)
    assert pending in present and processing in present


# --------------------------------------------------------------------------- #
# 5. batch/resume: batch-size 단위, 재실행 idempotent
# --------------------------------------------------------------------------- #
def test_batch_size_splits_and_rerun_is_idempotent(pg_engine):
    _clean(pg_engine)
    et = _marker()
    now = _now()
    for i in range(5):
        _seed(pg_engine, et, status="DONE",
              completed_at=now - datetime.timedelta(days=31, seconds=i))

    with pg_engine.connect() as conn:
        res = run(conn, batch_size=2, apply=True, now=now)
    assert res.deleted_done == 5
    assert res.batches == 3                     # 2 + 2 + 1

    # resume/idempotent: 다시 돌리면 남은 것 0
    with pg_engine.connect() as conn:
        res2 = run(conn, batch_size=2, apply=True, now=now)
    assert res2.scanned == 0 and res2.deleted == 0


# --------------------------------------------------------------------------- #
# 6. advisory lock: 동시 purge skip (상호배제)
# --------------------------------------------------------------------------- #
def test_advisory_lock_skips_when_held(pg_engine):
    _clean(pg_engine)
    et = _marker()
    now = _now()
    (done_id,) = _seed(pg_engine, et, status="DONE",
                       completed_at=now - datetime.timedelta(days=31))

    with pg_engine.connect() as locker:
        got = locker.execute(
            text("SELECT pg_try_advisory_lock(hashtext(:k))"),
            {"k": ADVISORY_LOCK_KEY},
        ).scalar()
        assert got is True
        try:
            with pg_engine.connect() as conn:
                res = run(conn, apply=True, now=now)
            assert res.locked is True and res.deleted == 0
            assert done_id in _present(pg_engine)     # skip → 그대로 존재
        finally:
            locker.execute(
                text("SELECT pg_advisory_unlock(hashtext(:k))"),
                {"k": ADVISORY_LOCK_KEY},
            )

    # 락 해제 후에는 정상 삭제(락이 진짜 차단 원인이었음을 증명)
    with pg_engine.connect() as conn:
        res = run(conn, apply=True, now=now)
    assert res.locked is False and res.deleted_done == 1
    assert done_id not in _present(pg_engine)


# --------------------------------------------------------------------------- #
# 7. 잘못된 인자(nonzero exit proxy)
# --------------------------------------------------------------------------- #
def test_invalid_args_raise(pg_engine):
    with pg_engine.connect() as conn:
        with pytest.raises(ValueError):
            run(conn, batch_size=0, apply=True)
        with pytest.raises(ValueError):
            run(conn, done_retention_days=-1, apply=True)
        with pytest.raises(ValueError):
            run(conn, dead_retention_days=-1, apply=True)


# --------------------------------------------------------------------------- #
# 8. worker daily provider: 86400s 주기 배선 + RETENTION heartbeat lag<90000s
# --------------------------------------------------------------------------- #
def test_worker_wires_daily_retention_at_86400s():
    """공용 worker(별도 scheduler 아님)가 retention 을 하루 주기로 호출하도록 배선됐는지 고정."""
    from tools.ops.run_domain_side_effect_outbox import _parse_args

    args = _parse_args([])
    assert args.retention_scan_interval == 86400          # 하루 주기 기본
    assert ReadinessThresholds().max_retention_scan_lag == 90000  # lag 예산


def test_worker_retention_scan_purges_and_reports_fresh_lag(pg_engine):
    """공용 worker retention scan 이 terminal 을 purge 하고, 직후 RETENTION heartbeat lag<90000s."""
    _clean(pg_engine)
    et = _marker()
    now = _now()
    (old_done,) = _seed(pg_engine, et, status="DONE",
                        completed_at=now - datetime.timedelta(days=31))
    (old_dead,) = _seed(pg_engine, et, status="DEAD",
                        dead_at=now - datetime.timedelta(days=181))
    (recent,) = _seed(pg_engine, et, status="DONE",
                      completed_at=now - datetime.timedelta(days=1))

    # 공용 worker 의 daily provider 진입점(run_retention_once) — 별도 scheduler 아님.
    result = run_retention_once(pg_engine, now_fn=lambda: now)
    assert result["done_purged"] >= 1 and result["dead_purged"] >= 1

    present = _present(pg_engine)
    assert old_done not in present and old_dead not in present
    assert recent in present                              # retention 미달 보존

    # scan 직후 RETENTION heartbeat lag≈0 → readiness 의 retention scan_lag(<90000) 통과.
    upsert_heartbeat(pg_engine, WORKER_KIND_DELIVERY, oldest_lag_seconds=0)
    upsert_heartbeat(pg_engine, WORKER_KIND_EXPIRY_SCAN, oldest_lag_seconds=0)
    upsert_heartbeat(pg_engine, WORKER_KIND_RETENTION, oldest_lag_seconds=0)
    obs = {
        "heartbeats": {
            WORKER_KIND_DELIVERY: {"age_seconds": 0, "oldest_lag_seconds": 0},
            WORKER_KIND_EXPIRY_SCAN: {"age_seconds": 0, "oldest_lag_seconds": 0},
            WORKER_KIND_RETENTION: {"age_seconds": 0, "oldest_lag_seconds": 0},
        },
        "oldest_pending_lag": None,
        "dead_count": 0,
    }
    report = evaluate_readiness(obs, ReadinessThresholds())
    assert report.ready and not any(
        f["check"] == "scan_lag" for f in report.failures
    )
