"""AS 방문 가능시간(`schedule.as_visit.availability`) 계약 테스트 (2026-08-06).

- normalize/label SSOT (foms/services/orders/as_availability.py)
- 쓰기 경로: POST /api/update_order_field `as_visit_availability`
  (저장·as_log system 로그·초기화·값 오류 409)
"""

import pytest

from db import db_session
from models import Order
from foms.services.orders.as_availability import (
    as_availability_label,
    get_as_availability,
    normalize_as_availability,
)


def test_normalize_as_availability_contract():
    assert normalize_as_availability(None) is None
    assert normalize_as_availability({}) is None
    # 전부 무관 + 메모 없음 = 초기화와 동일
    assert normalize_as_availability({"days": "any", "time": "any"}) is None
    assert normalize_as_availability({"days": "weekend", "time": "pm"}) == {
        "days": "weekend", "time": "pm"}
    got = normalize_as_availability({"days": "Weekday", "time": "AM", "note": "  경비실 경유  "})
    assert got == {"days": "weekday", "time": "am", "note": "경비실 경유"}
    with pytest.raises(ValueError):
        normalize_as_availability({"days": "sunday"})
    with pytest.raises(ValueError):
        normalize_as_availability("weekend")
    with pytest.raises(ValueError):
        normalize_as_availability({"time": "midnight"})


def test_as_availability_label():
    assert as_availability_label(None) == ""
    assert as_availability_label({"days": "weekend", "time": "pm"}) == "주말·오후"
    assert as_availability_label(
        {"days": "weekday", "time": "any", "note": "3시 이후"}) == "평일·시간무관 (3시 이후)"


def _make_as_order():
    order = Order(
        received_date="2026-08-01",
        customer_name="가능시간 QA",
        phone="010-0000-0000",
        address="서울시 마포구 테스트로 1",
        product="붙박이장",
        status="AS_RECEIVED",
        as_received_date="2026-08-01",
        is_erp_order=True,
        structured_data={
            "parties": {"customer": {"name": "가능시간 QA", "phone": "010-0000-0000"}},
            "site": {"address_full": "서울시 마포구 테스트로 1"},
            "shipment": {},
            "schedule": {},
        },
    )
    db_session.add(order)
    db_session.commit()
    return order


def _last_as_log_text(order):
    logs = (((order.structured_data or {}).get("shipment") or {}).get("as_log") or [])
    return logs[-1]["text"] if logs else ""


def test_field_update_saves_availability_and_logs(auth_client):
    order = _make_as_order()
    resp = auth_client.post("/api/update_order_field", json={
        "order_id": order.id,
        "field": "as_visit_availability",
        "value": {"days": "weekend", "time": "pm", "note": "경비실"},
    })
    assert resp.status_code == 200, resp.get_data(as_text=True)
    db_session.expire_all()
    fresh = db_session.query(Order).get(order.id)
    assert get_as_availability(fresh.structured_data) == {
        "days": "weekend", "time": "pm", "note": "경비실"}
    assert _last_as_log_text(fresh) == "가능시간: 주말·오후 (경비실)"

    # 초기화(None) → 키 제거 + 로그
    resp = auth_client.post("/api/update_order_field", json={
        "order_id": order.id, "field": "as_visit_availability", "value": None,
    })
    assert resp.status_code == 200, resp.get_data(as_text=True)
    db_session.expire_all()
    fresh = db_session.query(Order).get(order.id)
    assert get_as_availability(fresh.structured_data) is None
    assert _last_as_log_text(fresh) == "가능시간 초기화"


def test_field_update_rejects_invalid_availability(auth_client):
    oid = _make_as_order().id
    resp = auth_client.post("/api/update_order_field", json={
        "order_id": oid,
        "field": "as_visit_availability",
        "value": {"days": "sunday"},
    })
    assert resp.status_code == 409
    db_session.expire_all()
    fresh = db_session.query(Order).get(oid)
    assert get_as_availability(fresh.structured_data) is None
