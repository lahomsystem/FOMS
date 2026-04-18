"""Template contract tests for the ERP Order shared-form script island."""

from werkzeug.security import generate_password_hash

import pytest

from db import db_session
from models import Order, User


@pytest.fixture
def erp_editor_client(client):
    """Login a user that can open ERP Order add/edit pages."""
    user = User(
        username="erp_admin",
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="ERP Admin",
    )
    db_session.add(user)
    db_session.commit()

    client.post(
        "/login",
        data={"username": "erp_admin", "password": "admin"},
        follow_redirects=True,
    )
    return client


def _create_erp_order() -> Order:
    order = Order(
        received_date="2026-04-14",
        customer_name="ERP Order Contract",
        phone="010-1111-2222",
        address="Seoul",
        product="Wardrobe",
        status="RECEIVED",
        is_erp_order=True,
        structured_data={},
    )
    db_session.add(order)
    db_session.commit()
    return order


def _assert_shared_form_script_contract(body: str) -> None:
    payment_urls_idx = body.index("window.__ERP_PAYMENT_ICON_URLS")
    erp_order_shared_idx = body.index("js/orders/erp-order-shared.js")
    html2canvas_idx = body.index("html2canvas.min.js")
    estimate_preview_idx = body.index("js/orders/estimate-preview.js")

    assert payment_urls_idx < erp_order_shared_idx < html2canvas_idx < estimate_preview_idx

    # W5-B8: giant inline shared-form code was moved out of the partial.
    assert "function erpRecalcItemsTotal()" not in body
    assert "async function erpSaveStructured(opts = {})" not in body
    assert "window.erpTogglePayment = async function" not in body

    # Shared host DOM contract remains provided by the ERP Order tab partial.
    assert 'id="erp-items"' in body
    assert 'id="erp-save-btn"' in body
    assert 'id="erp-attachments-input"' in body


def test_add_order_page_renders_thin_erp_order_partial_contract(erp_editor_client) -> None:
    response = erp_editor_client.get("/add")

    assert response.status_code == 200
    body = response.get_data(as_text=True)

    payment_urls_idx = body.index("window.__ERP_PAYMENT_ICON_URLS")
    erp_order_shared_tag_idx = body.index("js/orders/erp-order-shared.js")
    config_idx = body.index('id="erp-order-config"')
    order_enabled_idx = body.index("var ERP_ORDER_ENABLED = _aoCfg ? safeJsonParse(_aoCfg.getAttribute('data-erp-order-enabled'), false) : false;")
    draft_mode_idx = body.index("window.__ERP_ORDER_DRAFT_MODE = true;")

    assert payment_urls_idx < erp_order_shared_tag_idx < config_idx < order_enabled_idx < draft_mode_idx
    _assert_shared_form_script_contract(body)
    assert 'data-erp-order-draft-mode="true"' in body


def test_edit_order_page_renders_thin_erp_order_partial_contract(erp_editor_client) -> None:
    order = _create_erp_order()

    response = erp_editor_client.get(f"/edit/{order.id}")

    assert response.status_code == 200
    body = response.get_data(as_text=True)

    payment_urls_idx = body.index("window.__ERP_PAYMENT_ICON_URLS")
    erp_order_shared_tag_idx = body.index("js/orders/erp-order-shared.js")
    config_idx = body.index('id="erp-order-config"')
    draft_mode_idx = body.index("window.__ERP_ORDER_DRAFT_MODE = false;")

    assert config_idx < payment_urls_idx < erp_order_shared_tag_idx < draft_mode_idx
    _assert_shared_form_script_contract(body)
    assert f'data-order-id="{order.id}"' in body
    assert 'data-erp-order-enabled="true"' in body
