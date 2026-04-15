"""Template contract tests for the ERP Beta shared-form script island."""

from werkzeug.security import generate_password_hash

import pytest

from db import db_session
from models import Order, User


@pytest.fixture
def erp_editor_client(client):
    """Login a user that can open ERP Beta add/edit pages."""
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


def _create_erp_beta_order() -> Order:
    order = Order(
        received_date="2026-04-14",
        customer_name="ERP Beta Contract",
        phone="010-1111-2222",
        address="Seoul",
        product="Wardrobe",
        status="RECEIVED",
        is_erp_beta=True,
        structured_data={},
    )
    db_session.add(order)
    db_session.commit()
    return order


def _assert_shared_form_script_contract(body: str) -> None:
    payment_urls_idx = body.index("window.__ERP_PAYMENT_ICON_URLS")
    beta_shared_idx = body.index("js/orders/beta-shared.js")
    html2canvas_idx = body.index("html2canvas.min.js")
    estimate_preview_idx = body.index("js/orders/estimate-preview.js")

    assert payment_urls_idx < beta_shared_idx < html2canvas_idx < estimate_preview_idx

    # W5-B8: giant inline shared-form code was moved out of the partial.
    assert "function erpRecalcItemsTotal()" not in body
    assert "async function erpSaveStructured(opts = {})" not in body
    assert "window.erpTogglePayment = async function" not in body

    # Shared host DOM contract remains provided by the ERP Beta tab partial.
    assert 'id="erp-items"' in body
    assert 'id="erp-save-btn"' in body
    assert 'id="erp-attachments-input"' in body


def test_add_order_page_renders_thin_erp_beta_partial_contract(erp_editor_client) -> None:
    response = erp_editor_client.get("/add")

    assert response.status_code == 200
    body = response.get_data(as_text=True)

    order_id_idx = body.index("let ORDER_ID = 0;")
    draft_mode_idx = body.index("window.__ERP_BETA_DRAFT_MODE = true;")
    payment_urls_idx = body.index("window.__ERP_PAYMENT_ICON_URLS")

    assert order_id_idx < draft_mode_idx < payment_urls_idx
    _assert_shared_form_script_contract(body)


def test_edit_order_page_renders_thin_erp_beta_partial_contract(erp_editor_client) -> None:
    order = _create_erp_beta_order()

    response = erp_editor_client.get(f"/edit/{order.id}")

    assert response.status_code == 200
    body = response.get_data(as_text=True)

    order_id_idx = body.index(
        "const ORDER_ID = parseInt(document.querySelector('.card[data-order-id]')?.dataset.orderId || '0');"
    )
    draft_mode_idx = body.index("window.__ERP_BETA_DRAFT_MODE = false;")
    payment_urls_idx = body.index("window.__ERP_PAYMENT_ICON_URLS")

    assert order_id_idx < draft_mode_idx < payment_urls_idx
    _assert_shared_form_script_contract(body)
