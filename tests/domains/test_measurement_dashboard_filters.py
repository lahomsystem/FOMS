"""measurement dashboard request 파서(parse_measurement_dashboard_filters) 동작 보존 회귀.

Batch 3 구조-추출: 라우트에서 분리한 파싱·날짜창 파생 규칙이 기존과 1:1 동일함을 고정.
- q/search/manager alias 검색어
- date_from+date_to 둘 다 유효 ISO일 때만 use_range
- date 단일일(range 아닐 때, 유효 ISO)
- range/single 둘 다 없으면 당일 기본 진입
- 패널 창 = [today, today+14d]
"""
import datetime

from flask import request

from foms.services.measurement_dashboard_filters import (
    MeasurementDashboardFilters,
    parse_measurement_dashboard_filters,
)

TODAY = datetime.date(2026, 6, 28)


def _parse(app, query_string: str) -> MeasurementDashboardFilters:
    with app.test_request_context(f"/erp/measurement?{query_string}"):
        return parse_measurement_dashboard_filters(request, TODAY)


def test_default_no_args_uses_today_single_day(app):
    f = _parse(app, "")
    assert f.use_range is False
    assert f.use_single_day is True
    assert f.selected_date == "2026-06-28"
    assert f.search_q == ""
    assert f.open_map is False
    assert f.range_start == TODAY
    assert f.range_end == datetime.date(2026, 7, 12)
    assert f.range_start_str == "2026-06-28"
    assert f.range_end_str == "2026-07-12"


def test_valid_range(app):
    f = _parse(app, "date_from=2026-07-01&date_to=2026-07-05")
    assert f.use_range is True
    assert f.use_single_day is False
    assert f.date_from == "2026-07-01"
    assert f.date_to == "2026-07-05"


def test_invalid_range_falls_back_to_today(app):
    f = _parse(app, "date_from=bad&date_to=nope")
    assert f.use_range is False
    assert f.use_single_day is True
    assert f.selected_date == "2026-06-28"


def test_single_day(app):
    f = _parse(app, "date=2026-07-03")
    assert f.use_single_day is True
    assert f.use_range is False
    assert f.selected_date == "2026-07-03"


def test_invalid_single_day_falls_back_to_today(app):
    f = _parse(app, "date=not-a-date")
    assert f.use_single_day is True
    assert f.selected_date == "2026-06-28"


def test_range_takes_precedence_over_single_date(app):
    # use_single_day = bool(req_date) and not use_range → range가 이기면 single False
    f = _parse(app, "date=2026-07-03&date_from=2026-07-01&date_to=2026-07-05")
    assert f.use_range is True
    assert f.use_single_day is False


def test_search_query_aliases(app):
    assert _parse(app, "q=foo").search_q == "foo"
    assert _parse(app, "search=bar").search_q == "bar"
    assert _parse(app, "manager=kim").search_q == "kim"


def test_open_map_flag(app):
    assert _parse(app, "open_map=1").open_map is True
    assert _parse(app, "").open_map is False
    assert _parse(app, "open_map=0").open_map is False


def test_panel_window_is_today_plus_14(app):
    f = _parse(app, "date=2026-07-03")
    # 패널 창은 selected_date와 무관하게 항상 [today, today+14]
    assert f.range_start_str == "2026-06-28"
    assert f.range_end_str == "2026-07-12"


def test_range_over_three_months_clamps_date_to(app):
    # 3개월(92일) 초과 range → date_to를 date_from+92일로 clamp
    f = _parse(app, "date_from=2026-01-01&date_to=2026-12-31")
    assert f.use_range is True
    assert f.date_from == "2026-01-01"
    assert f.date_to == "2026-04-03"  # 2026-01-01 + 92일


def test_range_within_three_months_keeps_date_to(app):
    # 3개월 이내 range → date_to 원본 유지
    f = _parse(app, "date_from=2026-07-01&date_to=2026-07-05")
    assert f.use_range is True
    assert f.date_to == "2026-07-05"


def test_range_exactly_92_days_not_clamped(app):
    # 정확히 date_from+92일은 캡 경계 → clamp 없음
    f = _parse(app, "date_from=2026-01-01&date_to=2026-04-03")
    assert f.use_range is True
    assert f.date_to == "2026-04-03"


def test_manager_filter_parsed_and_stripped(app):
    f = _parse(app, "manager_filter=%20kim%20")
    assert f.manager_filter == "kim"


def test_manager_filter_default_empty(app):
    assert _parse(app, "").manager_filter == ""
