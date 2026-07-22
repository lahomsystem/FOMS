"""실측 대시보드 route strip inline 렌더 성능 계약."""

from __future__ import annotations

from db import db_session
from foms.services.common.address_converter import FOMSAddressConverter
from foms.services.measurement_route import (
    build_inline_route_strip_payload,
    build_measurement_route_payload,
)
from models import Order, OrderScheduleDate

MEASURE_DATE = "2026-07-20"


def _make_measurement_order(idx: int, *, lat=None, lng=None) -> Order:
    order = Order(
        received_date="2026-07-19",
        customer_name=f"인라인고객{idx}",
        phone=f"010-2000-{idx:04d}",
        address=f"서울시 인라인구 {idx}",
        product="붙박이장",
        status="MEASURE",
        measurement_date=MEASURE_DATE,
        measurement_time=f"{9 + idx:02d}:00",
        manager_name="실측담당",
        is_erp_order=True,
        erp_stage_code="MEASURE",
        lat=lat,
        lng=lng,
        geocode_status="success" if lat is not None and lng is not None else "pending",
        structured_data={
            "workflow": {"stage": "MEASURE"},
            "parties": {
                "customer": {"name": f"ERP고객{idx}", "phone": f"010-3000-{idx:04d}"},
                "manager": {"name": "실측담당"},
            },
            "site": {"address_full": f"서울시 인라인구 {idx}"},
            "schedule": {"measurement": {"date": MEASURE_DATE}},
            "items": [{"product_name": "붙박이장"}],
        },
    )
    db_session.add(order)
    db_session.flush()
    db_session.add(
        OrderScheduleDate(
            order_id=order.id,
            kind="measurement",
            date=MEASURE_DATE,
            source="test",
        )
    )
    db_session.commit()
    return order


def test_inline_route_strip_uses_stored_coords_without_geocoding(app, monkeypatch):
    """대시보드 HTML 렌더 path 는 저장 좌표만 사용하고 주소 변환기를 호출하지 않는다."""
    with app.app_context():
        def _boom(self, address):  # pragma: no cover - 호출되면 회귀
            raise AssertionError(f"inline render must not geocode: {address}")

        monkeypatch.setattr(FOMSAddressConverter, "convert_address", _boom)
        _make_measurement_order(1, lat=37.501, lng=127.031)
        _make_measurement_order(2, lat=37.521, lng=127.041)

        payload = build_inline_route_strip_payload(db_session, date_filter=MEASURE_DATE)

    assert [p["customer_name"] for p in payload["route"]] == ["ERP고객1", "ERP고객2"]
    assert [(p["lat"], p["lng"]) for p in payload["route"]] == [(37.501, 127.031), (37.521, 127.041)]


def test_inline_route_strip_empty_for_missing_coords_without_geocoding(app, monkeypatch):
    """좌표가 없으면 렌더를 막지 않고 빈 inline payload 로 JS fetch 재진입을 막는다."""
    with app.app_context():
        calls = {"n": 0}

        def _boom(self, address):  # pragma: no cover - 호출되면 회귀
            calls["n"] += 1
            raise AssertionError(f"inline render must not geocode: {address}")

        monkeypatch.setattr(FOMSAddressConverter, "convert_address", _boom)
        _make_measurement_order(10, lat=None, lng=None)
        _make_measurement_order(11, lat=None, lng=None)

        payload = build_inline_route_strip_payload(db_session, date_filter=MEASURE_DATE)

    assert payload == {"route": []}
    assert calls["n"] == 0


def test_route_payload_persists_geocoded_coords(app, monkeypatch):
    """API route 계보는 지오코딩 성공 좌표를 주문에 저장한다(다음 방문 fast path)."""
    with app.app_context():
        monkeypatch.setattr(
            FOMSAddressConverter,
            "convert_address",
            lambda self, address: (37.111, 127.222, "success"),
        )
        o1 = _make_measurement_order(20, lat=None, lng=None)
        o2 = _make_measurement_order(21, lat=None, lng=None)
        ids = (o1.id, o2.id)

        payload = build_measurement_route_payload(db_session, date_filter=MEASURE_DATE)
        assert payload["total_points"] == 2

        db_session.expire_all()
        saved = db_session.query(Order).filter(Order.id.in_(ids)).all()
        assert len(saved) == 2
        for order in saved:
            assert (order.lat, order.lng) == (37.111, 127.222)
            assert order.geocode_status == "success"
            assert order.geocoded_at is not None


def test_route_payload_keeps_existing_coords(app, monkeypatch):
    """이미 좌표가 있는 주문은 변환기가 다른 좌표를 줘도 덮어쓰지 않는다(멱등)."""
    with app.app_context():
        monkeypatch.setattr(
            FOMSAddressConverter,
            "convert_address",
            lambda self, address: (35.999, 128.999, "success"),
        )
        o1 = _make_measurement_order(30, lat=37.501, lng=127.031)
        o2 = _make_measurement_order(31, lat=37.521, lng=127.041)
        ids = (o1.id, o2.id)

        build_measurement_route_payload(db_session, date_filter=MEASURE_DATE)

        db_session.expire_all()
        saved = {o.id: o for o in db_session.query(Order).filter(Order.id.in_(ids)).all()}
        assert (saved[ids[0]].lat, saved[ids[0]].lng) == (37.501, 127.031)
        assert (saved[ids[1]].lat, saved[ids[1]].lng) == (37.521, 127.041)
