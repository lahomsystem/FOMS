"""P0-01: ERP mobile v2 cohort rollout — wiring and shell-bridge contracts."""

from __future__ import annotations

from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services import feature_flags
from foms.services.context_processors import inject_foms_flags, inject_status_list
from models import User

ROOT = Path(__file__).resolve().parents[2]

ERP_V2_PATHS = (
    "/erp/dashboard",
    "/erp/shipment",
    "/erp/drawing-workbench",
    "/erp/as",
    "/erp/construction/dashboard",
)


def _login_admin(client) -> User:
    user = User(
        username="p0_01_cohort_admin",
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="P0-01 Cohort Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def test_shell_bridge_css_imported_and_tablet_band_rules() -> None:
    """13-foms-shell-bridge.css must hide legacy global nav in the 768–991px band."""
    erp_pro = (ROOT / "static/css/foundation/erp-pro.css").read_text(encoding="utf-8")
    bridge = (ROOT / "static/css/foundation/erp-pro/13-foms-shell-bridge.css").read_text(
        encoding="utf-8"
    )
    assert "13-foms-shell-bridge.css" in erp_pro
    assert "max-width: 991.98px" in bridge
    assert "body.erp-mobile-v2-layout .layout-global-nav" in bridge
    assert "layout-global-nav--erp-v2-suppressed" in bridge
    assert "display: none !important" in bridge
    assert "min-width: 992px" in bridge


@pytest.mark.parametrize(
    ("mobile_v2", "cohort_raw", "user_id", "expected_mobile"),
    [
        ("false", "", 1, False),
        ("true", "", 1, False),
        ("true", "2", 1, False),
        ("true", "1", 1, True),
        ("true", "1,2", 2, True),
    ],
)
def test_cohort_flag_matrix(
    monkeypatch: pytest.MonkeyPatch,
    mobile_v2: str,
    cohort_raw: str,
    user_id: int,
    expected_mobile: bool,
) -> None:
    """Roadmap flag matrix: global flag on but empty/wrong cohort stays off."""
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", mobile_v2)
    if cohort_raw:
        monkeypatch.setenv("FOMS_V3_SHELL_COHORT", cohort_raw)
    else:
        monkeypatch.delenv("FOMS_V3_SHELL_COHORT", raising=False)
    assert (
        feature_flags.is_enabled_for_user(
            "ERP_MOBILE_V2_ENABLED",
            user_id,
            cohort_key="FOMS_V3_SHELL_COHORT",
        )
        is expected_mobile
    )


def test_inject_status_list_and_foms_flags_align_with_feature_flags(
    app, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Context processors must expose the same cohort gate as feature_flags."""
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "42")
    user = User(
        username="p0_01_ctx",
        password=generate_password_hash("x"),
        role="ADMIN",
        team="CS",
        name="Ctx",
        is_active=True,
    )
    user.id = 42

    with app.test_request_context("/erp/dashboard"):
        from flask import g

        g.current_user = user
        status_ctx = inject_status_list()
        flags_ctx = inject_foms_flags()

    assert status_ctx["erp_mobile_v2_enabled"] is True
    assert flags_ctx["flag_mobile_v2"] is True


@pytest.mark.parametrize("path", ERP_V2_PATHS)
def test_erp_routes_apply_mobile_shell_when_user_in_cohort(
    client, monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    """Cohort in: ERP routes render mobile shell markers and suppress global nav."""
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    user = _login_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))

    response = client.get(path)

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'class="erp-mobile-v2-layout"' in body
    assert "erp-mobile-shell" in body
    assert "layout-global-nav--erp-v2-suppressed" in body
    assert 'data-erp-v2-global-nav="suppressed"' in body


def test_erp_routes_legacy_shell_when_cohort_off(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cohort out: legacy global nav remains; mobile layout class absent."""
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    _login_admin(client)

    response = client.get("/erp/dashboard")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'class="erp-mobile-v2-layout"' not in body
    assert 'class="layout-global-nav navbar' in body
    assert "layout-global-nav--erp-v2-suppressed" not in body


@pytest.mark.parametrize("width", [320, 390, 768, 1024, 1280, 1920])
def test_layout_nav_suppression_markup_present_for_cohort_html_contract(
    width: int,
) -> None:
    """
    Roadmap viewport list — HTML carries suppression hooks for CSS bridge.

    Playwright baselines assert pixels; this asserts markup/CSS contracts exist.
    """
    nav = (ROOT / "templates/partials/shared/layout_nav.html").read_text(encoding="utf-8")
    layout = (ROOT / "templates/cs/layout.html").read_text(encoding="utf-8")
    assert "layout-global-nav--erp-v2-suppressed" in nav
    assert "d-none d-lg-block" in nav
    assert "erp-mobile-v2-layout" in layout
    del width  # documented breakpoint list for roadmap traceability
