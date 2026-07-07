from db import db_session
from models import Order
from foms.services.channel_security import generate_wam_short_link_token


def _create_order():
    order = Order(
        received_date="2026-03-27",
        customer_name="ERP Order",
        phone="000-0000-0000",
        address="-",
        product="ERP Order",
        status="RECEIVED",
        is_erp_order=True,
        structured_data={
            "workflow": {"stage": "DRAWING"},
            "parties": {"customer": {"name": "Real Customer", "phone": "010-1234-5678"}},
            "site": {"address_full": "Seoul Teheran-ro 123"},
            "items": [{"product_name": "Kitchen Set"}],
        },
    )
    db_session.add(order)
    db_session.commit()
    return order


def test_short_wam_link_redirects_to_mobile_erp_order_detail(client, app):
    with app.app_context():
        order = _create_order()
        token = generate_wam_short_link_token(order.id)

    response = client.get(f"/w/{token}", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"/erp/orders/{order.id}/mobile")
    assert "/channel/wam/" not in response.headers["Location"]


def test_short_wam_link_survives_wam_feature_flag_disabled(client, app, monkeypatch):
    monkeypatch.setenv("CHANNEL_WAM_ENABLED", "false")
    with app.app_context():
        order = _create_order()
        token = generate_wam_short_link_token(order.id)

    response = client.get(f"/w/{token}", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"/erp/orders/{order.id}/mobile")


def test_short_wam_link_rejects_invalid_token(client):
    response = client.get("/w/not-a-token", follow_redirects=False)

    assert response.status_code == 401
    assert "Invalid or expired link" in response.get_data(as_text=True)


def test_channel_wam_html_page_is_retired(client):
    response = client.get("/channel/wam/")

    assert response.status_code == 410
    assert "Channel WAM page has been retired" in response.get_data(as_text=True)


def test_channel_wam_api_is_retired_json(client):
    response = client.get("/channel/wam/api/bootstrap")
    payload = response.get_json()

    assert response.status_code == 410
    assert payload["ok"] is False
    assert payload["error"]["code"] == "wam_retired"
