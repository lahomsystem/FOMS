"""ROUTE-01/03: scheduled hero/next 정합 + 저장 좌표 우선 계약.

`measurement_route.py`의 예전 버그: `route`가 최근접 이웃(NN)으로 재배열되어
반환되어, '다음 방문'/히어로 판정(첫 미완료 지점)이 예약 순서가 아니라 NN 순서를
따랐다 — 다른 화면의 예약시각 기반 히어로 위젯과 어긋나는 원인(P1-6).

수정: `route`는 항상 예약 순서(측정 시각 오름차순)다. NN 재배열 추정 동선
(`optimized_route`)은 2026-08-31 제거했다 — 직선거리 근사가 실제 동선과 크게
달라 쓸모가 없었다. 여기서는 예약 순서 유지만 계약으로 못 박는다.

ROUTE-03: API 빌더는 주문에 저장된 lat/lng 가 있으면 외부 주소 변환기를 부르지
않는다(응답 중앙값 5초의 원인). 좌표가 없는 주문만 폴백으로 지오코딩한다.
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

# 지리적으로 A(시작) 기준 C가 B보다 훨씬 가깝다 — 거리 기준 재배열이라면 A→C→B가
# 됐을 배치다. route는 그와 무관하게 예약순서 A→B→C를 유지해야 한다.
_COORDS = {
    "서울시 루트구 A": (37.50, 127.00),
    "서울시 루트구 B": (37.80, 127.00),  # A와 매우 멀다
    "서울시 루트구 C": (37.52, 127.02),  # A와 매우 가깝다
}


def _make_order(
    idx: str,
    time_str: str,
    *,
    completed: bool = False,
    lat: float | None = None,
    lng: float | None = None,
) -> Order:
    """실측일 주문 1건 생성. lat/lng 를 주면 '이미 지오코딩된 주문'이 된다."""
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
        lat=lat,
        lng=lng,
        geocode_status="success" if lat is not None and lng is not None else "pending",
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


def test_scheduled_hero_next_is_first_incomplete_in_appointment_order(app, monkeypatch):
    """'다음 방문'(첫 미완료) 판정은 예약 순서 route 기준 — 좌표 근접도와 무관."""
    monkeypatch.setattr(FOMSAddressConverter, "convert_address", _stub_convert_address)
    with app.app_context():
        order_a = _make_order("A", "09:00", completed=True)
        order_b = _make_order("B", "10:00")
        order_c = _make_order("C", "11:00")

        payload = build_measurement_route_payload(db_session, date_filter=MEASURE_DATE)

    scheduled = payload["route"]
    assert [p["id"] for p in scheduled] == [order_a.id, order_b.id, order_c.id]

    # C가 A에 훨씬 가깝지만(거리 재배열이라면 C가 앞) '다음 방문'은 예약상 다음인 B다.
    next_scheduled = next(p for p in scheduled if not p["measurement_completed"])
    assert next_scheduled["id"] == order_b.id  # 예약상 다음 = B (A는 완료됨)


def test_route_payload_skips_geocoding_when_coords_already_stored(app, monkeypatch):
    """ROUTE-03: 저장 좌표가 있는 주문은 주소 변환기를 단 한 번도 호출하지 않는다.

    운영에서 이 API 가 min 187ms / 중앙값 5초의 이중 분포를 보인 원인 — 저장해 둔
    좌표를 무시하고 매번 외부 지오코딩을 왕복했다(프로세스 LRU 캐시가 살아 있는
    replica 에서만 빨랐다).
    """
    calls: list[str] = []

    def _counting_convert(self, address):  # pragma: no cover - 호출되면 회귀
        calls.append(address)
        return _stub_convert_address(self, address)

    monkeypatch.setattr(FOMSAddressConverter, "convert_address", _counting_convert)
    with app.app_context():
        order_a = _make_order("A", "09:00", lat=37.50, lng=127.00)
        order_b = _make_order("B", "10:00", lat=37.80, lng=127.00)

        payload = build_measurement_route_payload(db_session, date_filter=MEASURE_DATE)

    assert calls == []  # 외부 지오코딩 왕복 0회
    assert [p["id"] for p in payload["route"]] == [order_a.id, order_b.id]
    assert [(p["lat"], p["lng"]) for p in payload["route"]] == [(37.50, 127.00), (37.80, 127.00)]
    # 저장 좌표 경로의 geo_status 는 인라인 fast path 와 동일 기준(주문의 geocode_status).
    assert [p["geo_status"] for p in payload["route"]] == ["success", "success"]


def test_route_payload_geocodes_only_orders_without_stored_coords(app, monkeypatch):
    """ROUTE-03: 좌표 없는 주문만 폴백 지오코딩 — 저장 좌표 주문은 건너뛴다."""
    calls: list[str] = []

    def _counting_convert(self, address):
        calls.append(address)
        return _stub_convert_address(self, address)

    monkeypatch.setattr(FOMSAddressConverter, "convert_address", _counting_convert)
    with app.app_context():
        order_a = _make_order("A", "09:00", lat=37.50, lng=127.00)
        order_b = _make_order("B", "10:00")  # 좌표 없음 → 폴백 대상
        ids = (order_a.id, order_b.id)

        payload = build_measurement_route_payload(db_session, date_filter=MEASURE_DATE)

        assert [p["id"] for p in payload["route"]] == [order_a.id, order_b.id]

        db_session.expire_all()
        saved = {o.id: o for o in db_session.query(Order).filter(Order.id.in_(ids)).all()}
        # 폴백 성공 좌표는 다음 요청의 fast path 를 위해 저장된다.
        assert (saved[order_b.id].lat, saved[order_b.id].lng) == _COORDS["서울시 루트구 B"]
        # 이미 좌표가 있던 주문은 그대로.
        assert (saved[order_a.id].lat, saved[order_a.id].lng) == (37.50, 127.00)

    # 변환기는 좌표 없는 B 주소로만 1회 호출됐다.
    assert calls == ["서울시 루트구 B"]


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
