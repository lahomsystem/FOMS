"""Tests for ERP global mine-only filter (URL + cookie SSOT)."""

from __future__ import annotations

from flask import request


def test_mine_from_url_param(app):
    from foms.services.common.erp_mine_filter import erp_mine_only_from_request

    with app.test_request_context("/erp/production/dashboard?mine=1"):
        assert erp_mine_only_from_request(request) is True


def test_mine_from_cookie_when_url_omits_mine(app):
    from foms.services.common.erp_mine_filter import erp_mine_only_from_request

    with app.test_request_context(
        "/erp/measurement",
        headers={"Cookie": "erp_mine_only=1"},
    ):
        assert erp_mine_only_from_request(request) is True


def test_explicit_mine_off_overrides_cookie(app):
    from foms.services.common.erp_mine_filter import erp_mine_only_from_request

    with app.test_request_context(
        "/erp/measurement?mine=",
        headers={"Cookie": "erp_mine_only=1"},
    ):
        assert erp_mine_only_from_request(request) is False


def test_tower_mine_from_cookie(app):
    from foms.services.common.erp_mine_filter import erp_tower_mine_from_request

    with app.test_request_context(
        "/erp/dashboard",
        headers={"Cookie": "erp_mine_only=1"},
    ):
        assert erp_tower_mine_from_request(request) is True


def test_tower_mine_explicit_off_overrides_cookie(app):
    from foms.services.common.erp_mine_filter import erp_tower_mine_from_request

    with app.test_request_context(
        "/erp/dashboard?tower_mine=",
        headers={"Cookie": "erp_mine_only=1"},
    ):
        assert erp_tower_mine_from_request(request) is False


def test_construction_team_forced_mine_only(app):
    from foms.services.common.erp_mine_filter import erp_mine_only_for_construction

    class _User:
        team = "CONSTRUCTION"

    with app.test_request_context("/erp/construction/dashboard"):
        assert erp_mine_only_for_construction(request, _User()) is True
