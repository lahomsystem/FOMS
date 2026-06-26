"""orders dashboard request 파서(parse_orders_dashboard_filters) 동작 보존 회귀.

Batch 2a 구조-추출: 라우트에서 분리한 파싱·정규화 규칙이 기존과 1:1 동일함을 고정한다.
- 레거시 MEASURED -> MEASURE
- sort 화이트리스트(그 외 latest)
- date ISO 유효성(실패 시 무시)
- risk 키 화이트리스트(밖이면 무시)
- focus_order int(실패 시 None)
- effective_stage = '' if q else stage
"""
from flask import request

from foms.services.orders.dashboard_filters import (
    OrdersDashboardFilters,
    parse_orders_dashboard_filters,
)


def _parse(app, query_string: str) -> OrdersDashboardFilters:
    with app.test_request_context(f"/erp/dashboard?{query_string}"):
        return parse_orders_dashboard_filters(request)


def test_defaults_empty_args(app):
    f = _parse(app, "")
    assert f.stage == ""
    assert f.urgent == ""
    assert f.has_alert == ""
    assert f.alert_type == ""
    assert f.q == ""
    assert f.effective_stage == ""
    assert f.team == ""
    assert f.sort == "latest"
    assert f.today == ""
    assert f.tower_mine is False
    assert f.mine is False
    assert f.date == ""
    assert f.field == ""
    assert f.risk == ""
    assert f.focus_order_id is None


def test_legacy_measured_normalized(app):
    assert _parse(app, "stage=MEASURED").stage == "MEASURE"
    assert _parse(app, "stage=MEASURE").stage == "MEASURE"
    assert _parse(app, "stage=DRAWING").stage == "DRAWING"


def test_effective_stage_cleared_by_query(app):
    f = _parse(app, "stage=MEASURE&q=hello")
    assert f.q == "hello"
    assert f.stage == "MEASURE"
    assert f.effective_stage == ""  # q가 있으면 stage 필터 무력화


def test_effective_stage_kept_without_query(app):
    f = _parse(app, "stage=CONSTRUCTION")
    assert f.effective_stage == "CONSTRUCTION"


def test_sort_whitelist(app):
    assert _parse(app, "sort=amount").sort == "amount"
    assert _parse(app, "sort=schedule").sort == "schedule"
    assert _parse(app, "sort=latest").sort == "latest"
    assert _parse(app, "sort=bogus").sort == "latest"
    assert _parse(app, "").sort == "latest"


def test_date_iso_validation(app):
    assert _parse(app, "date=2026-06-26").date == "2026-06-26"
    assert _parse(app, "date=not-a-date").date == ""
    assert _parse(app, "date=2026-13-99").date == ""


def test_risk_whitelist(app):
    assert _parse(app, "risk=balance_due").risk == "balance_due"
    assert _parse(app, "risk=construction_unready").risk == "construction_unready"
    assert _parse(app, "risk=measure_unassigned").risk == "measure_unassigned"
    assert _parse(app, "risk=drawing_stalled").risk == "drawing_stalled"
    assert _parse(app, "risk=bogus").risk == ""


def test_focus_order_int_parsing(app):
    assert _parse(app, "focus_order=123").focus_order_id == 123
    assert _parse(app, "focus_order=abc").focus_order_id is None
    assert _parse(app, "").focus_order_id is None


def test_mine_flag(app):
    assert _parse(app, "mine=1").mine is True
    assert _parse(app, "").mine is False


def test_search_alias_q_or_search(app):
    # get_search_query_arg('q', 'search') 동작 보존
    assert _parse(app, "q=foo").q == "foo"
    assert _parse(app, "search=bar").q == "bar"


def test_passthrough_simple_args(app):
    f = _parse(app, "team=SALES&urgent=1&has_alert=1&alert_type=measurement_d4&today=1&field=measure")
    assert f.team == "SALES"
    assert f.urgent == "1"
    assert f.has_alert == "1"
    assert f.alert_type == "measurement_d4"
    assert f.today == "1"
    assert f.field == "measure"
