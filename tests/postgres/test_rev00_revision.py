"""REV-00 PostgreSQL 계약 테스트 (PGTEST-00 lane).

order mutation revision helper 의 If-Match(mutation_version) 검증, idempotency
replay/만료, ``FOR UPDATE`` 직렬화(lost update 0), read-after-write receipt shape,
purge 인덱스 존재를 실 PostgreSQL 다중 커밋 세션으로 검증한다.
``FOMS_TEST_DATABASE_URL`` 미설정이면 lane 자체가 skip 된다(conftest). 커밋 파일에는
비밀번호를 넣지 않는다(env 로 주입).

helper 는 아직 실제 mutation route 에 적용되지 않았다(REV-00 경계) — 이 테스트가
하류 packet 이 의존할 계약을 정본으로 고정한다.
"""
from __future__ import annotations

import datetime
import threading
import time
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from foms.services.datetime_kst import now_utc_naive
from foms.services.orders.revision import (
    IDEMPOTENCY_REPLAY_WINDOW,
    READ_RECEIPT_TTL,
    IdempotencyKeyConflictError,
    IdempotencyKeyExpiredError,
    OrderNotFoundError,
    PreconditionRequiredError,
    RevisionConflictError,
    execute_order_mutation,
)
from models import Order, OrderMutationReadResource, OrderMutationReceipt, User

_H = "a" * 64  # 아무 sha256-hex placeholder


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _session(pg_engine):
    """pg_engine 기반 독립 연결/세션(동시성 테스트용 다중 커밋)."""
    return sessionmaker(bind=pg_engine)()


_SEQ = [0]


def _make_user(session, *, role="STAFF"):
    _SEQ[0] += 1
    u = User(
        username=f"rev_{_SEQ[0]}_{int(time.time() * 1000) % 100000}",
        password="pw-not-committed",
        name="작업자",
        role=role,
        team=None,
        is_active=True,
    )
    session.add(u)
    session.commit()
    return u


def _make_order(session, **kw):
    o = Order(
        received_date="2026-07-24",
        customer_name="홍길동",
        phone="010-0000-0000",
        address="서울",
        product="침대",
    )
    for k, v in kw.items():
        setattr(o, k, v)
    session.add(o)
    session.commit()
    return o


def _touch_mutation(hold_event=None, sleep_s=0.0):
    """structured_data.counter 를 +1 하고 changed family 를 돌려주는 콜러블."""

    def _m(session, orders):
        fams = {}
        for o in orders:
            sd = dict(o.structured_data or {})
            sd["counter"] = sd.get("counter", 0) + 1
            o.structured_data = sd
            fams[o.id] = ["ORDERS_INDEX", f"ORDER_DETAIL:{o.id}"]
        if hold_event is not None:
            hold_event.set()
        if sleep_s:
            time.sleep(sleep_s)  # lock 을 잡은 채 대기 → 경합 스레드가 FOR UPDATE 블록
        return fams

    return _m


# --------------------------------------------------------------------------- #
# 1. If-Match(mutation_version)
# --------------------------------------------------------------------------- #
def test_if_match_bumps_and_records_receipt(pg_engine):
    s = _session(pg_engine)
    try:
        actor = _make_user(s)
        order = _make_order(s)
        assert order.mutation_version == 1

        result = execute_order_mutation(
            s,
            actor_user_id=actor.id,
            policy_id="ORDER_STRUCTURED_PATCH",
            order_ids=[order.id],
            expected_versions={order.id: 1},
            scope_hash=_H,
            request_hash=_H,
            mutation=_touch_mutation(),
        )
        s.commit()

        assert result.replayed is False
        assert result.headers == {"Cache-Control": "private, no-store"}
        # response shape: {mutation_receipt, resources:[{order_id,resulting_version,changed_cache_families}]}
        assert result.body["mutation_receipt"] == result.read_receipt_id
        assert result.body["resources"] == [
            {
                "order_id": order.id,
                "resulting_version": 2,
                "changed_cache_families": ["ORDERS_INDEX", f"ORDER_DETAIL:{order.id}"],
            }
        ]
        uuid.UUID(result.read_receipt_id)  # opaque 128-bit UUID

        s.refresh(order)
        assert order.mutation_version == 2
        assert order.structured_data["counter"] == 1

        receipt = (
            s.query(OrderMutationReceipt)
            .filter_by(read_receipt_id=result.read_receipt_id)
            .one()
        )
        assert receipt.actor_user_id == actor.id
        assert receipt.resulting_versions == {str(order.id): 2}
        child = (
            s.query(OrderMutationReadResource)
            .filter_by(read_receipt_id=result.read_receipt_id, order_id=order.id)
            .one()
        )
        assert child.resulting_version == 2
    finally:
        s.close()


def test_if_match_mismatch_409_no_change(pg_engine):
    s = _session(pg_engine)
    try:
        actor = _make_user(s)
        order = _make_order(s)  # version 1
        with pytest.raises(RevisionConflictError) as ei:
            execute_order_mutation(
                s,
                actor_user_id=actor.id,
                policy_id="ORDER_STRUCTURED_PATCH",
                order_ids=[order.id],
                expected_versions={order.id: 99},  # stale
                scope_hash=_H,
                request_hash=_H,
                mutation=_touch_mutation(),
            )
        s.rollback()
        assert ei.value.current_versions == {order.id: 1}
        s.refresh(order)
        assert order.mutation_version == 1
        # 이 order/actor 에 receipt 가 만들어지지 않음(pg_engine 은 세션 공유 → 전역 count 금지).
        assert s.query(OrderMutationReceipt).filter_by(actor_user_id=actor.id).count() == 0
        assert (
            s.query(OrderMutationReadResource).filter_by(order_id=order.id).count() == 0
        )
    finally:
        s.close()


def test_require_if_match_missing_raises_428(pg_engine):
    s = _session(pg_engine)
    try:
        actor = _make_user(s)
        order = _make_order(s)
        with pytest.raises(PreconditionRequiredError):
            execute_order_mutation(
                s,
                actor_user_id=actor.id,
                policy_id="ORDER_STRUCTURED_PATCH",
                order_ids=[order.id],
                expected_versions=None,
                require_if_match=True,
                scope_hash=_H,
                request_hash=_H,
                mutation=_touch_mutation(),
            )
        s.rollback()
    finally:
        s.close()


def test_missing_order_raises_404(pg_engine):
    s = _session(pg_engine)
    try:
        actor = _make_user(s)
        with pytest.raises(OrderNotFoundError):
            execute_order_mutation(
                s,
                actor_user_id=actor.id,
                policy_id="ORDER_STRUCTURED_PATCH",
                order_ids=[999_999_999],
                scope_hash=_H,
                request_hash=_H,
                mutation=_touch_mutation(),
            )
        s.rollback()
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 2. idempotency replay / 만료
# --------------------------------------------------------------------------- #
def test_idempotency_replay_no_duplicate_write(pg_engine):
    s = _session(pg_engine)
    try:
        actor = _make_user(s)
        order = _make_order(s)
        key = str(uuid.uuid4())

        r1 = execute_order_mutation(
            s,
            actor_user_id=actor.id,
            policy_id="ORDER_STRUCTURED_PATCH",
            order_ids=[order.id],
            idempotency_key=key,
            scope_hash=_H,
            request_hash=_H,
            mutation=_touch_mutation(),
        )
        s.commit()
        assert r1.replayed is False

        # 같은 key + 같은 hash replay: 저장된 응답 반환, business write 0.
        r2 = execute_order_mutation(
            s,
            actor_user_id=actor.id,
            policy_id="ORDER_STRUCTURED_PATCH",
            order_ids=[order.id],
            idempotency_key=key,
            scope_hash=_H,
            request_hash=_H,
            mutation=_touch_mutation(),
        )
        s.commit()
        assert r2.replayed is True
        assert r2.body == r1.body
        assert r2.read_receipt_id == r1.read_receipt_id

        s.refresh(order)
        assert order.mutation_version == 2  # 한 번만 bump
        assert order.structured_data["counter"] == 1  # mutation 한 번만 실행
        assert s.query(OrderMutationReceipt).filter_by(idempotency_key=key).count() == 1
    finally:
        s.close()


def test_idempotency_same_key_different_hash_conflict(pg_engine):
    s = _session(pg_engine)
    try:
        actor = _make_user(s)
        order = _make_order(s)
        key = str(uuid.uuid4())
        execute_order_mutation(
            s, actor_user_id=actor.id, policy_id="P", order_ids=[order.id],
            idempotency_key=key, scope_hash=_H, request_hash=_H,
            mutation=_touch_mutation(),
        )
        s.commit()
        with pytest.raises(IdempotencyKeyConflictError):
            execute_order_mutation(
                s, actor_user_id=actor.id, policy_id="P", order_ids=[order.id],
                idempotency_key=key, scope_hash=_H, request_hash="b" * 64,
                mutation=_touch_mutation(),
            )
        s.rollback()
    finally:
        s.close()


def test_idempotency_key_expired_after_24h(pg_engine):
    s = _session(pg_engine)
    try:
        actor = _make_user(s)
        order = _make_order(s)
        key = str(uuid.uuid4())
        t0 = now_utc_naive()
        execute_order_mutation(
            s, actor_user_id=actor.id, policy_id="P", order_ids=[order.id],
            idempotency_key=key, scope_hash=_H, request_hash=_H,
            mutation=_touch_mutation(), now=t0,
        )
        s.commit()

        # replay window(24h) 초과 뒤 같은 key → IDEMPOTENCY_KEY_EXPIRED.
        later = t0 + IDEMPOTENCY_REPLAY_WINDOW + datetime.timedelta(seconds=1)
        with pytest.raises(IdempotencyKeyExpiredError):
            execute_order_mutation(
                s, actor_user_id=actor.id, policy_id="P", order_ids=[order.id],
                idempotency_key=key, scope_hash=_H, request_hash=_H,
                mutation=_touch_mutation(), now=later,
            )
        s.rollback()
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 3. 동시성: FOR UPDATE 직렬화 → lost update 0
# --------------------------------------------------------------------------- #
def test_concurrent_mutation_serialized_no_lost_update(pg_engine):
    setup = _session(pg_engine)
    try:
        actor = _make_user(setup)
        order = _make_order(setup)
        order_id, actor_id = order.id, actor.id
    finally:
        setup.close()

    started = threading.Event()
    versions = {}

    def _run(tag, hold):
        sess = _session(pg_engine)
        try:
            res = execute_order_mutation(
                sess,
                actor_user_id=actor_id,
                policy_id="ORDER_STRUCTURED_PATCH",
                order_ids=[order_id],
                scope_hash=_H,
                request_hash=_H,
                mutation=_touch_mutation(
                    hold_event=started if hold else None,
                    sleep_s=0.6 if hold else 0.0,
                ),
            )
            sess.commit()
            versions[tag] = res.body["resources"][0]["resulting_version"]
        finally:
            sess.close()

    ta = threading.Thread(target=_run, args=("A", True))
    ta.start()
    started.wait(2.0)          # A 가 lock 을 잡고 sleep 에 들어갈 때까지
    tb = threading.Thread(target=_run, args=("B", False))
    tb.start()
    ta.join(5.0)
    tb.join(5.0)

    # 직렬화 → 둘 다 순차 성공, version 단조(2,3), counter == 2 (lost update 0).
    assert sorted(versions.values()) == [2, 3], versions
    check = _session(pg_engine)
    try:
        o = check.query(Order).filter_by(id=order_id).one()
        assert o.mutation_version == 3
        assert o.structured_data["counter"] == 2
        assert (
            check.query(OrderMutationReceipt).filter_by(actor_user_id=actor_id).count() == 2
        )
    finally:
        check.close()


def test_concurrent_if_match_only_one_wins(pg_engine):
    """둘 다 expected_version=1 → 한쪽만 성공(→2), 다른 쪽 REVISION_CONFLICT."""
    setup = _session(pg_engine)
    try:
        actor = _make_user(setup)
        order = _make_order(setup)
        order_id, actor_id = order.id, actor.id
    finally:
        setup.close()

    started = threading.Event()
    outcome = {}

    def _run(tag, hold):
        sess = _session(pg_engine)
        try:
            execute_order_mutation(
                sess,
                actor_user_id=actor_id,
                policy_id="P",
                order_ids=[order_id],
                expected_versions={order_id: 1},
                scope_hash=_H,
                request_hash=_H,
                mutation=_touch_mutation(
                    hold_event=started if hold else None,
                    sleep_s=0.6 if hold else 0.0,
                ),
            )
            sess.commit()
            outcome[tag] = "ok"
        except RevisionConflictError:
            sess.rollback()
            outcome[tag] = "conflict"
        finally:
            sess.close()

    ta = threading.Thread(target=_run, args=("A", True))
    ta.start()
    started.wait(2.0)
    tb = threading.Thread(target=_run, args=("B", False))
    tb.start()
    ta.join(5.0)
    tb.join(5.0)

    assert sorted(outcome.values()) == ["conflict", "ok"], outcome
    check = _session(pg_engine)
    try:
        o = check.query(Order).filter_by(id=order_id).one()
        assert o.mutation_version == 2  # 정확히 1회 bump
        assert (
            check.query(OrderMutationReceipt).filter_by(actor_user_id=actor_id).count() == 1
        )
    finally:
        check.close()


# --------------------------------------------------------------------------- #
# 4. read-after-write receipt shape / batch 정규화 / 상한
# --------------------------------------------------------------------------- #
def test_read_receipt_ttls_and_batch_normalization(pg_engine):
    s = _session(pg_engine)
    try:
        actor = _make_user(s)
        o1 = _make_order(s)
        o2 = _make_order(s)
        t0 = now_utc_naive()
        result = execute_order_mutation(
            s,
            actor_user_id=actor.id,
            policy_id="COPY_ORDER",
            order_ids=[o2.id, o1.id],  # 정렬 무관 — helper 가 ID 순 정규화
            scope_hash=_H,
            request_hash=_H,
            mutation=_touch_mutation(),
            now=t0,
        )
        s.commit()

        receipt = (
            s.query(OrderMutationReceipt)
            .filter_by(read_receipt_id=result.read_receipt_id)
            .one()
        )
        # read_expires_at = 커밋+2분, expires_at = 커밋+24시간.
        assert receipt.read_expires_at == t0 + READ_RECEIPT_TTL
        assert receipt.expires_at == t0 + IDEMPOTENCY_REPLAY_WINDOW
        # batch → resource ID 순 정규화, child PK (read_receipt_id, order_id) 2행.
        assert [r["order_id"] for r in result.body["resources"]] == sorted([o1.id, o2.id])
        assert (
            s.query(OrderMutationReadResource)
            .filter_by(read_receipt_id=result.read_receipt_id)
            .count()
            == 2
        )
    finally:
        s.close()


def test_resource_cap_rejected(pg_engine):
    s = _session(pg_engine)
    try:
        actor = _make_user(s)
        with pytest.raises(ValueError):
            execute_order_mutation(
                s, actor_user_id=actor.id, policy_id="P",
                order_ids=list(range(1, 1002)),  # 1001 > MAX_RESOURCES
                scope_hash=_H, request_hash=_H, mutation=_touch_mutation(),
            )
        with pytest.raises(ValueError):
            execute_order_mutation(
                s, actor_user_id=actor.id, policy_id="P", order_ids=[],
                scope_hash=_H, request_hash=_H, mutation=_touch_mutation(),
            )
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 5. purge 인덱스 존재(REV-00 은 인덱스만; purge 도구는 REV-CLEANUP-01)
# --------------------------------------------------------------------------- #
def test_expiry_purge_index_exists(pg_engine):
    with pg_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename = 'order_mutation_receipts'"
            )
        ).fetchall()
    names = {r[0] for r in rows}
    assert "ix_omr_expires_id" in names, names          # (expires_at, id) purge keyset
    assert "ix_omr_actor_read_expires" in names, names  # read cleanup
