"""AS dashboard request 파서(parse_as_dashboard_filters) 동작 보존 회귀.

Batch 5 구조-추출: 라우트 상단 파싱·tab 화이트리스트가 기존과 1:1 동일함을 고정.
"""
from flask import request

from foms.services.as_dashboard_filters import (
    AsDashboardFilters,
    parse_as_dashboard_filters,
)


def _parse(app, query_string: str) -> AsDashboardFilters:
    with app.test_request_context(f"/erp/as?{query_string}"):
        return parse_as_dashboard_filters(request)


def test_defaults(app):
    f = _parse(app, "")
    assert f.status_filter == ""
    assert f.search_q == ""
    assert f.selected_date is None
    assert f.open_map is False
    assert f.tab == "incomplete"


def test_status_filter(app):
    assert _parse(app, "status=AS").status_filter == "AS"
    assert _parse(app, "status=AS_COMPLETED").status_filter == "AS_COMPLETED"


def test_search_query_aliases(app):
    assert _parse(app, "q=foo").search_q == "foo"
    assert _parse(app, "search=bar").search_q == "bar"
    assert _parse(app, "manager=kim").search_q == "kim"


def test_selected_date_raw_or_none(app):
    assert _parse(app, "date=2026-07-01").selected_date == "2026-07-01"
    assert _parse(app, "").selected_date is None


def test_open_map_flag(app):
    assert _parse(app, "open_map=1").open_map is True
    assert _parse(app, "").open_map is False
    assert _parse(app, "open_map=0").open_map is False


def test_tab_whitelist(app):
    assert _parse(app, "tab=incomplete").tab == "incomplete"
    assert _parse(app, "tab=completed").tab == "completed"
    assert _parse(app, "tab=sales_delivery").tab == "sales_delivery"
    assert _parse(app, "tab=bogus").tab == "incomplete"
    assert _parse(app, "").tab == "incomplete"
