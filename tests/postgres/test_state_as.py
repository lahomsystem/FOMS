"""STATE-AS-01 PostgreSQL 계약 테스트 (PGTEST-00 lane).

canonical AS cycle 전이의 원자성을 실 PostgreSQL 다중 커밋 세션으로 고정한다:

* register 커밋이 별도 세션에서 보이고(as_lifecycle cycle RECEIVED + version bump +
  ``AS_REGISTERED`` event), rollback 시 cycle/event/version 이 함께 사라진다(원자성).
* ``FOR UPDATE`` 직렬화 — 같은 RECEIVED cycle 에 동시 AS_START 하면 정확히 한쪽만 성공하고
  다른 쪽은 :class:`ASCycleError` (actual 이 이미 IN_PROGRESS). version 은 정확히 1회 bump.

``FOMS_TEST_DATABASE_URL`` 미설정이면 conftest 가 lane 을 skip 한다(dev DSN 은 env 로만
주입, 커밋 파일에 비밀번호 금지). DSN 이 없으면 sqlite domains lane(``tests/domains/
test_state_as.py``)이 동일 계약을 대체 검증한다.
"""
from __future__ import annotations

import threading
import time

from sqlalchemy.orm import sessionmaker

from foms.services.orders.as_cycle_service import (
    ASCycleError,
    register_as_cycle,
    start_as_cycle,
)
from foms.services.orders.revision import RevisionError
from foms.services.orders.state_axes import read_as_status
from models import Order, OrderEvent, User

_H = "a" * 64
_SEQ = [0]


def _session(pg_engine):
    return sessionmaker(bind=pg_engine)()


def _make_actor(session) -> User:
    _SEQ[0] += 1
    u = User(username=f"sas_{_SEQ[0]}_{int(time.time() * 1000) % 100000}",
             password="pw-not-committed", name="AS작업자", role="STAFF",
             team="CS", is_active=True)
    session.add(u)
    session.commit()
    return u


def _make_order(session) -> Order:
    o = Order(received_date="2026-07-24", customer_name="홍길동", phone="010-0000-0000",
              address="서울", product="옷장", is_erp_order=True, status="CS",
              erp_stage_code="CS", structured_data={"workflow": {"stage": "CS"}, "shipment": {}})
    session.add(o)
    session.commit()
    return o


def test_pg_register_persists(pg_engine):
    s = _session(pg_engine)
    try:
        actor = _make_actor(s)
        order = _make_order(s)
        oid = order.id
        register_as_cycle(s, order_id=oid, actor_user_id=actor.id, as_content="문 파손",
                          received_date="2026-07-24", scope_hash=_H, request_hash=_H)
        s.commit()
    finally:
        s.close()

    check = _session(pg_engine)
    try:
        o = check.query(Order).filter_by(id=oid).one()
        assert read_as_status(o) == "RECEIVED"
        assert o.status == "AS_RECEIVED"  # overlay projection
        assert o.structured_data["workflow"]["stage"] == "CS"  # main 불변
        assert o.mutation_version == 2  # 생성(1) + register(1)
        events = check.query(OrderEvent).filter_by(order_id=oid).all()
        assert [e.event_type for e in events] == ["AS_REGISTERED"]
    finally:
        check.close()


def test_pg_register_rolls_back_atomically(pg_engine):
    s = _session(pg_engine)
    try:
        actor = _make_actor(s)
        order = _make_order(s)
        oid = order.id
        register_as_cycle(s, order_id=oid, actor_user_id=actor.id, as_content="문 파손",
                          received_date="2026-07-24", scope_hash=_H, request_hash=_H)
        s.rollback()
    finally:
        s.close()

    check = _session(pg_engine)
    try:
        o = check.query(Order).filter_by(id=oid).one()
        assert "as_lifecycle" not in (o.structured_data or {})
        assert o.mutation_version == 1
        assert check.query(OrderEvent).filter_by(order_id=oid).count() == 0
    finally:
        check.close()


def test_pg_concurrent_start_only_one_wins(pg_engine):
    setup = _session(pg_engine)
    try:
        actor = _make_actor(setup)
        order = _make_order(setup)
        oid, actor_id = order.id, actor.id
        register_as_cycle(setup, order_id=oid, actor_user_id=actor_id, as_content="접수",
                          received_date="2026-07-24", scope_hash=_H, request_hash=_H)
        setup.commit()
    finally:
        setup.close()

    ready = threading.Barrier(2)
    outcome = {}

    def _run(tag):
        sess = _session(pg_engine)
        try:
            ready.wait(5.0)
            start_as_cycle(sess, order_id=oid, actor_user_id=actor_id, reason="r",
                           description="d", scope_hash=_H, request_hash=_H)
            sess.commit()
            outcome[tag] = "ok"
        except (ASCycleError, RevisionError):
            sess.rollback()
            outcome[tag] = "conflict"
        finally:
            sess.close()

    ta = threading.Thread(target=_run, args=("A",))
    tb = threading.Thread(target=_run, args=("B",))
    ta.start(); tb.start()
    ta.join(10.0); tb.join(10.0)

    assert sorted(outcome.values()) == ["conflict", "ok"], outcome

    check = _session(pg_engine)
    try:
        o = check.query(Order).filter_by(id=oid).one()
        assert read_as_status(o) == "IN_PROGRESS"
        assert o.mutation_version == 3  # 생성(1)+register(1)+start(1); 실패 전이는 bump 없음
        started = check.query(OrderEvent).filter_by(order_id=oid, event_type="AS_STARTED").count()
        assert started == 1
    finally:
        check.close()
