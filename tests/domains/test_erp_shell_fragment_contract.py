"""EPT-B1/B2/B3/B4: ERP shell contract, PRIMARY_NAV vs FRAGMENT_READY, dual-mode + tier header."""

from __future__ import annotations

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, User

from foms.services.common import erp_navigation_contract as enc
from foms.services.common import erp_shell_http as esh


@pytest.fixture(autouse=True)
def _reset_dashboard_cache_runtime():
    from foms.services.common import dashboard_cache as dc

    dc.reset_dashboard_cache_runtime_for_tests()
    yield
    dc.reset_dashboard_cache_runtime_for_tests()


def _login_erp_admin(client):
    user = User(
        username="ept_b1_contract_admin",
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="EPT B1 Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role

    return user


def test_contract_constants_and_paths_frozen():
    """Header/view/tab mapping must match SPEC (single source of truth)."""
    assert enc.MICRO_CACHE_READ_SLICES_RETAINED is True
    assert enc.ERP_SHELL_REQUEST_HEADER == "X-FOMS-ERP-SHELL"
    assert enc.ERP_SHELL_REQUEST_HEADER_ACTIVE == "1"
    assert enc.ERP_VIEW_QUERY_PARAM == "view"
    assert enc.VIEW_FRAGMENT == "fragment"
    assert enc.VIEW_CRITICAL == "critical"
    assert enc.VIEW_HEAVY == "heavy"
    assert enc.ERP_FRAGMENT_RESPONSE_HEADER == "X-FOMS-ERP-FRAGMENT"
    assert enc.ERP_FRAGMENT_RESPONSE_ACTIVE == "1"
    assert enc.ERP_FRAGMENT_VIEW_TIER_HEADER == "X-FOMS-ERP-FRAGMENT-TIER"
    assert enc.ERP_CANONICAL_TAB_PATHS is enc.ERP_FRAGMENT_READY_PATHS
    assert enc.ERP_CANONICAL_TAB_PATHS == (
        "/erp/dashboard",
        "/erp/measurement",
        "/erp/drawing-workbench",
        "/erp/production/dashboard",
        "/erp/shipment",
        "/erp/as",
        "/erp/construction/dashboard",
        "/erp/completion",
        "/erp/history/",
    )
    assert len(enc.ERP_PRIMARY_NAV_PATHS) == 9
    assert len(enc.ERP_FRAGMENT_READY_PATHS) == 9
    assert enc.ERP_FRAGMENT_READY_PATHS == enc.ERP_PRIMARY_NAV_PATHS
    assert frozenset(enc.ERP_FRAGMENT_READY_PATHS) <= frozenset(enc.ERP_PRIMARY_NAV_PATHS)
    not_yet_fragment = frozenset(enc.ERP_PRIMARY_NAV_PATHS) - frozenset(
        enc.ERP_FRAGMENT_READY_PATHS
    )
    assert len(not_yet_fragment) == 0
    assert len(enc.ERP_TAB_IDS) == len(enc.ERP_CANONICAL_TAB_PATHS)
    for path in enc.ERP_CANONICAL_TAB_PATHS:
        assert path in enc.ERP_PATH_TO_TAB_ID


def test_get_erp_shell_view_mode_from_request(app):
    """Shell header + view=critical|heavy|fragment; omit shell or view → None."""
    with app.test_request_context(
        "/erp/dashboard?view=fragment",
        headers={"X-FOMS-ERP-SHELL": "1"},
    ):
        from flask import request

        assert esh.get_erp_shell_view_mode(request) == enc.VIEW_FRAGMENT
        assert esh.wants_erp_shell_tab_body(request) is True

    with app.test_request_context(
        "/erp/dashboard?view=critical",
        headers={"X-FOMS-ERP-SHELL": "1"},
    ):
        from flask import request

        assert esh.get_erp_shell_view_mode(request) == enc.VIEW_CRITICAL

    with app.test_request_context("/erp/dashboard?view=fragment"):
        from flask import request

        assert esh.get_erp_shell_view_mode(request) is None

    with app.test_request_context(
        "/erp/dashboard",
        headers={"X-FOMS-ERP-SHELL": "1"},
    ):
        from flask import request

        assert esh.get_erp_shell_view_mode(request) is None


def test_normalize_query_fingerprint_stable():
    from werkzeug.datastructures import MultiDict

    m = MultiDict([("b", "2"), ("a", "1")])
    assert enc.normalize_erp_query_for_cache_fingerprint(m) == "a=1&b=2"


def test_canonical_erp_routes_registered(app):
    rules = {str(r.rule) for r in app.url_map.iter_rules()}
    for path in enc.ERP_CANONICAL_TAB_PATHS:
        assert path in rules, f"missing route: {path}"


def test_primary_nav_routes_registered(app):
    """B1 잠금판 9 primary는 app.url_map에 등록되어 있어야 한다."""
    rules = {str(r.rule) for r in app.url_map.iter_rules()}
    for path in enc.ERP_PRIMARY_NAV_PATHS:
        assert path in rules, f"missing primary route: {path}"


@pytest.mark.parametrize("view_mode", ["critical", "heavy"])
def test_orders_dashboard_critical_heavy_matches_fragment_body_tier_header(
    client, monkeypatch, view_mode,
):
    """B3: critical/heavy use same partial as fragment; tier header differs."""
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("FOMS_DASHBOARD_MICRO_CACHE_ENABLED", "1")
    _login_erp_admin(client)

    base = client.get(
        "/erp/dashboard?view=fragment",
        headers={"X-FOMS-ERP-SHELL": "1"},
    )
    alt = client.get(
        f"/erp/dashboard?view={view_mode}",
        headers={"X-FOMS-ERP-SHELL": "1"},
    )
    assert base.status_code == 200
    assert alt.status_code == 200
    assert base.data == alt.data
    assert base.headers.get("X-FOMS-ERP-FRAGMENT-TIER") == enc.VIEW_FRAGMENT
    assert alt.headers.get("X-FOMS-ERP-FRAGMENT-TIER") == view_mode


def test_view_fragment_without_shell_returns_full_document(client, monkeypatch):
    """JS-off / direct: view=fragment alone must not strip document shell."""
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("FOMS_DASHBOARD_MICRO_CACHE_ENABLED", "1")
    _login_erp_admin(client)

    response = client.get("/erp/dashboard?view=fragment")
    assert response.status_code == 200
    assert response.headers.get("X-FOMS-ERP-FRAGMENT") != "1"
    assert b"<!DOCTYPE" in response.data[:120] or response.data.strip().startswith(b"<!")


def test_orders_dashboard_fragment_returns_fragment_header(client, monkeypatch):
    """Shell fragment fetch returns body slice + X-FOMS-ERP-FRAGMENT (EPT-B2+ orders)."""
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("FOMS_DASHBOARD_MICRO_CACHE_ENABLED", "1")
    _login_erp_admin(client)

    response = client.get(
        "/erp/dashboard?view=fragment",
        headers={
            "X-FOMS-ERP-SHELL": "1",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("X-FOMS-ERP-FRAGMENT") == "1"
    data = response.data
    assert b"<!DOCTYPE" not in data[:80]
    assert b"erp-dashboard" in data


@pytest.mark.parametrize(
    "path,needle",
    [
        ("/erp/measurement", b"erp-measurement-dashboard"),
        ("/erp/shipment", b"erp-mobile-shell"),
        ("/erp/as", b"erp-as"),
        ("/erp/drawing-workbench", b"dw-process-map"),
        ("/erp/production/dashboard", b"erp-dashboard"),
        ("/erp/construction/dashboard", b"erp-dashboard"),
        ("/erp/completion", b"erp-completion"),
        ("/erp/history/", b"history-chevron"),
    ],
)
def test_other_erp_tab_fragments_return_fragment_header(client, monkeypatch, path, needle):
    """Measurement/shipment/AS fragment mode returns HTML slice + fragment header (EPT-B3+)."""
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("FOMS_DASHBOARD_MICRO_CACHE_ENABLED", "1")
    _login_erp_admin(client)

    response = client.get(
        f"{path}?view=fragment",
        headers={"X-FOMS-ERP-SHELL": "1"},
    )
    assert response.status_code == 200
    assert response.headers.get("X-FOMS-ERP-FRAGMENT") == "1"
    data = response.data
    assert b"<!DOCTYPE" not in data[:80]
    assert needle in data


@pytest.mark.parametrize(
    "path",
    [
        "/erp/drawing-workbench",
        "/erp/production/dashboard",
        "/erp/construction/dashboard",
        "/erp/completion",
        "/erp/history/",
    ],
)
@pytest.mark.parametrize("view_mode", ["critical", "heavy"])
def test_secondary_primary_critical_heavy_matches_fragment_body_tier_header(
    client, monkeypatch, path, view_mode,
):
    """EPT-B4: secondary primaries use same partial as fragment; tier header differs."""
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("FOMS_DASHBOARD_MICRO_CACHE_ENABLED", "1")
    _login_erp_admin(client)

    base = client.get(f"{path}?view=fragment", headers={"X-FOMS-ERP-SHELL": "1"})
    alt = client.get(f"{path}?view={view_mode}", headers={"X-FOMS-ERP-SHELL": "1"})
    assert base.status_code == 200
    assert alt.status_code == 200
    assert base.data == alt.data
    assert base.headers.get("X-FOMS-ERP-FRAGMENT-TIER") == enc.VIEW_FRAGMENT
    assert alt.headers.get("X-FOMS-ERP-FRAGMENT-TIER") == view_mode


@pytest.mark.parametrize(
    "path",
    [
        "/erp/drawing-workbench",
        "/erp/history/",
    ],
)
def test_view_fragment_without_shell_returns_full_document_secondary(client, monkeypatch, path):
    """JS-off: view=fragment without shell header must not strip document shell."""
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("FOMS_DASHBOARD_MICRO_CACHE_ENABLED", "1")
    _login_erp_admin(client)

    response = client.get(f"{path}?view=fragment")
    assert response.status_code == 200
    assert response.headers.get("X-FOMS-ERP-FRAGMENT") != "1"
    assert b"<!DOCTYPE" in response.data[:120] or response.data.strip().startswith(b"<!")


def test_canonical_erp_paths_return_200_when_authenticated(client, monkeypatch):
    """Full document GET without shell header: existing behavior preserved."""
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("FOMS_DASHBOARD_MICRO_CACHE_ENABLED", "1")
    _login_erp_admin(client)

    for path in enc.ERP_CANONICAL_TAB_PATHS:
        response = client.get(path)
        assert response.status_code == 200, f"{path} -> {response.status_code}"
        assert b"html" in response.data.lower() or response.data.strip().startswith(b"<!")


def _seed_minimal_erp_order_drawing_workbench():
    """Minimal ERP Order order for drawing workbench detail (in-memory tests)."""
    o = Order(
        received_date="2026-01-01",
        customer_name="C",
        phone="01000000000",
        address="Addr",
        product="P",
        is_erp_order=True,
        structured_data={
            "workflow": {"stage": "DRAWING"},
            "drawing": {"status": "PENDING"},
            "parties": {
                "customer": {"name": "C"},
                "manager": {"name": "M"},
            },
            "drawing_current_files": [],
            "drawing_transfer_history": [],
        },
    )
    db_session.add(o)
    db_session.commit()
    return o.id


def _seed_minimal_order_for_edit():
    """Minimal ERP Order order for edit page GET fragment contract checks."""
    o = Order(
        received_date="2026-01-01",
        customer_name="C",
        phone="01000000000",
        address="Addr",
        product="P",
        is_erp_order=True,
        structured_data={},
    )
    db_session.add(o)
    db_session.commit()
    return o.id


def test_ept_b5_legacy_erp_order_redirect_to_edit_erp_order(client, monkeypatch):
    """GET /erp/orders/<id> → 302 to /edit/<id> with open=erp-order."""
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("FOMS_DASHBOARD_MICRO_CACHE_ENABLED", "1")
    _login_erp_admin(client)
    oid = _seed_minimal_erp_order_drawing_workbench()
    resp = client.get(f"/erp/orders/{oid}", follow_redirects=False)
    assert resp.status_code == 302
    loc = resp.headers.get("Location", "")
    assert f"/edit/{oid}" in loc.replace("\\", "/")
    assert "erp-order" in loc


def test_ept_b5_legacy_erp_order_redirect_preserves_query_context(client, monkeypatch):
    """Legacy redirect should keep focus/category context while forcing open=erp-order."""
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("FOMS_DASHBOARD_MICRO_CACHE_ENABLED", "1")
    _login_erp_admin(client)
    oid = _seed_minimal_erp_order_drawing_workbench()

    resp = client.get(
        f"/erp/orders/{oid}?focus=attachments&category=drawing",
        follow_redirects=False,
    )

    assert resp.status_code == 302
    loc = resp.headers.get("Location", "")
    normalized = loc.replace("\\", "/")
    assert f"/edit/{oid}" in normalized
    assert "open=erp-order" in normalized
    assert "focus=attachments" in normalized
    assert "category=drawing" in normalized


def test_ept_b5_drawing_workbench_detail_shell_fragment_contract(client, monkeypatch):
    """EPT-B5: subordinate detail returns fragment slice + headers when shell+view."""
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("FOMS_DASHBOARD_MICRO_CACHE_ENABLED", "1")
    _login_erp_admin(client)
    oid = _seed_minimal_erp_order_drawing_workbench()
    response = client.get(
        f"/erp/drawing-workbench/{oid}?view=fragment",
        headers={"X-FOMS-ERP-SHELL": "1"},
    )
    assert response.status_code == 200
    assert response.headers.get("X-FOMS-ERP-FRAGMENT") == "1"
    assert response.headers.get("X-FOMS-ERP-FRAGMENT-TIER") == enc.VIEW_FRAGMENT
    data = response.data
    assert b"<!DOCTYPE" not in data[:120]
    assert b"erp-pro" in data


@pytest.mark.parametrize("view_mode", ["critical", "heavy"])
def test_ept_b5_drawing_workbench_detail_tier_body_parity(client, monkeypatch, view_mode):
    """EPT-B5: critical/heavy same body as fragment; tier header differs."""
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("FOMS_DASHBOARD_MICRO_CACHE_ENABLED", "1")
    _login_erp_admin(client)
    oid = _seed_minimal_erp_order_drawing_workbench()
    base = client.get(
        f"/erp/drawing-workbench/{oid}?view=fragment",
        headers={"X-FOMS-ERP-SHELL": "1"},
    )
    alt = client.get(
        f"/erp/drawing-workbench/{oid}?view={view_mode}",
        headers={"X-FOMS-ERP-SHELL": "1"},
    )
    assert base.status_code == 200
    assert alt.status_code == 200
    assert base.data == alt.data
    assert base.headers.get("X-FOMS-ERP-FRAGMENT-TIER") == enc.VIEW_FRAGMENT
    assert alt.headers.get("X-FOMS-ERP-FRAGMENT-TIER") == view_mode


def test_ept_b5_drawing_workbench_detail_view_fragment_without_shell_full_document(
    client, monkeypatch,
):
    """JS-off / direct: view=fragment without shell → full document, no fragment header."""
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("FOMS_DASHBOARD_MICRO_CACHE_ENABLED", "1")
    _login_erp_admin(client)
    oid = _seed_minimal_erp_order_drawing_workbench()
    response = client.get(f"/erp/drawing-workbench/{oid}?view=fragment")
    assert response.status_code == 200
    assert response.headers.get("X-FOMS-ERP-FRAGMENT") != "1"
    assert (
        b"<!DOCTYPE" in response.data[:200]
        or response.data.strip().startswith(b"<!")
    )


def test_ept_b5_edit_order_shell_fragment_contract(client, monkeypatch):
    """Edit surface is now full-document only even when shell/view params leak in."""
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("FOMS_DASHBOARD_MICRO_CACHE_ENABLED", "1")
    _login_erp_admin(client)
    oid = _seed_minimal_order_for_edit()
    response = client.get(
        f"/edit/{oid}?view=fragment&open=erp-order",
        headers={"X-FOMS-ERP-SHELL": "1"},
    )
    assert response.status_code == 200
    assert response.headers.get("X-FOMS-ERP-FRAGMENT") != "1"
    data = response.data
    assert b"<!DOCTYPE" in data[:200] or data.strip().startswith(b"<!")
    assert b"erp-order-config" in data
    assert b"js/orders/erp-order-shared.js" in data


@pytest.mark.parametrize("view_mode", ["critical", "heavy"])
def test_ept_b5_edit_order_tier_body_parity(client, monkeypatch, view_mode):
    """Edit surface ignores shell tiers and stays a full document for all view modes."""
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("FOMS_DASHBOARD_MICRO_CACHE_ENABLED", "1")
    _login_erp_admin(client)
    oid = _seed_minimal_order_for_edit()
    base = client.get(
        f"/edit/{oid}?view=fragment&open=erp-order",
        headers={"X-FOMS-ERP-SHELL": "1"},
    )
    alt = client.get(
        f"/edit/{oid}?view={view_mode}&open=erp-order",
        headers={"X-FOMS-ERP-SHELL": "1"},
    )
    assert base.status_code == 200
    assert alt.status_code == 200
    assert base.data == alt.data
    assert base.headers.get("X-FOMS-ERP-FRAGMENT") != "1"
    assert alt.headers.get("X-FOMS-ERP-FRAGMENT") != "1"
    assert b"<!DOCTYPE" in base.data[:200] or base.data.strip().startswith(b"<!")
    assert b"<!DOCTYPE" in alt.data[:200] or alt.data.strip().startswith(b"<!")


def test_ept_b5_edit_order_view_fragment_without_shell_full_document(client, monkeypatch):
    """view=fragment without shell on edit → full document (scripts block preserved on full page)."""
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("FOMS_DASHBOARD_MICRO_CACHE_ENABLED", "1")
    _login_erp_admin(client)
    oid = _seed_minimal_order_for_edit()
    response = client.get(f"/edit/{oid}?view=fragment")
    assert response.status_code == 200
    assert response.headers.get("X-FOMS-ERP-FRAGMENT") != "1"
    assert (
        b"<!DOCTYPE" in response.data[:200]
        or response.data.strip().startswith(b"<!")
    )


def test_ept_b5_shipment_settings_shell_fragment_contract(client, monkeypatch):
    """Tier C: /erp/shipment-settings dual-mode aligned with B3/B4."""
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("FOMS_DASHBOARD_MICRO_CACHE_ENABLED", "1")
    _login_erp_admin(client)
    response = client.get(
        "/erp/shipment-settings?view=fragment",
        headers={"X-FOMS-ERP-SHELL": "1"},
    )
    assert response.status_code == 200
    assert response.headers.get("X-FOMS-ERP-FRAGMENT") == "1"
    assert b"worker-settings-grid" in response.data


def test_ept_b5_map_view_full_document_no_shell_fragment_contract(client, monkeypatch):
    """Descendant /map_view: no apply_erp_shell_fragment_headers — not a fragment swap target."""
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("FOMS_DASHBOARD_MICRO_CACHE_ENABLED", "1")
    _login_erp_admin(client)
    response = client.get(
        "/map_view?view=fragment",
        headers={"X-FOMS-ERP-SHELL": "1"},
    )
    assert response.status_code == 200
    assert response.headers.get("X-FOMS-ERP-FRAGMENT") != "1"
