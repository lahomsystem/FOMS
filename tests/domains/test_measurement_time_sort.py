"""ROUTE-02: 실측 방문시각 파서 + 동선/히어로 정렬 계약.

운영 재현(2026-08-10, production): ERP 주문은 `orders.measurement_time` 컬럼이
전부 NULL 이고 실제 시각은 `structured_data.schedule.measurement.time`에만 있다.
컬럼 기준 SQL 정렬은 키가 전부 같아 `id ASC`(접수순)로 떨어졌고, 동선 스트립은
"1번 전은영(4시)"을, 히어로 카드는 "정재영(10시)"을 '다음 방문'이라 말했다.

여기 테스트는 (1) 자유 텍스트 파서, (2) 컬럼이 NULL 이어도 route 가 방문시각
순서로 나오는지, (3) 20건 상한이 큐를 잘라내지 않는지, (4) 좌표 없는 건이
조용히 사라지지 않고 개수로 보고되는지를 고정한다.
"""

from __future__ import annotations

import pytest

from db import db_session
from foms.services.measurement_route import build_inline_route_strip_payload
from foms.services.measurement_time import (
    format_minutes_hm,
    measurement_time_sort_key,
    measurement_time_text,
    parse_measurement_time_minutes,
)
from models import Order, OrderScheduleDate

MEASURE_DATE = "2026-09-15"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("10시", 10 * 60),
        ("10시 30분", 10 * 60 + 30),
        ("09:00", 9 * 60),
        ("8시30분~9시", 8 * 60 + 30),
        ("11시", 11 * 60),
        ("12시40분", 12 * 60 + 40),
        ("4시", 16 * 60),          # 마커 없는 1~6시는 오후 관용
        ("4시 이후", 16 * 60),
        ("1시~2시", 13 * 60),
        ("오후 12시", 12 * 60),
        ("오후 5시-5시30분", 17 * 60),
        ("오전", 9 * 60),
        ("오후", 13 * 60),
        ("저녁", 18 * 60),
        ("종일", 8 * 60),
        ("", None),
        ("-", None),
        (None, None),
        ("미정", None),
    ],
)
def test_parse_measurement_time_minutes(raw, expected):
    """실측 시간 자유 텍스트 → 분 단위 정렬 키."""
    assert parse_measurement_time_minutes(raw) == expected


def test_format_minutes_hm():
    """카운트다운 위젯 계약 형식(HH:MM)."""
    assert format_minutes_hm(16 * 60) == "16:00"
    assert format_minutes_hm(8 * 60 + 30) == "08:30"
    assert format_minutes_hm(None) is None


class _FakeOrder:
    def __init__(self, order_id, structured_data=None, measurement_time=None):
        self.id = order_id
        self.structured_data = structured_data
        self.measurement_time = measurement_time


def test_measurement_time_text_prefers_structured_data():
    """flat 컬럼이 비어도 structured_data 시각을 읽는다(운영 실제 형태)."""
    order = _FakeOrder(1, {"schedule": {"measurement": {"time": "10시"}}}, None)
    assert measurement_time_text(order) == "10시"


def test_measurement_time_text_falls_back_to_column():
    """structured_data 가 없으면 legacy 컬럼 폴백."""
    assert measurement_time_text(_FakeOrder(2, None, "09:00")) == "09:00"


def test_sort_key_puts_unknown_time_last():
    """시각 미상은 항상 뒤로, 같은 시각은 id 오름차순."""
    known = _FakeOrder(9, {"schedule": {"measurement": {"time": "10시"}}})
    unknown = _FakeOrder(1, {"schedule": {"measurement": {"time": ""}}})
    assert sorted([unknown, known], key=measurement_time_sort_key) == [known, unknown]


def _make_order(idx: int, sd_time: str | None, *, lat=None, lng=None) -> Order:
    """flat measurement_time 은 비운다 — 운영 ERP 주문과 동일 형태."""
    address = f"서울시 시각구 {idx}"
    order = Order(
        received_date="2026-09-14",
        customer_name=f"시각고객{idx}",
        phone=f"010-7000-{idx:04d}",
        address=address,
        product="붙박이장",
        status="MEASURE",
        measurement_date=MEASURE_DATE,
        measurement_time=None,
        measurement_completed=False,
        manager_name="실측담당",
        is_erp_order=True,
        erp_stage_code="MEASURE",
        lat=lat,
        lng=lng,
        structured_data={
            "workflow": {"stage": "MEASURE"},
            "site": {"address_full": address},
            "schedule": {"measurement": {"date": MEASURE_DATE, "time": sd_time}},
        },
    )
    db_session.add(order)
    db_session.flush()
    db_session.add(
        OrderScheduleDate(
            order_id=order.id, kind="measurement", date=MEASURE_DATE, source="test"
        )
    )
    db_session.commit()
    return order


def test_inline_route_orders_by_visit_time_not_order_id(app):
    """flat 컬럼이 NULL 이어도 동선은 방문시각 순서 — 접수순(id) 금지."""
    with app.app_context():
        late = _make_order(1, "4시", lat=37.50, lng=127.00)      # 16:00, id 작음
        early = _make_order(2, "10시", lat=37.51, lng=127.01)    # 10:00, id 큼
        payload = build_inline_route_strip_payload(db_session, date_filter=MEASURE_DATE)

    assert [p["id"] for p in payload["route"]] == [early.id, late.id]
    assert payload["route"][0]["measurement_time"] == "10시"


def test_inline_route_reports_missing_coords_instead_of_hiding(app):
    """좌표 없는 건은 조용히 빠지지 않고 missing_coords 로 보고된다."""
    with app.app_context():
        _make_order(3, "9시", lat=37.50, lng=127.00)
        _make_order(4, "10시", lat=37.51, lng=127.01)
        _make_order(5, "11시")  # 좌표 없음
        payload = build_inline_route_strip_payload(db_session, date_filter=MEASURE_DATE)

    assert len(payload["route"]) == 2
    assert payload["total_scheduled"] == 3
    assert payload["missing_coords"] == 1
    assert payload["truncated"] == 0


def test_inline_route_limit_covers_queue_over_twenty(app):
    """하루 20건 초과 큐도 전부 그린다(옛 20 고정 상한 회귀 금지)."""
    with app.app_context():
        for i in range(22):
            _make_order(100 + i, f"{7 + i % 5}시", lat=37.5 + i * 0.001, lng=127.0)
        payload = build_inline_route_strip_payload(db_session, date_filter=MEASURE_DATE)

    assert len(payload["route"]) == 22
    assert payload["truncated"] == 0


def test_inline_route_reports_truncation_when_over_limit(app):
    """상한을 넘기면 잘린 건수를 truncated 로 보고한다."""
    with app.app_context():
        for i in range(5):
            _make_order(200 + i, "9시", lat=37.5 + i * 0.001, lng=127.0)
        payload = build_inline_route_strip_payload(
            db_session, date_filter=MEASURE_DATE, limit=3
        )

    assert len(payload["route"]) == 3
    assert payload["truncated"] == 2
