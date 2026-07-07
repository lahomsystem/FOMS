from db import db_session
from models import Order, OrderAttachment
from foms.services.channel_security import generate_wam_session_token, generate_wam_short_link_token


def _create_order(**overrides):
    order = Order(
        received_date="2026-03-27",
        customer_name="WAM Customer",
        phone="010-1111-2222",
        address="Seoul Test-gu 123",
        product="Starter Kitchen",
        status="RECEIVED",
        manager_name="Manager Kim",
        structured_data={
            "workflow": {"stage": "DRAWING"},
            "parties": {"customer": {"name": "WAM Customer", "phone": "010-1111-2222"}},
            "site": {"address_full": "Seoul Test-gu 123"},
            "items": [{"product_name": "Starter Kitchen"}],
        },
        is_erp_order=True,
    )
    for key, value in overrides.items():
        setattr(order, key, value)
    db_session.add(order)
    db_session.commit()
    return order


def test_wam_api_missing_token_returns_retired_json(client):
    response = client.get("/channel/wam/api/bootstrap")

    assert response.status_code == 410
    assert response.json["ok"] is False
    assert response.json["error"]["code"] == "wam_retired"


def test_wam_api_session_cookie_still_returns_retired_json(client, app):
    with app.app_context():
        order = _create_order()
        token = generate_wam_session_token("wam_viewer", order.id)

    client.set_cookie("wam_session", token, path="/channel/wam")
    response = client.get("/channel/wam/api/bootstrap")

    assert response.status_code == 410
    assert response.json["error"]["code"] == "wam_retired"


def test_wam_attachment_routes_are_retired_before_storage_access(client, app):
    with app.app_context():
        order = _create_order()
        attachment = OrderAttachment(
            order_id=order.id,
            filename="drawing.png",
            file_type="image",
            category="drawing",
            file_size=1024,
            storage_key="wam/test-drawing.png",
        )
        db_session.add(attachment)
        db_session.commit()

    response = client.get(f"/channel/wam/api/attachments/{attachment.id}/open")

    assert response.status_code == 410
    assert response.json["error"]["code"] == "wam_retired"


def test_short_link_keeps_existing_channel_messages_working(client, app):
    with app.app_context():
        order = _create_order()
        token = generate_wam_short_link_token(order.id)

    response = client.get(f"/w/{token}", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"/erp/orders/{order.id}/mobile")
    assert "/channel/wam/" not in response.headers["Location"]


def test_bound_short_link_no_longer_requires_wam_manager_binding(client, app):
    with app.app_context():
        order = _create_order()
        token = generate_wam_short_link_token(order.id, manager_id="unknown-manager")

    response = client.get(f"/w/{token}", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"/erp/orders/{order.id}/mobile")
