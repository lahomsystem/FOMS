"""shipment dashboard request 파서(parse_shipment_dashboard_filters) 동작 보존 회귀.

Batch 3 구조-추출: 라우트에서 분리한 파싱·파생 규칙이 기존과 1:1 동일함을 고정.
- q/search/manager alias 검색어
- date_from+date_to 둘 다 유효 ISO일 때만 use_range
- date 단일일(range 아닐 때, 유효 ISO)
- range/single 둘 다 없으면 당일 기본 진입
- is_construction(시공팀)·mine_only(시공팀 또는 mine=1)·user_locked_calendar_date
"""
import datetime

from flask import request

from foms.services.shipment_dashboard_filters import (
    ShipmentDashboardFilters,
    parse_shipment_dashboard_filters,
)

TODAY = datetime.date(2026, 6, 28)


class _User:
    def __init__(self, team=None):
        self.team = team


def _parse(app, query_string: str, user=None) -> ShipmentDashboardFilters:
    with app.test_request_context(f"/erp/shipment?{query_string}"):
        return parse_shipment_dashboard_filters(request, user, TODAY)


def test_default_no_args_uses_today_single_day(app):
    f = _parse(app, "")
    assert f.use_range is False
    assert f.use_single_day is True
    assert f.selected_date == "2026-06-28"
    assert f.req_date == "2026-06-28"
    assert f.search_q == ""
    assert f.user_locked_calendar_date is False


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


def test_single_day_locks_calendar(app):
    f = _parse(app, "date=2026-07-03")
    assert f.use_single_day is True
    assert f.use_range is False
    assert f.selected_date == "2026-07-03"
    assert f.user_locked_calendar_date is True  # date 인자 명시 → 고정


def test_invalid_single_day_falls_back_to_today(app):
    f = _parse(app, "date=not-a-date")
    assert f.use_single_day is True
    assert f.selected_date == "2026-06-28"
    # date 인자가 있었으므로 user_locked는 True(원본 bool(date_arg_raw))
    assert f.user_locked_calendar_date is True


def test_search_query_aliases(app):
    assert _parse(app, "q=foo").search_q == "foo"
    assert _parse(app, "search=bar").search_q == "bar"
    assert _parse(app, "manager=kim").search_q == "kim"


def test_is_construction_by_team(app):
    assert _parse(app, "", user=_User("CONSTRUCTION")).is_construction is True
    assert _parse(app, "", user=_User("SALES")).is_construction is False
    # current_user None이면 원본 식(current_user and ...) 결과는 falsy(None)
    assert not _parse(app, "", user=None).is_construction


def test_mine_only_construction_team_always_true(app):
    assert _parse(app, "", user=_User("CONSTRUCTION")).mine_only is True


def test_mine_only_non_construction_no_arg_false(app):
    assert _parse(app, "", user=_User("SALES")).mine_only is False
    assert _parse(app, "", user=None).mine_only is False
