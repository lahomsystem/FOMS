"""STATE-CONST-CS-01 PostgreSQL 계약 테스트 (PGTEST-00 lane).

시공 attempt 전이·CS 완료를 실 PostgreSQL 로 고정한다 — SQLite domain lane 이 잡지 못하는
세 가지:

* ``OrderConstructionAttempt.uq_construction_attempt_current`` 부분 유니크(``WHERE is_current``)
  가 실제로 강제되어 한 주문에 current attempt 는 최대 1개다(SQLite 는 이 partial 을 full
  unique 로 격하하므로 append/rework 를 여기서만 검증). 종결(REWORKED/COMPLETED·is_current=False)
  은 slot 을 풀어 **새 attempt append** 를 가능케 한다(과거 attempt immutable·override 0).
* transition_order(CONSTRUCTION_COMPLETE/CS_COMPLETE) 가 실 FOR UPDATE/mutation_version/
  receipt/tx내 outbox 와 함께 커밋되어 별도 세션에서 보인다.
* 새 attempt evidence 격리(이전 attempt evidence 혼입 0).

``FOMS_TEST_DATABASE_URL`` 미설정이면 conftest 가 lane 을 skip 한다(dev DSN 은 env 로만
주입, 커밋 파일에 비밀번호 금지). foms.api.construction.orders / foms.api.cs.complete import 는
CONSTRUCTION_COMPLETE / CS_COMPLETE command 를 registry 에 등록하는 side-effect 를 갖는다.
"""
from __future__ import annotations

import time
import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

import foms.api.cs.complete  # noqa: F401  # import 시 CS_COMPLETE command 등록
import foms.api.construction.orders  # noqa: F401  # import 시 CONSTRUCTION_COMPLETE command 등록
from foms.services.orders.order_transition_service import COMMAND_REGISTRY, transition_order
from models import (
    DomainSideEffectOutbox,
    Order,
    OrderConstructionAttempt,
    OrderEvent,
    OrderMutationReceipt,
    User,
)

_H = "c" * 64
_SEQ = [0]


def _session(pg_engine):
    return sessionmaker(bind=pg_engine)()


def _make_actor(session) -> User:
    _SEQ[0] += 1
    u = User(username=f"cc_{_SEQ[0]}_{int(time.time() * 1000) % 100000}",
             password="pw-not-committed", name="시공작업자", role="STAFF",
             team="CONSTRUCTION", is_active=True)
    session.add(u)
    session.commit()
    return u


def _make_order(session, stage="CONSTRUCTION") -> Order:
    o = Order(received_date="2026-07-24", customer_name="홍길동", phone="010-0000-0000",
              address="서울", product="붙박이장", is_erp_order=True, status=stage,
              erp_stage_code=stage, structured_data={"workflow": {"stage": stage}})
    session.add(o)
    session.commit()
    return o


def _mint_attempt(session, order_id, *, status="IN_PROGRESS", is_current=True, evidence=None):
    attempt = OrderConstructionAttempt(
        id=str(uuid.uuid4()), order_id=order_id, status=status, is_current=is_current,
        evidence=evidence if evidence is not None else {"before": [], "after": []},
    )
    session.add(attempt)
    session.commit()
    return attempt


def test_registry_has_construction_cs_commands():
    """import 가 CONSTRUCTION_COMPLETE(CONSTRUCTION→CS)·CS_COMPLETE(CS→COMPLETED) 를 additive 등록."""
    assert {"CONSTRUCTION_COMPLETE", "CS_COMPLETE"} <= set(COMMAND_REGISTRY)
    assert COMMAND_REGISTRY["CONSTRUCTION_COMPLETE"].from_values == ("CONSTRUCTION",)
    assert COMMAND_REGISTRY["CONSTRUCTION_COMPLETE"].to_values == ("CS",)  # direct COMPLETED 금지
    assert COMMAND_REGISTRY["CS_COMPLETE"].from_values == ("CS",)
    assert COMMAND_REGISTRY["CS_COMPLETE"].to_values == ("COMPLETED",)


# --------------------------------------------------------------------------- #
# 1. partial-unique current + append(과거 immutable·override 0)
# --------------------------------------------------------------------------- #
def test_pg_one_current_attempt_partial_unique(pg_engine):
    """한 주문에 current(is_current) attempt 는 최대 1개 — 두 번째 current insert 는 IntegrityError."""
    s = _session(pg_engine)
    try:
        order = _make_order(s)
        _mint_attempt(s, order.id, is_current=True)
        s.add(OrderConstructionAttempt(id=str(uuid.uuid4()), order_id=order.id,
                                       status="IN_PROGRESS", is_current=True, evidence={}))
        with pytest.raises(IntegrityError):
            s.commit()
        s.rollback()
    finally:
        s.close()


def test_pg_reworked_frees_slot_for_isolated_new_attempt(pg_engine):
    """REWORKED 봉인(is_current=False)이 slot 을 풀어 새 attempt append; 과거 immutable·evidence 격리."""
    s = _session(pg_engine)
    try:
        order = _make_order(s)
        first = _mint_attempt(s, order.id, is_current=True, evidence={"before": [], "after": [11]})
        first_id = first.id

        # 재작업 봉인: 현재 attempt 를 REWORKED·is_current=False 로(터미널).
        first.status = "REWORKED"
        first.is_current = False
        first.fail_reason = "site_issue"
        s.commit()

        # slot 이 풀려 새 attempt append 가능(빈 evidence — 이전 attempt 혼입 0).
        second = _mint_attempt(s, order.id, is_current=True)
        second_id = second.id

        s.expire_all()
        attempts = (
            s.query(OrderConstructionAttempt)
            .filter(OrderConstructionAttempt.order_id == order.id)
            .all()
        )
        assert len(attempts) == 2  # override 아님 — append
        assert second_id != first_id
        # 과거 attempt immutable: REWORKED·evidence 그대로.
        sealed = s.get(OrderConstructionAttempt, first_id)
        assert sealed.status == "REWORKED" and sealed.is_current is False
        assert sealed.evidence == {"before": [], "after": [11]}
        # 새 attempt: 격리된 빈 evidence.
        fresh = s.get(OrderConstructionAttempt, second_id)
        assert fresh.status == "IN_PROGRESS" and fresh.is_current is True
        assert fresh.evidence == {"before": [], "after": []}
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 2. transition_order 커밋(별도 세션 가시성·receipt·event·outbox)
# --------------------------------------------------------------------------- #
def test_pg_construction_complete_advances_to_cs(pg_engine):
    """CONSTRUCTION→CS 전이가 실제 커밋되고 receipt/event/outbox 가 별도 세션에서 보인다."""
    s = _session(pg_engine)
    try:
        actor = _make_actor(s)
        order = _make_order(s, "CONSTRUCTION")
        oid = order.id
        _mint_attempt(s, oid, is_current=True)

        result = transition_order(
            s, command_id="CONSTRUCTION_COMPLETE", order_id=oid, actor_user_id=actor.id,
            expected_from="CONSTRUCTION", target_value="CS", scope_hash=_H, request_hash=_H,
        )
        s.commit()
        assert result.axes_after.main == "CS"
    finally:
        s.close()

    verify = _session(pg_engine)
    try:
        saved = verify.get(Order, oid)
        assert saved.erp_stage_code == "CS" and saved.status == "CS"  # direct COMPLETED 금지
        assert verify.query(OrderEvent).filter_by(order_id=oid, event_type="CONSTRUCTION_COMPLETED").count() == 1
        assert verify.query(OrderMutationReceipt).filter_by(policy_id="STATE_CONSTRUCTION_COMPLETE").count() == 1
        assert verify.query(DomainSideEffectOutbox).filter_by(effect_type="STAGE_NOTIFICATION").count() >= 1
    finally:
        verify.close()


def test_pg_cs_complete_advances_to_completed(pg_engine):
    """CS→COMPLETED 전이가 실제 커밋되고 CS_COMPLETED event/receipt 가 별도 세션에서 보인다."""
    s = _session(pg_engine)
    try:
        actor = _make_actor(s)
        order = _make_order(s, "CS")
        oid = order.id

        result = transition_order(
            s, command_id="CS_COMPLETE", order_id=oid, actor_user_id=actor.id,
            expected_from="CS", target_value="COMPLETED", scope_hash=_H, request_hash=_H,
        )
        s.commit()
        assert result.axes_after.main == "COMPLETED"
    finally:
        s.close()

    verify = _session(pg_engine)
    try:
        saved = verify.get(Order, oid)
        assert saved.erp_stage_code == "COMPLETED" and saved.status == "COMPLETED"
        assert verify.query(OrderEvent).filter_by(order_id=oid, event_type="CS_COMPLETED").count() == 1
        assert verify.query(OrderMutationReceipt).filter_by(policy_id="STATE_CS_COMPLETE").count() == 1
    finally:
        verify.close()
