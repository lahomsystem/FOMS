"""Mobile v3 shell contract — variant gating, asset exclusivity, persona homes.

Locks the two-layer gate (v2 cohort → v3 cohort → ``foms_shell_pref`` cookie)
resolved by :func:`foms.services.feature_flags.resolve_shell_variant` down to the
rendered HTML surface. Reuses the ``client``/``monkeypatch`` fixtures and the
env-cohort login pattern from ``test_p0_01_erp_mobile_v2_cohort.py`` — no new
heavy fixtures.

Stable markers (chosen by reading the templates):
  - v3 shell        : ``data-foms-app-shell-v3`` / ``fos-shell-v3``
                      (templates/partials/v3/foms_app_shell_v3.html)
  - v2 critical CSS : ``id="foms-mobile-v2-critical-css"`` (layout_head.html, v2 gate)
  - v3 CSS link     : ``css/v3/foms-mobile-v3.css``
  - v3 shell JS     : ``js/v3/foms-mobile-v3.js``
  - v3 toggle JS    : ``js/v3/foms-shell-toggle.js`` (v3-eligible only)
  - drawer entry    : ``data-foms-shell-toggle="v3"`` (v2 shell + v3-eligible)
"""

from __future__ import annotations

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from models import User

# --- Rendered-surface markers (SSOT for this contract) ---------------------
V3_SHELL_MARKER = "data-foms-app-shell-v3"
V3_SHELL_CLASS = "fos-shell-v3"
V2_CRITICAL_CSS = 'id="foms-mobile-v2-critical-css"'
V3_CSS_LINK = "css/v3/foms-mobile-v3.css"
V3_SHELL_JS = "js/v3/foms-mobile-v3.js"
V3_TOGGLE_JS = "js/v3/foms-shell-toggle.js"
DRAWER_V3_ENTRY = 'data-foms-shell-toggle="v3"'

# 6 domain routes → the persona-home marker that route injects into the v3 slot.
# Paths verified against blueprint url_for targets (erp_construction uses the
# canonical ``/dashboard`` suffix; the ADMIN test user bypasses the team redirect).
PERSONA_ROUTE_MARKERS = [
    ("/erp/dashboard", 'data-persona-home="cs"'),
    ("/erp/measurement", 'data-persona-home="sales"'),
    ("/erp/drawing-workbench", 'data-seg-panel="delivered"'),
    ("/erp/production/dashboard", 'data-persona-home="production"'),
    ("/erp/construction/dashboard", 'data-foms-persona-home="construction"'),
    ("/erp/shipment", "px-shipment-herounit"),
]


def _login_admin(client, username: str = "shell_v3_admin") -> User:
    """Create an ADMIN (team=CS) user and seed a logged-in session.

    ADMIN team lets construction/other domain routes render without hitting the
    CONSTRUCTION-team redirect. Mirrors the P0-01 cohort test login helper.
    """
    user = User(
        username=username,
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="Shell v3 Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _enable_v3(monkeypatch, user_id, cohort_value: str | None = None) -> None:
    """Grant full v3 eligibility (both v2 + v3 cohorts) for ``user_id``.

    ``cohort_value`` defaults to the explicit user id; pass ``"all"`` to exercise
    the all-rollout sentinel. No cookie set → variant resolves to the default v3.
    """
    value = cohort_value if cohort_value is not None else str(user_id)
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", value)
    monkeypatch.setenv("FOMS_SHELL_V3_ENABLED", "true")
    monkeypatch.setenv("FOMS_SHELL_V3_COHORT", value)


def _enable_v2_only(monkeypatch, user_id) -> None:
    """Grant v2 cohort but leave the v3 gate off → variant resolves to ``v2``."""
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user_id))
    monkeypatch.delenv("FOMS_SHELL_V3_ENABLED", raising=False)
    monkeypatch.delenv("FOMS_SHELL_V3_COHORT", raising=False)


def _enable_legacy(monkeypatch) -> None:
    """Global flag on but the user is outside every cohort → variant ``legacy``."""
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "9999999")
    monkeypatch.delenv("FOMS_SHELL_V3_ENABLED", raising=False)
    monkeypatch.delenv("FOMS_SHELL_V3_COHORT", raising=False)


@pytest.mark.parametrize("cohort_value", [None, "all"])
def test_v3_eligible_user_gets_v3_shell_and_no_v2_critical_css(
    client, monkeypatch, cohort_value
) -> None:
    """v3-eligible (both cohorts / all-sentinel), no cookie → v3 shell renders.

    Contract 1: v3 shell marker present, v2 mobile critical CSS absent, v3 CSS
    link present.
    """
    user = _login_admin(client)
    _enable_v3(monkeypatch, user.id, cohort_value)

    response = client.get("/erp/dashboard")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert V3_SHELL_MARKER in body
    assert V3_SHELL_CLASS in body
    assert V2_CRITICAL_CSS not in body
    assert V3_CSS_LINK in body


def test_v3_eligible_with_v2_cookie_returns_v2_shell_with_drawer_entry(
    client, monkeypatch
) -> None:
    """Same eligible user + ``foms_shell_pref=v2`` cookie → v2 shell (not v3).

    Contract 2: v2 critical CSS present, v3 CSS absent, drawer v3 entry point
    present (v2-shell escape hatch back to v3 for eligible users).
    """
    user = _login_admin(client)
    _enable_v3(monkeypatch, user.id)
    # Test-client cookie jar (not a raw Cookie header) drives request.cookies.
    client.set_cookie("foms_shell_pref", "v2")

    response = client.get("/erp/dashboard")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert V2_CRITICAL_CSS in body
    assert V3_CSS_LINK not in body
    assert DRAWER_V3_ENTRY in body
    assert V3_SHELL_MARKER not in body


def test_v2_only_user_has_no_v3_assets_or_toggle(client, monkeypatch) -> None:
    """v2 cohort only (outside v3 cohort) → zero v3 assets, no toggle/drawer entry.

    Contract 3: v3 CSS/shell/toggle JS absent, drawer v3 entry absent, v3 shell
    marker absent. Sanity: v2 critical CSS present confirms v2 (not legacy).
    """
    user = _login_admin(client)
    _enable_v2_only(monkeypatch, user.id)

    response = client.get("/erp/dashboard")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert V2_CRITICAL_CSS in body
    assert V3_CSS_LINK not in body
    assert V3_SHELL_JS not in body
    assert V3_TOGGLE_JS not in body
    assert DRAWER_V3_ENTRY not in body
    assert V3_SHELL_MARKER not in body


def test_legacy_user_has_neither_v2_nor_v3_shell_assets(client, monkeypatch) -> None:
    """Outside every cohort → legacy shell: both v2 and v3 assets absent.

    Contract 4: no v2 critical CSS, no v3 CSS/shell/toggle JS, no v3 shell marker.
    """
    _login_admin(client)
    _enable_legacy(monkeypatch)

    response = client.get("/erp/dashboard")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert V2_CRITICAL_CSS not in body
    assert V3_CSS_LINK not in body
    assert V3_SHELL_JS not in body
    assert V3_TOGGLE_JS not in body
    assert V3_SHELL_MARKER not in body


@pytest.mark.parametrize(("path", "marker"), PERSONA_ROUTE_MARKERS)
def test_v3_domain_routes_render_persona_home(
    client, monkeypatch, path, marker
) -> None:
    """Each of the 6 domain routes renders 200 + its persona-home marker in v3.

    Contract 5: the route-specific ``fos_content_partial`` (persona home) renders
    inside the shared v3 shell for an eligible user.
    """
    user = _login_admin(client)
    _enable_v3(monkeypatch, user.id)

    response = client.get(path)

    assert response.status_code == 200, f"{path} -> {response.status_code}"
    body = response.get_data(as_text=True)
    assert V3_SHELL_MARKER in body, f"{path} missing v3 shell"
    assert marker in body, f"{path} missing persona marker {marker!r}"


def test_v3_fragment_tab_swap_returns_persona_shell_slice(client, monkeypatch) -> None:
    """v3 user fragment fetch (shell header + view=fragment) → 200 slice, no doc.

    Contract 6: the fragment tab-body path is not broken for v3 — it returns the
    v3 persona shell as a headerless slice with the fragment response header.
    """
    user = _login_admin(client)
    _enable_v3(monkeypatch, user.id)

    response = client.get(
        "/erp/dashboard?view=fragment",
        headers={"X-FOMS-ERP-SHELL": "1"},
    )

    assert response.status_code == 200
    assert response.headers.get("X-FOMS-ERP-FRAGMENT") == "1"
    data = response.get_data()
    assert b"<!DOCTYPE" not in data[:80]
    assert V3_SHELL_MARKER.encode() in data
