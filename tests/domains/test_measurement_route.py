"""ROUTE-01: scheduled hero/next 정합 + optimized 별도 label·sequence 계약.

`measurement_route.py`의 예전 버그: `route`가 최근접 이웃(NN)으로 재배열되어
반환되어, '다음 방문'/히어로 판정(첫 미완료 지점)이 예약 순서가 아니라 NN 순서를
따랐다 — 다른 화면의 예약시각 기반 히어로 위젯과 어긋나는 원인(P1-6).

수정: `route`는 항상 예약 순서(측정 시각 오름차순)를 유지하고, NN 재배열은
`optimized_route`/`optimized_total_distance_km`로 별도 제공한다.
"""

from __future__ import annotations

from db import db_session
from foms.services.common.address_converter import FOMSAddressConverter
from foms.services.measurement_route import (
    build_inline_route_strip_payload,
    build_measurement_route_payload,
)
from models import Order, OrderScheduleDate

MEASURE_DATE = "2026-07-24"

# 지리적으로 A(시작) 기준 C가 B보다 훨씬 가깝다 → NN은 A→C→B, 예약순서는 A→B→C.
# (schedule 순서와 NN 순서가 실제로 달라야 분리가 증명됨)
_COORDS = {
    "서울시 루트구 A": (37.50, 127.00),
    "서울시 루트구 B": (37.80, 127.00),  # A와 매우 멀다
    "서울시 루트구 C": (37.52, 127.02),  # A와 매우 가깝다
}


def _make_order(idx: str, time_str: str, *, completed: bool = False) -> Order:
    address = f"서울시 루트구 {idx}"
    order = Order(
        received_date="2026-07-23",
        customer_name=f"루트고객{idx}",
        phone=f"010-4000-{ord(idx):04d}",
        address=address,
        product="붙박이장",
        status="MEASURE",
        measurement_date=MEASURE_DATE,
        measurement_time=time_str,
        measurement_completed=completed,
        manager_name="실측담당",
        is_erp_order=True,
        erp_stage_code="MEASURE",
        structured_data={
            "workflow": {"stage": "MEASURE"},
            "parties": {"manager": {"name": "실측담당"}},
            "site": {"address_full": address},
            "schedule": {"measurement": {"date": MEASURE_DATE, "time": time_str}},
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


def _stub_convert_address(self, address):
    coords = _COORDS.get(address)
    if not coords:
        return (None, None, "failed")
    return (coords[0], coords[1], "success")


def test_scheduled_route_matches_appointment_order_not_nearest_neighbor(app, monkeypatch):
    """route(예약 순서)는 측정 시각 오름차순 그대로 — NN 재배열 금지(hero/next SSOT)."""
    monkeypatch.setattr(FOMSAddressConverter, "convert_address", _stub_convert_address)
    with app.app_context():
        order_a = _make_order("A", "09:00")
        order_b = _make_order("B", "10:00")
        order_c = _make_order("C", "11:00")

        payload = build_measurement_route_payload(db_session, date_filter=MEASURE_DATE)

    scheduled_ids = [p["id"] for p in payload["route"]]
    assert scheduled_ids == [order_a.id, order_b.id, order_c.id]


def test_optimized_route_is_separate_sequence_from_scheduled(app, monkeypatch):
    """optimized_route는 NN 재배열 — scheduled route와 다른 label·sequence로 분리."""
    monkeypatch.setattr(FOMSAddressConverter, "convert_address", _stub_convert_address)
    with app.app_context():
        order_a = _make_order("A", "09:00")
        order_b = _make_order("B", "10:00")
        order_c = _make_order("C", "11:00")

        payload = build_measurement_route_payload(db_session, date_filter=MEASURE_DATE)

    scheduled_ids = [p["id"] for p in payload["route"]]
    optimized_ids = [p["id"] for p in payload["optimized_route"]]

    # NN은 A에서 시작해 더 가까운 C를 B보다 먼저 방문한다 — 예약 순서와 달라야 분리 증명.
    assert scheduled_ids == [order_a.id, order_b.id, order_c.id]
    assert optimized_ids == [order_a.id, order_c.id, order_b.id]
    assert optimized_ids != scheduled_ids
    assert payload["optimized_total_distance_km"] > 0
    # 별도 label(키 이름) — route/optimized_route가 혼동 없이 공존.
    assert "route" in payload and "optimized_route" in payload


def test_scheduled_hero_next_ignores_optimized_order(app, monkeypatch):
    """'다음 방문'(첫 미완료) 판정은 scheduled route 기준 — optimized 순서와 무관."""
    monkeypatch.setattr(FOMSAddressConverter, "convert_address", _stub_convert_address)
    with app.app_context():
        order_a = _make_order("A", "09:00", completed=True)
        order_b = _make_order("B", "10:00")
        order_c = _make_order("C", "11:00")

        payload = build_measurement_route_payload(db_session, date_filter=MEASURE_DATE)

    scheduled = payload["route"]
    next_scheduled = next(p for p in scheduled if not p["measurement_completed"])
    assert next_scheduled["id"] == order_b.id  # 예약상 다음 = B (A는 완료됨)

    # optimized 순서에서 첫 미완료는 다를 수 있다(A→C→B, A는 완료라 첫 미완료는 C) —
    # hero/next 판정은 반드시 scheduled 기준이어야 하며 optimized 기준과 섞이면 안 된다.
    optimized = payload["optimized_route"]
    next_optimized = next(p for p in optimized if not p["measurement_completed"])
    assert next_optimized["id"] == order_c.id
    assert next_scheduled["id"] != next_optimized["id"]


def test_route_payload_does_not_mutate_order_stage_or_status(app, monkeypatch):
    """DB stage 불변: 동선 계산은 order.status/structured_data.workflow.stage를 건드리지 않는다."""
    monkeypatch.setattr(FOMSAddressConverter, "convert_address", _stub_convert_address)
    with app.app_context():
        order_a = _make_order("A", "09:00")
        order_b = _make_order("B", "10:00")
        ids = (order_a.id, order_b.id)

        build_measurement_route_payload(db_session, date_filter=MEASURE_DATE)

        db_session.expire_all()
        saved = {o.id: o for o in db_session.query(Order).filter(Order.id.in_(ids)).all()}
        for order_id in ids:
            assert saved[order_id].status == "MEASURE"
            assert saved[order_id].structured_data.get("workflow", {}).get("stage") == "MEASURE"


def test_inline_route_strip_keeps_appointment_order_without_nn_reorder(app):
    """서버 인라인(fast path)도 저장 좌표 기준으로 예약 순서를 유지 — NN 재배열 없음."""
    with app.app_context():
        order_a = Order(
            received_date="2026-07-23",
            customer_name="인라인루트A",
            phone="010-5000-0001",
            address="서울시 인라인루트구 A",
            product="붙박이장",
            status="MEASURE",
            measurement_date=MEASURE_DATE,
            measurement_time="09:00",
            manager_name="실측담당",
            is_erp_order=True,
            lat=37.50,
            lng=127.00,
            geocode_status="success",
            structured_data={"schedule": {"measurement": {"date": MEASURE_DATE}}},
        )
        order_b = Order(
            received_date="2026-07-23",
            customer_name="인라인루트B",
            phone="010-5000-0002",
            address="서울시 인라인루트구 B",
            product="붙박이장",
            status="MEASURE",
            measurement_date=MEASURE_DATE,
            measurement_time="10:00",
            manager_name="실측담당",
            is_erp_order=True,
            lat=37.80,  # A와 매우 멀다 — NN이라면 C보다 나중에 방문될 좌표
            lng=127.00,
            geocode_status="success",
            structured_data={"schedule": {"measurement": {"date": MEASURE_DATE}}},
        )
        order_c = Order(
            received_date="2026-07-23",
            customer_name="인라인루트C",
            phone="010-5000-0003",
            address="서울시 인라인루트구 C",
            product="붙박이장",
            status="MEASURE",
            measurement_date=MEASURE_DATE,
            measurement_time="11:00",
            manager_name="실측담당",
            is_erp_order=True,
            lat=37.52,  # A와 매우 가깝다 — NN이라면 B보다 먼저 방문될 좌표
            lng=127.02,
            geocode_status="success",
            structured_data={"schedule": {"measurement": {"date": MEASURE_DATE}}},
        )
        for order in (order_a, order_b, order_c):
            db_session.add(order)
        db_session.flush()
        for order in (order_a, order_b, order_c):
            db_session.add(
                OrderScheduleDate(
                    order_id=order.id,
                    kind="measurement",
                    date=MEASURE_DATE,
                    source="test",
                )
            )
        db_session.commit()

        payload = build_inline_route_strip_payload(db_session, date_filter=MEASURE_DATE)

    ids = [p["id"] for p in payload["route"]]
    # NN이었다면 [A, C, B]가 됐을 것 — 예약 순서(A, B, C) 그대로여야 한다.
    assert ids == [order_a.id, order_b.id, order_c.id]
