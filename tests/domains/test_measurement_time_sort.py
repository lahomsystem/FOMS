"""ROUTE-02: 실측 방문시각 파서 + 히어로 정렬 계약.

운영 재현(2026-08-10, production): ERP 주문은 `orders.measurement_time` 컬럼이
전부 NULL 이고 실제 시각은 `structured_data.schedule.measurement.time`에만 있다.
컬럼 기준 SQL 정렬은 키가 전부 같아 `id ASC`(접수순)로 떨어져 히어로 카드가
실제 다음 방문지와 다른 사람을 '다음 방문'이라 말했다.

여기 테스트는 자유 텍스트 파서와 정렬 키(미상 시각은 뒤, 동시각은 id 오름차순)를
고정한다. 2026-09-01 동선 스트립 제거로 인라인 페이로드 계약 부분은 삭제했다.
"""

from __future__ import annotations

import pytest

from foms.services.measurement_time import (
    format_minutes_hm,
    measurement_time_sort_key,
    measurement_time_text,
    parse_measurement_time_minutes,
)

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
