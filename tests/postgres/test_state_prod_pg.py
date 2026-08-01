"""STATE-PROD-01 PostgreSQL 계약 테스트 (PGTEST-00 lane).

생산 start/complete 전이 배선을 실 PostgreSQL 로 고정한다 — SQLite domain lane 이 잡지
못하는 두 가지:

* transition_order(PRODUCTION_START/PRODUCTION_COMPLETE) 가 실 FOR UPDATE/mutation_version/
  receipt/tx내 outbox 와 함께 커밋되어 별도 세션에서 보인다.
* ``ProductionRun.uq_production_run_current`` 부분 유니크(``WHERE is_current``) 가 실제로
  강제되어 한 주문에 current IN_PROGRESS run 은 최대 1개다(SQLite 는 이 partial 을 full
  unique 로 격하하므로 여기서만 검증 가능). 종결(COMPLETED+is_current=False)은 slot 을 푼다.

``FOMS_TEST_DATABASE_URL`` 미설정이면 conftest 가 lane 을 skip 한다(dev DSN 은 env 로만
주입, 커밋 파일에 비밀번호 금지). foms.api.production.orders import 는 PRODUCTION_START/
PRODUCTION_COMPLETE command 를 registry 에 등록하는 side-effect 를 갖는다.
"""
from __future__ import annotations

import time
import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from foms.api.production.orders import (  # import 시 command registry 등록
    _close_current_production_run,
    _mint_current_production_run,
)
from foms.services.orders.order_transition_service import COMMAND_REGISTRY, transition_order
from models import (
    DomainSideEffectOutbox,
    Order,
    OrderEvent,
    OrderMutationReceipt,
    ProductionRun,
    User,
)

_H = "a" * 64
_SEQ = [0]


def _session(pg_engine):
    return sessionmaker(bind=pg_engine)()


def _make_actor(session) -> User:
    _SEQ[0] += 1
    u = User(username=f"sp_{_SEQ[0]}_{int(time.time() * 1000) % 100000}",
             password="pw-not-committed", name="작업자", role="STAFF",
             team="PRODUCTION", is_active=True)
    session.add(u)
    session.commit()
    return u


def _make_order(session, stage="CONFIRM") -> Order:
    o = Order(received_date="2026-07-24", customer_name="홍길동", phone="010-0000-0000",
              address="서울", product="침대", is_erp_order=True, status=stage,
              erp_stage_code=stage, structured_data={"workflow": {"stage": stage}})
    session.add(o)
    session.commit()
    return o


def test_registry_has_production_commands():
    """production.orders import 가 PRODUCTION_START/COMPLETE command 를 additive 등록."""
    assert {"PRODUCTION_START", "PRODUCTION_COMPLETE"} <= set(COMMAND_REGISTRY)
    assert COMMAND_REGISTRY["PRODUCTION_START"].from_values == ("CONFIRM",)
    assert COMMAND_REGISTRY["PRODUCTION_COMPLETE"].to_values == ("CONSTRUCTION",)


# --------------------------------------------------------------------------- #
# 1. start→complete 전이가 실제 커밋되고 run 이 발급·종결된다
# --------------------------------------------------------------------------- #
def test_pg_start_then_complete_roundtrip(pg_engine):
    s = _session(pg_engine)
    try:
        actor = _make_actor(s)
        order = _make_order(s, "CONFIRM")
        oid = order.id

        start = transition_order(
            s, command_id="PRODUCTION_START", order_id=oid, actor_user_id=actor.id,
            expected_from="CONFIRM", target_value="PRODUCTION", scope_hash=_H, request_hash=_H,
        )
        _mint_current_production_run(s, oid, order.structured_data or {})
        s.commit()
        start_ev = start.event_id
    finally:
        s.close()

    check = _session(pg_engine)
    try:
        o = check.query(Order).filter_by(id=oid).one()
        assert o.erp_stage_code == "PRODUCTION" and o.status == "PRODUCTION"
        assert o.mutation_version == 2
        ev = check.query(OrderEvent).filter_by(id=start_ev).one()
        assert ev.event_type == "PRODUCTION_STARTED"
        assert check.query(DomainSideEffectOutbox).filter_by(order_event_id=start_ev).count() == 1
        assert check.query(OrderMutationReceipt).filter_by(policy_id="STATE_PRODUCTION_START").count() >= 1
        run = check.query(ProductionRun).filter_by(order_id=oid, is_current=True).one()
        assert run.status == "IN_PROGRESS"
    finally:
        check.close()

    s2 = _session(pg_engine)
    try:
        complete = transition_order(
            s2, command_id="PRODUCTION_COMPLETE", order_id=oid, actor_user_id=1,
            expected_from="PRODUCTION", target_value="CONSTRUCTION", scope_hash=_H, request_hash=_H,
        )
        _close_current_production_run(s2, oid)
        s2.commit()
        assert complete.event_id is not None
    finally:
        s2.close()

    check2 = _session(pg_engine)
    try:
        o = check2.query(Order).filter_by(id=oid).one()
        assert o.erp_stage_code == "CONSTRUCTION" and o.status == "CONSTRUCTION"
        assert check2.query(ProductionRun).filter_by(order_id=oid, is_current=True).count() == 0
        closed = check2.query(ProductionRun).filter_by(order_id=oid).one()
        assert closed.status == "COMPLETED" and closed.is_current is False
    finally:
        check2.close()


# --------------------------------------------------------------------------- #
# 2. current run partial-unique — 한 주문에 current IN_PROGRESS run 은 1개
# --------------------------------------------------------------------------- #
def test_pg_current_run_partial_unique_enforced(pg_engine):
    s = _session(pg_engine)
    try:
        order = _make_order(s, "PRODUCTION")
        oid = order.id
        s.add(ProductionRun(order_id=oid, status="IN_PROGRESS", steps=[], defects=[], is_current=True))
        s.commit()

        # 두 번째 current run 은 uq_production_run_current(partial) 위반.
        s.add(ProductionRun(order_id=oid, status="IN_PROGRESS", steps=[], defects=[], is_current=True))
        with pytest.raises(IntegrityError):
            s.commit()
        s.rollback()

        # 멱등 mint: 이미 current 가 있으면 새로 발급하지 않는다.
        _mint_current_production_run(s, oid, {})
        s.commit()
        assert s.query(ProductionRun).filter_by(order_id=oid).count() == 1

        # 종결하면 slot 이 풀려 새 current run 발급이 가능하다.
        _close_current_production_run(s, oid)
        s.commit()
        _mint_current_production_run(s, oid, {})
        s.commit()
        assert s.query(ProductionRun).filter_by(order_id=oid, is_current=True).count() == 1
        assert s.query(ProductionRun).filter_by(order_id=oid).count() == 2
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 3. same-key replay — 전이/event/version 중복 0 (실 PG 커밋 경로)
# --------------------------------------------------------------------------- #
def test_pg_same_key_replay_transitions_once(pg_engine):
    key = str(uuid.uuid4())
    s = _session(pg_engine)
    try:
        actor = _make_actor(s)
        order = _make_order(s, "CONFIRM")
        oid = order.id
        r1 = transition_order(
            s, command_id="PRODUCTION_START", order_id=oid, actor_user_id=actor.id,
            expected_from="CONFIRM", target_value="PRODUCTION",
            idempotency_key=key, scope_hash=_H, request_hash=_H,
        )
        s.commit()
        assert r1.replayed is False

        r2 = transition_order(
            s, command_id="PRODUCTION_START", order_id=oid, actor_user_id=actor.id,
            expected_from="CONFIRM", target_value="PRODUCTION",
            idempotency_key=key, scope_hash=_H, request_hash=_H,
        )
        s.commit()
        assert r2.replayed is True
        actor_id = actor.id
    finally:
        s.close()

    check = _session(pg_engine)
    try:
        o = check.query(Order).filter_by(id=oid).one()
        assert o.mutation_version == 2  # 단 1회 bump
        assert check.query(OrderEvent).filter_by(order_id=oid, event_type="PRODUCTION_STARTED").count() == 1
    finally:
        check.close()
