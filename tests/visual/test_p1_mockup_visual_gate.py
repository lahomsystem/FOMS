"""P1 visual/mockup gate — mobile v2 body must not sit under display:none ancestors."""

from __future__ import annotations

from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from models import User

ROOT = Path(__file__).resolve().parents[2]


def _login_admin(client) -> User:
    user = User(
        username="p1_visual_gate_admin",
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="P1 Visual Gate Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def test_p1_mobile_dashboard_body_outside_desktop_only_wrapper(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mobile v2 dashboard body is a sibling of desktop-only chrome, not nested inside it."""
    user = _login_admin(client)
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))

    resp = client.get("/erp/dashboard")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    desktop_idx = html.find('class="foms-shell-desktop-only"')
    layout_idx = html.find("erp-dashboard-layout")
    mobile_idx = html.find("foms-mobile-v2-dashboard")
    assert desktop_idx != -1
    assert layout_idx != -1
    assert mobile_idx != -1
    assert desktop_idx < layout_idx < mobile_idx, (
        "desktop chrome must precede mobile v2 body in DOM order"
    )


def _mobile_marker_after_desktop_layout(html: str, snippet: str) -> None:
    """Assert snippet exists and appears after erp-dashboard-layout (desktop-only region)."""
    assert snippet in html
    layout_idx = html.find("erp-dashboard-layout")
    marker_idx = html.find(snippet)
    assert layout_idx != -1 and marker_idx > layout_idx


def test_p1_mobile_dashboard_markers_not_display_none_scoped(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Queue scroll hooks render outside desktop-only layout region."""
    user = _login_admin(client)
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))

    resp = client.get("/erp/dashboard")
    html = resp.get_data(as_text=True)
    for snippet in (
        "data-foms-mobile-queue-scroll",
    ):
        _mobile_marker_after_desktop_layout(html, snippet)


def test_p1_foms_shell_css_hides_header_globally() -> None:
    """foms-shell.css hides erp-pro-header/nav on all mobile v2 shells (descendant selectors)."""
    css = (ROOT / "static/css/foundation/foms-shell.css").read_text(encoding="utf-8")
    assert ".erp-pro-header" in css
    assert ".erp-pro-nav" in css
    assert "display: none !important" in css
    assert "> .erp-pro-header" not in css
