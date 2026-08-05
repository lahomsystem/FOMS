"""T2 ``PAYMENT_CHANGED`` PostgreSQL 왕복 계약 (PGTEST-00 lane).

SQLite lane(``tests/domains/test_order_payment_sync.py``)이 못 증명하는 두 가지를 실 DB 로
고정한다.

1. **before 는 실 JSONB 컬럼에서 읽힌다.** before_flush 배치 SELECT 가
   ``session.connection()`` Core 실행으로 flush 전 committed ``structured_data``(JSONB)를
   되돌려주는지 — JSONB 는 SQLite ``JSON`` 과 result processing 이 다르고, 정본 저장 패턴의
   ``flag_modified`` 가 attribute history 를 파괴하므로 이 경로가 유일한 before 출처다.
2. **payload JSONB 왕복.** ``{"field","from","to","source"}`` 의 int/bool/str 값이 커밋 후
   재조회에서 파이썬 타입 그대로 돌아오는지(문자열화·널 붕괴 없음).

``FOMS_TEST_DATABASE_URL`` 미설정이면 lane 자체가 skip 된다(conftest). 커밋 파일에는
비밀번호를 넣지 않는다(env 로 주입).
"""
from __future__ import annotations

import copy
import time

from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.attributes import flag_modified

from models import Order, OrderEvent

_EVENT = "PAYMENT_CHANGED"
_SEQ = [0]


def _session(pg_engine):
    """PG 엔진에 바인딩된 실 커밋 세션 1개."""
    return sessionmaker(bind=pg_engine)()


def _sfx() -> str:
    """테스트 간 충돌을 막는 짧은 고유 접미사."""
    _SEQ[0] += 1
    return f"{_SEQ[0]}_{int(time.time() * 1000) % 1000000}"


def _erp_sd(payment: dict) -> dict:
    """payment 블록을 담은 최소 ERP structured_data."""
    return {
        "workflow": {"stage": "RECEIVED"},
        "parties": {"customer": {"name": "금액 고객", "phone": "010-1234-5678"}},
        "site": {"address_full": "서울 테헤란로 123"},
        "items": [{"product_name": "붙박이장", "price": 1000000}],
        "payment": payment,
    }


def _make_order(session, payment: dict) -> Order:
    """ERP 주문 1건을 실제로 커밋해 만든다(생성 flush 는 이벤트 대상이 아니다)."""
    order = Order(
        received_date="2026-08-01",
        customer_name=f"금액고객_{_sfx()}",
        phone="010-1234-5678",
        address="서울 테헤란로 123",
        product="붙박이장",
        status="RECEIVED",
        is_erp_order=True,
        structured_data=_erp_sd(payment),
    )
    session.add(order)
    session.commit()
    return order


def _mutate_payment(order: Order, **fields) -> None:
    """정본 패턴(deepcopy → 수정 → 재할당 → flag_modified)으로 payment 를 고친다."""
    sd = copy.deepcopy(order.structured_data or {})
    payment = dict(sd.get("payment") or {})
    payment.update(fields)
    sd["payment"] = payment
    order.structured_data = sd
    flag_modified(order, "structured_data")


def _events(session, order_id: int) -> list[OrderEvent]:
    """해당 주문의 ``PAYMENT_CHANGED`` 이벤트를 생성순으로 반환."""
    session.expire_all()
    return (
        session.query(OrderEvent)
        .filter(OrderEvent.order_id == order_id, OrderEvent.event_type == _EVENT)
        .order_by(OrderEvent.id.asc())
        .all()
    )


def test_jsonb_before_value_survives_flag_modified(pg_engine):
    """JSONB 컬럼에서 읽은 before 가 정확하고 payload 가 왕복해도 타입이 유지된다."""
    session = _session(pg_engine)
    try:
        order = _make_order(session, {"deposit": 300000, "discount": 11060})
        order_id = order.id

        _mutate_payment(order, discount=0)
        session.commit()

        events = _events(session, order_id)
        assert len(events) == 1
        payload = events[0].payload
        assert payload["field"] == "payment.discount"
        assert payload["from"] == 11060 and isinstance(payload["from"], int)
        assert payload["to"] == 0 and isinstance(payload["to"], int)
        assert payload["source"] == "system"
        assert events[0].created_by_user_id is None
    finally:
        session.close()


def test_bool_toggle_payload_round_trips_as_bool(pg_engine):
    """확인 토글 payload 의 ``from``/``to`` 가 JSONB 왕복 후에도 bool 이다."""
    session = _session(pg_engine)
    try:
        order = _make_order(session, {"deposit": 100000, "deposit_confirmed": False})
        order_id = order.id

        _mutate_payment(order, deposit_confirmed=True)
        session.commit()

        events = _events(session, order_id)
        assert len(events) == 1
        payload = events[0].payload
        assert payload["field"] == "payment.deposit_confirmed"
        assert payload["from"] is False
        assert payload["to"] is True
    finally:
        session.close()


def test_separate_transactions_each_emit_one_event(pg_engine):
    """트랜잭션이 갈리면 origin 캐시가 소거돼 각 트랜잭션마다 1건씩 남는다."""
    session = _session(pg_engine)
    try:
        order = _make_order(session, {"deposit": 100000})
        order_id = order.id

        _mutate_payment(order, deposit=200000)
        session.commit()
        _mutate_payment(order, deposit=300000)
        session.commit()

        transitions = [(e.payload["from"], e.payload["to"]) for e in _events(session, order_id)]
        assert transitions == [(100000, 200000), (200000, 300000)]
    finally:
        session.close()


def test_round_trip_within_one_transaction_leaves_no_row(pg_engine):
    """같은 트랜잭션 왕복이면 INSERT 된 이벤트 행까지 삭제돼 0건으로 끝난다."""
    session = _session(pg_engine)
    try:
        order = _make_order(session, {"discount": 11060})
        order_id = order.id

        _mutate_payment(order, discount=0)
        session.flush()
        assert len(_events(session, order_id)) == 1

        _mutate_payment(order, discount=11060)
        session.commit()
        assert _events(session, order_id) == []
    finally:
        session.close()


def test_rollback_discards_pending_state(pg_engine):
    """롤백된 트랜잭션의 pending 이벤트 상태는 다음 트랜잭션으로 새지 않는다."""
    session = _session(pg_engine)
    try:
        order = _make_order(session, {"deposit": 100000})
        order_id = order.id

        _mutate_payment(order, deposit=999000)
        session.flush()
        session.rollback()

        assert _events(session, order_id) == []

        order = session.get(Order, order_id)
        _mutate_payment(order, deposit=200000)
        session.commit()

        transitions = [(e.payload["from"], e.payload["to"]) for e in _events(session, order_id)]
        assert transitions == [(100000, 200000)]
    finally:
        session.close()
