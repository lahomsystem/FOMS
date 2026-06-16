"""P3 completion gate — bottom nav HTMX, history search-first, swipe API, lightbox."""

from __future__ import annotations

from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

ROOT = Path(__file__).resolve().parents[2]


def test_p3_01_bottom_nav_shell_assets() -> None:
    nav = (ROOT / "templates/partials/shared/erp_mobile_bottom_nav.html").read_text(encoding="utf-8")
    assert "data-foms-nav-id" in nav
    js = (ROOT / "static/js/foms/bottom-nav-shell.js").read_text(encoding="utf-8")
    assert "foms:erp-shell-fragment-swapped" in js
    assert "navigateBottomNavHtmx" in js
    shell = (ROOT / "templates/partials/shared/foms_app_shell.html").read_text(encoding="utf-8")
    assert "data-bottom-nav-htmx" in shell
    bundle = (ROOT / "templates/partials/shared/foms_p2_surface_bundle.html").read_text(encoding="utf-8")
    assert "bottom-nav-shell.js" in bundle


def test_p3_01_bottom_nav_htmx_flag_default_off(monkeypatch: pytest.MonkeyPatch) -> None:
    from foms.services.feature_flags import env_bool

    monkeypatch.delenv("FOMS_BOTTOM_NAV_HTMX_ENABLED", raising=False)
    assert env_bool("FOMS_BOTTOM_NAV_HTMX_ENABLED") is False


def test_p3_02_history_search_first_mobile() -> None:
    body = (ROOT / "templates/orders/partials/history_dashboard_body.html").read_text(encoding="utf-8")
    filters = (ROOT / "templates/orders/partials/history_mobile_filters.html").read_text(encoding="utf-8")
    filter_bar_css = (ROOT / "static/css/components/foms-mobile-filter-bar.css").read_text(encoding="utf-8")
    assert 'id="erp-history-search-q"' in filters
    assert "history_mobile_filters.html" in body
    assert "position: sticky" in filter_bar_css
    assert "js/foms/history-mobile.js" in body
    js = (ROOT / "static/js/foms/history-mobile.js").read_text(encoding="utf-8")
    assert "erp-history-search-q" in js
    assert "erp-history-mobile-empty" in js


def test_p3_03_queue_swipe_action_api(client, app) -> None:
    from db import db_session
    from models import Order, User

    with app.app_context():
        user = User(
            username="p3_swipe_admin",
            password=generate_password_hash("pass"),
            role="ADMIN",
            name="Swipe",
        )
        db_session.add(user)
        order = Order(
            received_date="2026-05-30",
            customer_name="SwipeTest",
            phone="010",
            address="Seoul",
            product="P",
        )
        db_session.add(order)
        db_session.commit()
        oid = order.id
        uid = user.id

    with client.session_transaction() as sess:
        sess["user_id"] = uid

    hold = client.post(f"/api/foms/queue/{oid}/action", json={"action": "hold"})
    assert hold.status_code == 200
    assert hold.get_json()["success"] is True
    assert hold.get_json()["data"]["new_status"] == "ON_HOLD"

    with app.app_context():
        refreshed = db_session.query(Order).filter(Order.id == oid).first()
        assert refreshed is not None
        assert refreshed.status == "ON_HOLD"

    approve = client.post(f"/api/foms/queue/{oid}/action", json={"action": "approve"})
    assert approve.status_code == 400
    assert approve.get_json()["success"] is False

    bad = client.post(f"/api/foms/queue/{oid}/action", json={"action": "invalid"})
    assert bad.status_code == 400


def test_p3_04_swipe_js_calls_api() -> None:
    js = (ROOT / "static/js/foms/swipe-actions.js").read_text(encoding="utf-8")
    assert "/api/foms/queue/" in js
    card = (ROOT / "templates/partials/shared/erp_mobile_queue_card.html").read_text(encoding="utf-8")
    assert "data-order-id" in card


def test_p3_05_history_lightbox_gallery() -> None:
    detail = (ROOT / "templates/orders/partials/history_detail_content.html").read_text(encoding="utf-8")
    assert "data-foms-lightbox-gallery" in detail
    assert "data-foms-lightbox-src" in detail
