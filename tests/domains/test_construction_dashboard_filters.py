"""construction dashboard request 파서 동작 보존 회귀 (Batch 4 구조-추출)."""
from flask import request

from foms.services.construction_dashboard_filters import (
    ConstructionDashboardFilters,
    parse_construction_dashboard_filters,
)


class _User:
    def __init__(self, team=None):
        self.team = team


def _parse(app, query_string: str, user=None) -> ConstructionDashboardFilters:
    with app.test_request_context(f"/erp/construction/dashboard?{query_string}"):
        return parse_construction_dashboard_filters(request, user)


def test_defaults(app):
    f = _parse(app, "")
    assert f.stage == ""
    assert f.q == ""
    assert f.focus_order_id is None
    assert not f.is_construction
    assert f.mine_only is False


def test_stage_and_focus(app):
    f = _parse(app, "stage=CONSTRUCTION&focus_order=42")
    assert f.stage == "CONSTRUCTION"
    assert f.focus_order_id == 42
    assert _parse(app, "focus_order=abc").focus_order_id is None


def test_search_aliases(app):
    assert _parse(app, "q=foo").q == "foo"
    assert _parse(app, "search=bar").q == "bar"


def test_is_construction_by_team(app):
    assert _parse(app, "", user=_User("CONSTRUCTION")).is_construction is True
    assert _parse(app, "", user=_User("SALES")).is_construction is False
    assert not _parse(app, "", user=None).is_construction


def test_mine_only(app):
    assert _parse(app, "", user=_User("CONSTRUCTION")).mine_only is True
    assert _parse(app, "", user=_User("SALES")).mine_only is False
    assert _parse(app, "", user=None).mine_only is False
