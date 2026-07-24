"""STATE-CORE-00 PostgreSQL 계약 테스트 (PGTEST-00 lane).

상태 전이 엔진의 원자성을 실 PostgreSQL 다중 커밋 세션으로 고정한다:

* ``FOR UPDATE`` 직렬화 — 같은 expected-from 으로 동시 전이하면 정확히 한쪽만 성공하고
  다른 쪽은 ``StageConflictError`` (actual 이 이미 바뀜). version 은 정확히 1회 bump,
  OrderEvent·outbox 도 1개.
* tx 원자성 — 전이 성공 commit 시 outbox 행이 별도 세션에서 보이고, rollback 시 전이·
  event·outbox 가 함께 사라진다.

``FOMS_TEST_DATABASE_URL`` 미설정이면 conftest 가 lane 을 skip 한다(dev DSN 은 env 로만
주입, 커밋 파일에 비밀번호 금지). endpoint 이관은 하류 몫이라 route 를 호출하지 않는다.
"""
from __future__ import annotations

import threading
import time
import uuid

from sqlalchemy.orm import sessionmaker

from foms.services.orders.order_transition_service import (
    StageConflictError,
    transition_order,
)
from foms.services.orders.revision import RevisionConflictError
from models import DomainSideEffectOutbox, Order, OrderEvent, OrderMutationReceipt, User

_H = "a" * 64
_SEQ = [0]


def _session(pg_engine):
    return sessionmaker(bind=pg_engine)()


def _make_actor(session) -> User:
    _SEQ[0] += 1
    u = User(username=f"st_{_SEQ[0]}_{int(time.time() * 1000) % 100000}",
             password="pw-not-committed", name="작업자", role="STAFF",
             team="CS", is_active=True)
    session.add(u)
    session.commit()
    return u


def _make_order(session, stage="RECEIVED") -> Order:
    o = Order(received_date="2026-07-24", customer_name="홍길동", phone="010-0000-0000",
              address="서울", product="침대", is_erp_order=True, status=stage,
              erp_stage_code=stage, structured_data={"workflow": {"stage": stage}})
    session.add(o)
    session.commit()
    return o


# --------------------------------------------------------------------------- #
# 1. 정상 전이가 실제로 커밋되어 별도 세션에서 보인다
# --------------------------------------------------------------------------- #
def test_pg_normal_transition_persists(pg_engine):
    s = _session(pg_engine)
    try:
        actor = _make_actor(s)
        order = _make_order(s)
        result = transition_order(
            s, command_id="REQUEST_MEASUREMENT", order_id=order.id,
            actor_user_id=actor.id, expected_from="RECEIVED", target_value="MEASURE",
            expected_version=1, scope_hash=_H, request_hash=_H,
        )
        s.commit()
        oid, ev_id = order.id, result.event_id
    finally:
        s.close()

    check = _session(pg_engine)
    try:
        o = check.query(Order).filter_by(id=oid).one()
        assert o.structured_data["workflow"]["stage"] == "MEASURE"
        assert o.erp_stage_code == "MEASURE"
        assert o.mutation_version == 2
        ev = check.query(OrderEvent).filter_by(id=ev_id).one()
        assert ev.event_type == "MEASUREMENT_REQUESTED"
        outbox = check.query(DomainSideEffectOutbox).filter_by(order_event_id=ev_id).all()
        assert len(outbox) == 1 and outbox[0].source_domain == "ORDER_EVENT"
    finally:
        check.close()


# --------------------------------------------------------------------------- #
# 2. 동시 전이: FOR UPDATE 직렬화 → 정확히 한쪽만 성공
# --------------------------------------------------------------------------- #
def test_pg_concurrent_expected_from_only_one_wins(pg_engine):
    setup = _session(pg_engine)
    try:
        actor = _make_actor(setup)
        order = _make_order(setup)
        order_id, actor_id = order.id, actor.id
    finally:
        setup.close()

    ready = threading.Barrier(2)
    outcome = {}

    def _run(tag):
        sess = _session(pg_engine)
        try:
            ready.wait(5.0)  # 두 스레드가 동시에 전이를 시도하도록 정렬
            transition_order(
                sess, command_id="REQUEST_MEASUREMENT", order_id=order_id,
                actor_user_id=actor_id, expected_from="RECEIVED", target_value="MEASURE",
                scope_hash=_H, request_hash=_H,
            )
            sess.commit()
            outcome[tag] = "ok"
        except (StageConflictError, RevisionConflictError):
            sess.rollback()
            outcome[tag] = "conflict"
        finally:
            sess.close()

    ta = threading.Thread(target=_run, args=("A",))
    tb = threading.Thread(target=_run, args=("B",))
    ta.start(); tb.start()
    ta.join(10.0); tb.join(10.0)

    # 직렬화 → 정확히 한쪽 성공, 한쪽 conflict(actual 이 MEASURE 로 바뀜).
    assert sorted(outcome.values()) == ["conflict", "ok"], outcome

    check = _session(pg_engine)
    try:
        o = check.query(Order).filter_by(id=order_id).one()
        assert o.structured_data["workflow"]["stage"] == "MEASURE"
        assert o.mutation_version == 2  # 정확히 1회 bump
        ev_ids = [e.id for e in check.query(OrderEvent).filter_by(order_id=order_id).all()]
        assert len(ev_ids) == 1  # event 1개
        assert check.query(OrderMutationReceipt).filter_by(actor_user_id=actor_id).count() == 1
        # 세션 공유 PG DB라 effect_type 은 타 테스트와 겹친다 → 이 order 의 event 로 scope.
        assert check.query(DomainSideEffectOutbox).filter(
            DomainSideEffectOutbox.order_event_id.in_(ev_ids)).count() == 1
    finally:
        check.close()


# --------------------------------------------------------------------------- #
# 3. tx 원자성 — rollback 시 전이·event·outbox 전부 사라짐
# --------------------------------------------------------------------------- #
def test_pg_transition_rolls_back_atomically(pg_engine):
    s = _session(pg_engine)
    try:
        actor = _make_actor(s)
        order = _make_order(s)
        oid = order.id
        et = "STAGE_NOTIFICATION"
        result = transition_order(
            s, command_id="REQUEST_MEASUREMENT", order_id=oid,
            actor_user_id=actor.id, expected_from="RECEIVED", target_value="MEASURE",
            idempotency_key=str(uuid.uuid4()), scope_hash=_H, request_hash=_H,
        )
        assert result.outbox_id is not None  # flush 됨(커밋 전)
        s.rollback()
    finally:
        s.close()

    check = _session(pg_engine)
    try:
        o = check.query(Order).filter_by(id=oid).one()
        assert o.structured_data["workflow"]["stage"] == "RECEIVED"
        assert o.mutation_version == 1
        assert check.query(OrderEvent).filter_by(order_id=oid).count() == 0
        # 이 order 의 event 에 매달린 outbox 도 rollback 으로 0(세션 공유 DB → order-scope).
        assert check.query(DomainSideEffectOutbox).join(
            OrderEvent, DomainSideEffectOutbox.order_event_id == OrderEvent.id
        ).filter(OrderEvent.order_id == oid).count() == 0
    finally:
        check.close()
