"""REV-CLEANUP-01 PostgreSQL 계약 테스트 (PGTEST-00 lane).

``tools/ops/purge_order_mutation_receipts.run`` 이 REV-00 스키마를 재사용해 만료
receipt 만 안전하게 배치 삭제하는지 실 PostgreSQL 다중 커밋 세션으로 검증한다:

* dry-run: 삭제 0, 대상 수만 보고.
* --apply: retention 초과 만료 receipt + child read-resource(FK cascade)만 삭제,
  active(24h replay window 안)·retention 미달 receipt 와 그 resource 는 불변.
* batch/resume: batch-size 단위로 나눠 지우고 재실행은 idempotent(남은 것 0).
* advisory lock: 다른 purge 가 락을 쥐면 아무것도 지우지 않고 skip.
* 경계: retention 미달 receipt 미삭제.

REV-00 이 cache_family_generations 테이블을 만들지 않으므로(설계 SSOT §2.4 line 407
에만 존재) purge 는 그 rows 를 참조조차 하지 않는다 — invariant 는 구조적으로 성립.

``FOMS_TEST_DATABASE_URL`` 미설정이면 conftest 가 lane 을 skip 한다. 커밋 파일에는
비밀번호를 넣지 않는다(env 로 주입).
"""
from __future__ import annotations

import time
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from foms.services.datetime_kst import now_utc_naive
from tools.ops.purge_order_mutation_receipts import ADVISORY_LOCK_KEY, run
from models import Order, OrderMutationReadResource, OrderMutationReceipt, User

_H = "a" * 64  # sha256-hex placeholder
_SEQ = [0]


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _session(pg_engine):
    """pg_engine 기반 독립 세션(seed 용, commit)."""
    return sessionmaker(bind=pg_engine)()


def _make_user(session) -> User:
    _SEQ[0] += 1
    u = User(
        username=f"purge_{_SEQ[0]}_{int(time.time() * 1000) % 100000}",
        password="pw-not-committed",
        name="작업자",
        role="STAFF",
        team=None,
        is_active=True,
    )
    session.add(u)
    session.commit()
    return u


def _make_order(session) -> Order:
    o = Order(
        received_date="2026-07-24",
        customer_name="홍길동",
        phone="010-0000-0000",
        address="서울",
        product="침대",
    )
    session.add(o)
    session.commit()
    return o


def _seed_receipt(session, *, actor_id, order_id, expires_at, with_child=True) -> str:
    """receipt(+선택적 child) 한 건을 지정 expires_at 으로 삽입하고 read_receipt_id 반환."""
    rid = str(uuid.uuid4())
    session.add(
        OrderMutationReceipt(
            read_receipt_id=rid,
            actor_user_id=actor_id,
            policy_id="P",
            idempotency_key=None,
            scope_hash=_H,
            request_hash=_H,
            response_status=200,
            response_body={"mutation_receipt": rid, "resources": []},
            resulting_versions={str(order_id): 2},
            read_expires_at=expires_at,  # purge 는 무시(NOT NULL 채우기용)
            expires_at=expires_at,
        )
    )
    session.flush()  # parent 먼저 → child FK(read_receipt_id) 만족
    if with_child:
        session.add(
            OrderMutationReadResource(
                read_receipt_id=rid,
                order_id=order_id,
                resulting_version=2,
                changed_cache_families_json=["ORDERS_INDEX", f"ORDER_DETAIL:{order_id}"],
            )
        )
    session.commit()
    return rid


def _clean(session) -> None:
    """purge 대상 테이블을 비워 이 테스트의 count 를 결정적으로 만든다."""
    session.execute(text("DELETE FROM order_mutation_read_resources"))
    session.execute(text("DELETE FROM order_mutation_receipts"))
    session.commit()


def _present_receipts(pg_engine) -> set:
    # psycopg2 는 UUID 컬럼을 uuid.UUID 로 돌려주므로 str 로 정규화(seed 는 str).
    with pg_engine.connect() as conn:
        return {
            str(r[0])
            for r in conn.execute(
                text("SELECT read_receipt_id FROM order_mutation_receipts")
            ).fetchall()
        }


def _present_children(pg_engine) -> set:
    with pg_engine.connect() as conn:
        return {
            str(r[0])
            for r in conn.execute(
                text("SELECT read_receipt_id FROM order_mutation_read_resources")
            ).fetchall()
        }


# --------------------------------------------------------------------------- #
# 1. dry-run: 삭제 0, 대상 수 보고
# --------------------------------------------------------------------------- #
def test_dry_run_counts_but_deletes_nothing(pg_engine):
    s = _session(pg_engine)
    try:
        _clean(s)
        actor = _make_user(s)
        order = _make_order(s)
        now = now_utc_naive()
        rid = _seed_receipt(
            s, actor_id=actor.id, order_id=order.id,
            expires_at=now - timedelta(days=8),
        )
    finally:
        s.close()

    with pg_engine.connect() as conn:
        res = run(conn, retention_days=7, apply=False, now=now)

    assert res.applied is False
    assert res.scanned == 1
    assert res.deleted == 0
    assert res.batches == 0
    assert rid in _present_receipts(pg_engine)      # 그대로 존재
    assert rid in _present_children(pg_engine)


# --------------------------------------------------------------------------- #
# 2. --apply: expired + child cascade 만 삭제, active/retention 미달 불변
# --------------------------------------------------------------------------- #
def test_apply_deletes_expired_with_child_cascade_only(pg_engine):
    s = _session(pg_engine)
    try:
        _clean(s)
        actor = _make_user(s)
        order = _make_order(s)
        now = now_utc_naive()
        expired = _seed_receipt(
            s, actor_id=actor.id, order_id=order.id,
            expires_at=now - timedelta(days=8),      # retention(7d) 초과 → 삭제
        )
        within = _seed_receipt(
            s, actor_id=actor.id, order_id=order.id,
            expires_at=now - timedelta(hours=1),     # 만료됐지만 retention 미달 → 불변
        )
        active = _seed_receipt(
            s, actor_id=actor.id, order_id=order.id,
            expires_at=now + timedelta(hours=23),    # active/replay window → 불변
        )
    finally:
        s.close()

    with pg_engine.connect() as conn:
        res = run(conn, retention_days=7, apply=True, now=now)

    assert res.applied is True
    assert res.deleted == 1                          # >7d 만료 1건만

    present = _present_receipts(pg_engine)
    children = _present_children(pg_engine)
    # expired parent + child cascade 삭제
    assert expired not in present
    assert expired not in children
    # active + retention 미달 receipt 와 그 resource 는 불변
    assert within in present and active in present
    assert within in children and active in children


# --------------------------------------------------------------------------- #
# 3. batch/resume: batch-size 단위, 재실행 idempotent
# --------------------------------------------------------------------------- #
def test_batch_size_splits_and_rerun_is_idempotent(pg_engine):
    s = _session(pg_engine)
    try:
        _clean(s)
        actor = _make_user(s)
        order = _make_order(s)
        now = now_utc_naive()
        for i in range(5):
            _seed_receipt(
                s, actor_id=actor.id, order_id=order.id,
                expires_at=now - timedelta(days=8, seconds=i),
                with_child=False,
            )
    finally:
        s.close()

    with pg_engine.connect() as conn:
        res = run(conn, retention_days=7, batch_size=2, apply=True, now=now)
    assert res.deleted == 5
    assert res.batches == 3                           # 2 + 2 + 1

    # resume/idempotent: 다시 돌리면 남은 것 0
    with pg_engine.connect() as conn:
        res2 = run(conn, retention_days=7, batch_size=2, apply=True, now=now)
    assert res2.scanned == 0
    assert res2.deleted == 0


# --------------------------------------------------------------------------- #
# 4. advisory lock: 동시 purge skip
# --------------------------------------------------------------------------- #
def test_advisory_lock_skips_when_held(pg_engine):
    s = _session(pg_engine)
    try:
        _clean(s)
        actor = _make_user(s)
        order = _make_order(s)
        now = now_utc_naive()
        rid = _seed_receipt(
            s, actor_id=actor.id, order_id=order.id,
            expires_at=now - timedelta(days=8), with_child=False,
        )
    finally:
        s.close()

    with pg_engine.connect() as locker:
        got = locker.execute(
            text("SELECT pg_try_advisory_lock(hashtext(:k))"),
            {"k": ADVISORY_LOCK_KEY},
        ).scalar()
        assert got is True
        try:
            with pg_engine.connect() as conn:
                res = run(conn, retention_days=7, apply=True, now=now)
            assert res.locked is True
            assert res.deleted == 0
            assert rid in _present_receipts(pg_engine)  # skip → 그대로 존재
        finally:
            locker.execute(
                text("SELECT pg_advisory_unlock(hashtext(:k))"),
                {"k": ADVISORY_LOCK_KEY},
            )

    # 락 해제 후에는 정상 삭제(락이 진짜 차단 원인이었음을 증명)
    with pg_engine.connect() as conn:
        res = run(conn, retention_days=7, apply=True, now=now)
    assert res.locked is False
    assert res.deleted == 1
    assert rid not in _present_receipts(pg_engine)


# --------------------------------------------------------------------------- #
# 5. 경계 + 잘못된 인자(nonzero exit proxy)
# --------------------------------------------------------------------------- #
def test_retention_boundary_keeps_recent_expired(pg_engine):
    s = _session(pg_engine)
    try:
        _clean(s)
        actor = _make_user(s)
        order = _make_order(s)
        now = now_utc_naive()
        # 정확히 retention 경계 부근: 6d(미달, 유지) vs 8d(초과, 삭제)
        keep = _seed_receipt(
            s, actor_id=actor.id, order_id=order.id,
            expires_at=now - timedelta(days=6), with_child=False,
        )
        drop = _seed_receipt(
            s, actor_id=actor.id, order_id=order.id,
            expires_at=now - timedelta(days=8), with_child=False,
        )
    finally:
        s.close()

    with pg_engine.connect() as conn:
        res = run(conn, retention_days=7, apply=True, now=now)
    assert res.deleted == 1
    present = _present_receipts(pg_engine)
    assert keep in present          # retention 미달 → 유지
    assert drop not in present       # retention 초과 → 삭제


def test_invalid_args_raise(pg_engine):
    with pg_engine.connect() as conn:
        with pytest.raises(ValueError):
            run(conn, batch_size=0, apply=True)
        with pytest.raises(ValueError):
            run(conn, retention_days=-1, apply=True)
