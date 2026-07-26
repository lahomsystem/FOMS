"""DATA-01 PostgreSQL 계약 테스트 (PGTEST-00 lane).

structured form projection(server pricing·provenance lock)과 REV-00
``execute_order_mutation`` 낙관 잠금을 **실 PostgreSQL JSONB·다중 커밋 세션**으로 검증한다.

* JSONB round-trip: projection 재계산 totals·보존 provenance 가 commit→reload 후 정확히 유지.
* 동시 저장 race: 같은 If-Match(mutation_version) 로 두 structured 저장이 경합하면 정확히
  한쪽만 성공(version→2)하고 다른 쪽은 ``REVISION_CONFLICT``(lost update 0).

``FOMS_TEST_DATABASE_URL`` (또는 PG* env) 미설정이면 lane 자체가 skip 된다(conftest). 커밋
파일에는 비밀번호를 넣지 않는다(env 로 주입).
"""
from __future__ import annotations

import copy
import threading
import time

from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.attributes import flag_modified

from foms.services.orders.revision import RevisionConflictError, execute_order_mutation
from foms.services.orders.structured_form_projection import project_structured_form
from models import Order, OrderMutationReceipt, User

_H = "b" * 64
_SEQ = [0]
_POLICY = "ERP_STRUCTURED_PUT"


def _session(pg_engine):
    return sessionmaker(bind=pg_engine)()


def _make_user(session):
    _SEQ[0] += 1
    u = User(
        username=f"data01_{_SEQ[0]}_{int(time.time() * 1000) % 100000}",
        password="pw-not-committed",
        name="작업자",
        role="ADMIN",
        team="CS",
        is_active=True,
    )
    session.add(u)
    session.commit()
    return u


def _make_order(session, structured_data):
    o = Order(
        received_date="2026-07-24",
        customer_name="홍길동",
        phone="010-0000-0000",
        address="서울 테헤란로 1",
        product="붙박이장",
        status="RECEIVED",
        is_erp_order=True,
        structured_data=structured_data,
    )
    session.add(o)
    session.commit()
    return o


def _projection_mutation(payload):
    """폼 payload 를 projection 해 structured_data 에 반영하는 mutation 콜러블."""

    def _mutate(sess, orders):
        o = orders[0]
        old_sd = o.structured_data if isinstance(o.structured_data, dict) else {}
        sd = copy.deepcopy(payload)
        project_structured_form(old_sd, sd)
        o.structured_data = sd
        flag_modified(o, "structured_data")
        return {o.id: [f"ORDER_DETAIL:{o.id}", "ORDERS_INDEX"]}

    return _mutate


# --------------------------------------------------------------------------- #
# 1. JSONB round-trip: server pricing·provenance 가 commit→reload 후 유지
# --------------------------------------------------------------------------- #
def test_projection_jsonb_round_trip(pg_engine):
    """projection 재계산 totals·보존 provenance 가 실 PG JSONB 에 정확히 저장된다."""
    setup = _session(pg_engine)
    try:
        actor = _make_user(setup)
        order = _make_order(
            setup,
            {
                "confidence": "high",
                "raw": {"text": "ORIG"},
                "workflow": {"stage": "RECEIVED"},
                "parties": {"customer": {"name": "홍길동", "phone": "010-0000-0000"}},
                "site": {"address_full": "서울 테헤란로 1"},
                "items": [{"product_name": "붙박이장", "price": 0}],
            },
        )
        order_id, actor_id = order.id, actor.id
    finally:
        setup.close()

    payload = {
        "entity_type": "order_structured",
        "confidence": "forged",          # provenance overwrite 시도 → 무시되어야 함
        "raw": {"text": "HACK"},
        "workflow": {"stage": "RECEIVED"},
        "parties": {"customer": {"name": "홍길동", "phone": "010-0000-0000"}},
        "site": {"address_full": "서울 테헤란로 1"},
        "items": [{"product_name": "장", "price": 100000}, {"product_name": "장2", "price": 50000}],
        "payment": {"free_input": "배송:30000", "discount": 20000, "deposit": 40000},
        "totals": {"items_total": 999999, "shipping_price": 888888},  # 거짓 → 무시
        "evil_inject": {"is_admin": True},                            # 임의 키 → strip
    }

    sess = _session(pg_engine)
    try:
        execute_order_mutation(
            sess,
            actor_user_id=actor_id,
            policy_id=_POLICY,
            order_ids=[order_id],
            expected_versions={order_id: 1},
            scope_hash=_H,
            request_hash=_H,
            mutation=_projection_mutation(payload),
        )
        sess.commit()
    finally:
        sess.close()

    check = _session(pg_engine)
    try:
        o = check.query(Order).filter_by(id=order_id).one()
        sd = o.structured_data
        assert o.mutation_version == 2
        assert sd["totals"]["items_total"] == 150000        # 서버 재계산
        assert sd["totals"]["shipping_price"] == 160000     # 품목150000+배송30000-할인20000
        assert sd["confidence"] == "high"                   # provenance 보존
        assert sd["raw"] == {"text": "ORIG"}
        assert "evil_inject" not in sd                      # allowlist strip
    finally:
        check.close()


# --------------------------------------------------------------------------- #
# 2. 동시 저장 race: 같은 If-Match → 한쪽만 성공, 다른 쪽 REVISION_CONFLICT
# --------------------------------------------------------------------------- #
def test_concurrent_structured_save_only_one_wins(pg_engine):
    """두 structured 저장이 같은 mutation_version=1 로 경합 → ok 1 · conflict 1(lost update 0)."""
    base_sd = {
        "workflow": {"stage": "RECEIVED"},
        "parties": {"customer": {"name": "홍길동", "phone": "010-0000-0000"}},
        "site": {"address_full": "서울 테헤란로 1"},
        "items": [{"product_name": "붙박이장", "price": 0}],
    }
    setup = _session(pg_engine)
    try:
        actor = _make_user(setup)
        order = _make_order(setup, copy.deepcopy(base_sd))
        order_id, actor_id = order.id, actor.id
    finally:
        setup.close()

    started = threading.Event()
    outcome = {}

    def _run(tag, hold, price):
        payload = copy.deepcopy(base_sd)
        payload["items"] = [{"product_name": "붙박이장", "price": price}]

        def _mutate(sess, orders):
            o = orders[0]
            sd = copy.deepcopy(payload)
            project_structured_form(o.structured_data or {}, sd)
            o.structured_data = sd
            flag_modified(o, "structured_data")
            if hold:
                started.set()
                time.sleep(0.6)  # 락을 잡은 채 대기 → 경합 스레드가 FOR UPDATE 블록
            return {o.id: ["ORDERS_INDEX"]}

        sess = _session(pg_engine)
        try:
            execute_order_mutation(
                sess,
                actor_user_id=actor_id,
                policy_id=_POLICY,
                order_ids=[order_id],
                expected_versions={order_id: 1},
                scope_hash=_H,
                request_hash=_H,
                mutation=_mutate,
            )
            sess.commit()
            outcome[tag] = "ok"
        except RevisionConflictError:
            sess.rollback()
            outcome[tag] = "conflict"
        finally:
            sess.close()

    ta = threading.Thread(target=_run, args=("A", True, 111000))
    ta.start()
    started.wait(2.0)
    tb = threading.Thread(target=_run, args=("B", False, 222000))
    tb.start()
    ta.join(5.0)
    tb.join(5.0)

    assert sorted(outcome.values()) == ["conflict", "ok"], outcome
    check = _session(pg_engine)
    try:
        o = check.query(Order).filter_by(id=order_id).one()
        assert o.mutation_version == 2  # 정확히 1회 bump(lost update 0)
        assert (
            check.query(OrderMutationReceipt).filter_by(actor_user_id=actor_id).count() == 1
        )
    finally:
        check.close()
