"""새 주문 안내 찾기 — PostgreSQL 계약 (PGTEST-00 lane, 설계서 2026-11-20 6.1).

SQLite 증거는 ``tests/domains/test_open_order_lookup.py``. 여기서는 운영과 같은 방언에서만 드러나는 것을 본다:
전화 포함 검색(LIKE)과 번호 조각 확인, 숨은 초안 표식(JSONB ``meta.draft``) 거르기, 주소 포함 검색,
``create_order`` 안에서 자동 flush 없이 읽는 생성 기록. 번호는 시험마다 새로 만들어 다른 시험 줄과 섞이지 않는다.
"""

from __future__ import annotations

import itertools
import time

from sqlalchemy.orm import sessionmaker

from foms.services.orders.open_order_lookup import find_open_orders_for_customer, find_open_orders_with_more
from foms.services.orders.order_create import create_order
from models import Order, OrderEvent, OrderScheduleDate, User

_SEQ = itertools.count(int(time.time() * 1000) % 9000 + 1000)


def _session(pg_engine):
    return sessionmaker(bind=pg_engine)()


def _phone() -> str:
    """시험마다 다른 합성 휴대폰(숫자 11자)."""
    return f"0105{next(_SEQ) % 10000:04d}{next(_SEQ) % 1000:03d}"


def _add(session, *, digits, stage="PRODUCTION", status=None, address="합성시 가상구 다른로 1", meta_draft=False,
         deleted=False, construction=()):
    sd = {"workflow": {"stage": stage}, "parties": {"customer": {"name": "합성고객", "phone": digits}}}
    if meta_draft:
        sd["meta"] = {"draft": True}
    order = Order(
        received_date="2026-11-01", customer_name="합성고객", phone=digits, address=address, product="합성 붙박이장",
        status=status or stage, is_erp_order=True, erp_stage_code=stage, erp_phone_digits=digits,
        structured_data=sd, deleted_at="2026-11-01 10:00:00" if deleted else None,
    )
    session.add(order)
    session.flush()
    for index, date in enumerate(construction):
        session.add(OrderScheduleDate(order_id=order.id, kind="construction", date=date, source="beta_item",
                                      item_index=index))
    session.commit()
    return order.id


def test_phone_lookup_filters_and_two_number_field(pg_engine):
    s = _session(pg_engine)
    try:
        phone, other = _phone(), _phone()
        open_id = _add(s, digits=phone, construction=("2026-11-17", "2026-11-05"))
        both_id = _add(s, digits=phone + other, stage="MEASURE")
        _add(s, digits=phone, stage="COMPLETED")
        _add(s, digits=phone, stage="RECEIVED", status="DRAFT")
        _add(s, digits=phone, stage="RECEIVED", meta_draft=True)  # 숨은 초안(JSONB 표식)
        _add(s, digits=phone, deleted=True)

        rows = find_open_orders_for_customer(s, phone=f"{phone[:3]}-{phone[3:7]}-{phone[7:]}")

        assert [row["order_id"] for row in rows] == [both_id, open_id]
        assert rows[1]["construction_dates"] == ["2026-11-05", "2026-11-17"]
        assert rows[1]["stage_label"] == "생산" and rows[1]["reason"] == "phone"
        assert [row["order_id"] for row in find_open_orders_for_customer(s, phone=other)] == [both_id]
        assert find_open_orders_for_customer(s, phone=phone, exclude_order_id=open_id, limit=5) == [rows[0]]
    finally:
        s.close()


def test_address_lookup_and_more_count(pg_engine):
    s = _session(pg_engine)
    try:
        road = f"합성{next(_SEQ)}시험로"  # 도로명은 한글로 끝나야 주소 키가 나온다
        home = f"경기도 화성시 {road} 20 (가상동, 합성아파트) 2505동 1103호"
        ids = [_add(s, digits=_phone(), address=home) for _ in range(4)]
        _add(s, digits=_phone(), address=f"{road} 20 합성아파트 2505동 1104호")  # 대조군: 옆집

        rows, more = find_open_orders_with_more(s, phone="", address=f"{road} 20 합성아파트 2505동 1103호")

        assert [row["order_id"] for row in rows] == list(reversed(ids))[:3]
        assert {row["reason"] for row in rows} == {"address"}
        assert more == 1
    finally:
        s.close()


def test_create_order_records_open_order_ids(pg_engine):
    s = _session(pg_engine)
    try:
        owner = User(username=f"c7_pg_{next(_SEQ)}", password="pw-not-committed", name="STAFF_SALES", role="STAFF",
                     team="SALES", is_active=True)
        s.add(owner)
        s.commit()
        phone = _phone()
        existing_id = _add(s, digits=phone, stage="CONSTRUCTION")

        order = create_order(
            s, actor_user_id=owner.id, owner_user_id=owner.id, is_erp_order=True,
            order_fields=dict(received_date="2026-11-20", customer_name="합성고객", phone=phone, address="-",
                              product="장", status="RECEIVED"),
            structured_data={"parties": {"customer": {"name": "합성고객", "phone": phone}},
                             "items": [{"product_name": "장"}]},
        )
        s.commit()

        event = s.query(OrderEvent).filter_by(order_id=order.id, event_type="ORDER_CREATED").one()
        assert event.payload["open_order_ids"] == [existing_id]
        assert event.payload["owner_user_id"] == owner.id
    finally:
        s.close()
