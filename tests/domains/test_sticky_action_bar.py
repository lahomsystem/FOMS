"""P0-06: Sticky bottom CTA + touch target contracts (C08)."""

from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, User

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def erp_editor_client(client):
    """Login a user that can open order add/edit pages."""
    user = User(
        username="sticky_bar_admin",
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="Sticky Bar Admin",
    )
    db_session.add(user)
    db_session.commit()
    client.post(
        "/login",
        data={"username": "sticky_bar_admin", "password": "admin"},
        follow_redirects=True,
    )
    return client


def test_sticky_css_and_visual_viewport_contract() -> None:
    css = (ROOT / "static/css/components/foms-sticky-action-bar.css").read_text(
        encoding="utf-8"
    )
    assert "--foms-keyboard-h" in css
    assert ".foms-sticky-action-bar" in css

    js = (ROOT / "static/js/foms/visual-viewport.js").read_text(encoding="utf-8")
    assert "--foms-keyboard-h" in js
    assert "visualViewport" in js


def test_mobile_optimization_includes_foms_page_form() -> None:
    text = (
        ROOT / "static/css/foundation/erp-pro/09-mobile-erp-optimization.css"
    ).read_text(encoding="utf-8")
    assert "form.foms-page-form" in text
    assert "min-height: 44px" in text


def test_layout_includes_sticky_assets() -> None:
    head = (ROOT / "templates/partials/shared/layout_head.html").read_text(
        encoding="utf-8"
    )
    scripts = (ROOT / "templates/partials/shared/layout_scripts.html").read_text(
        encoding="utf-8"
    )
    assert "css/components/foms-sticky-action-bar.css" in head
    assert "js/foms/visual-viewport.js" in scripts


def test_add_order_template_sticky_footer() -> None:
    text = (ROOT / "templates/orders/add_order.html").read_text(encoding="utf-8")
    assert 'class="foms-page-form"' in text
    assert '<footer class="foms-sticky-action-bar"' in text
    assert "기존 주문 추가" in text


def test_edit_order_body_legacy_form_sticky_footer() -> None:
    text = (ROOT / "templates/orders/partials/edit_order_body.html").read_text(
        encoding="utf-8"
    )
    assert 'class="foms-page-form"' in text
    assert '<footer class="foms-sticky-action-bar"' in text
    assert "주문 수정" in text


def test_add_order_page_renders_sticky_bar(erp_editor_client) -> None:
    response = erp_editor_client.get("/add")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "foms-sticky-action-bar" in body
    assert "foms-page-form" in body
    assert "visual-viewport.js" in body


def test_edit_order_non_erp_renders_sticky_bar(erp_editor_client) -> None:
    order = Order(
        received_date="2026-05-29",
        customer_name="Sticky Legacy",
        phone="010-5555-4444",
        address="Seoul",
        product="Kitchen",
        status="RECEIVED",
        is_erp_order=False,
        structured_data={},
    )
    db_session.add(order)
    db_session.commit()

    response = erp_editor_client.get(f"/edit/{order.id}")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "foms-sticky-action-bar" in body
    assert 'id="editOrderForm"' in body


def test_erp_order_tab_mobile_template_sticky_footer_unchanged() -> None:
    text = (ROOT / "templates/orders/partials/erp_order_tab_mobile.html").read_text(
        encoding="utf-8"
    )
    assert "erp-mobile-sticky-action-bar" in text
    assert 'id="erp-save-btn"' in text
    assert 'id="erp-load-btn"' in text
    assert "erp-mobile-amount-toolbar" not in text


def test_erp_order_tab_template_save_on_shipment_row() -> None:
    text = (ROOT / "templates/orders/partials/erp_order_tab.html").read_text(
        encoding="utf-8"
    )
    assert 'class="card-body foms-page-form"' in text
    assert "erp-amount-save-row" in text
    assert 'id="erp-save-btn"' in text
    assert 'id="erp-items-total"' in text
    save_idx = text.index('id="erp-save-btn"')
    total_idx = text.index('id="erp-items-total"')
    assert save_idx < total_idx
    assert 'id="erp-load-btn"' not in text
    assert '<footer class="foms-sticky-action-bar"' not in text


def test_edit_order_erp_save_in_amount_row_not_sticky_footer(erp_editor_client) -> None:
    order = Order(
        received_date="2026-05-29",
        customer_name="Sticky ERP",
        phone="010-7777-8888",
        address="Seoul",
        product="Kitchen",
        status="RECEIVED",
        is_erp_order=True,
        structured_data={"schema_version": 1},
    )
    db_session.add(order)
    db_session.commit()

    response = erp_editor_client.get(f"/edit/{order.id}?open=erp-order")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'id="erp-save-btn"' in body
    assert 'id="erp-load-btn"' not in body
    save_idx = body.index('id="erp-save-btn"')
    total_idx = body.index('id="erp-items-total"', save_idx)
    assert save_idx < total_idx
    erp_save_snippet = body[save_idx:total_idx + 80]
    assert '<footer class="foms-sticky-action-bar"' not in erp_save_snippet
