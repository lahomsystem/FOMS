from db import db_session
from models import Order
from foms.services.channel_quick_actions import (
    STATUS_MAP,
    get_order_summary_for_wam,
    parse_foms_command,
    process_foms_command,
)
from foms.services.channel_security import generate_wam_session_token, generate_wam_short_link_token


ORDER_CMD = "\uc8fc\ubb38"
SCHEDULE_CMD = "\uc77c\uc815"


def test_parse_foms_command():
    cmd, param = parse_foms_command(f"{ORDER_CMD} 123")
    assert cmd == ORDER_CMD
    assert param == "123"

    cmd, param = parse_foms_command(f"{SCHEDULE_CMD} 456")
    assert cmd == SCHEDULE_CMD
    assert param == "456"

    cmd, param = parse_foms_command("invalid")
    assert cmd == ""
    assert param == ""


def test_process_foms_command_invalid(app):
    with app.app_context():
        res = process_foms_command("unknown 123")
        assert "/foms" in res["result"]["text"]

        res = process_foms_command(f"{ORDER_CMD} abc")
        assert "/foms" in res["result"]["text"]


def test_process_foms_command_order_not_found(app):
    with app.app_context():
        res = process_foms_command(f"{ORDER_CMD} 99999")
        assert "99999" in res["result"]["text"]


def test_process_foms_command_success(app):
    with app.app_context():
        order = Order(
            received_date="2026-03-26",
            customer_name="Legacy Customer",
            phone="010-9999-8888",
            address="Seoul Gangnam-gu",
            status="RECEIVED",
            product="Legacy Product",
        )
        db_session.add(order)
        db_session.commit()

        res = process_foms_command(f"{ORDER_CMD} {order.id}")
        text = res["result"]["text"]
        assert "Legacy Customer" in text
        assert "Legacy Product" in text

        wam_data = get_order_summary_for_wam(order.id)
        assert wam_data is not None
        assert wam_data["customer_name"] == "Legacy Customer"
        assert wam_data["status_kr"] == STATUS_MAP["RECEIVED"]


def test_process_foms_command_uses_canonical_identity_import(monkeypatch, app):
    with app.app_context():
        monkeypatch.setattr(
            "foms.services.channel_identity.is_action_allowed_for_manager",
            lambda manager_id, action_type: False,
        )

        res = process_foms_command(f"{ORDER_CMD} 123", manager_id="mgr-1")

        assert res["type"] == "text"
        assert "권한이 없습니다" in res["text"]


def test_get_order_summary_for_wam_uses_structured_data_for_erp_beta(app):
    with app.app_context():
        order = Order(
            received_date="2026-03-27",
            customer_name="ERP Beta",
            phone="000-0000-0000",
            address="-",
            product="ERP Beta",
            status="RECEIVED",
            is_erp_beta=True,
            structured_data={
                "workflow": {"stage": "DRAWING"},
                "parties": {
                    "customer": {"name": "Real Customer", "phone": "010-1234-5678"},
                    "manager": {"name": "Mango"},
                },
                "site": {"address_full": "Seoul Teheran-ro 123"},
                "items": [{"product_name": "Kitchen Set"}],
                "schedule": {
                    "measurement": {"date": "2026-03-28"},
                    "construction": {"date": "2026-04-01"},
                },
            },
        )
        db_session.add(order)
        db_session.commit()

        wam_data = get_order_summary_for_wam(order.id)

        assert wam_data is not None
        assert wam_data["customer_name"] == "Real Customer"
        assert wam_data["phone"] == "010-1234-5678"
        assert wam_data["address"] == "Seoul Teheran-ro 123"
        assert wam_data["product"] == "Kitchen Set"
        assert wam_data["measurement_date"] == "2026-03-28"
        assert wam_data["construction_date"] == "2026-04-01"
        assert wam_data["manager_name"] == "Mango"
        assert wam_data["status_kr"] != "RECEIVED"


def test_channel_wam_page_renders_structured_summary(client, app):
    with app.app_context():
        order = Order(
            received_date="2026-03-27",
            customer_name="ERP Beta",
            phone="000-0000-0000",
            address="-",
            product="ERP Beta",
            status="RECEIVED",
            is_erp_beta=True,
            structured_data={
                "workflow": {"stage": "DRAWING"},
                "parties": {
                    "customer": {"name": "Real Customer", "phone": "010-1234-5678"},
                    "manager": {"name": "Mango"},
                },
                "site": {"address_full": "Seoul Teheran-ro 123"},
                "items": [{"product_name": "Kitchen Set"}],
                "schedule": {
                    "measurement": {"date": "2026-03-28"},
                    "construction": {"date": "2026-04-01"},
                },
            },
        )
        db_session.add(order)
        db_session.commit()
        token = generate_wam_session_token("wam_viewer", order.id)

    client.set_cookie("wam_session", token, path="/channel/wam")
    response = client.get("/channel/wam/")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Real Customer" in body
    assert "010-1234-5678" in body
    assert "Seoul Teheran-ro 123" in body
    assert "Kitchen Set" in body
    assert "Mango" in body
    assert "2026-03-28" in body


def test_short_wam_link_redirects_to_entry_ticket_flow(client, app):
    with app.app_context():
        order = Order(
            received_date="2026-03-27",
            customer_name="ERP Beta",
            phone="000-0000-0000",
            address="-",
            product="ERP Beta",
            status="RECEIVED",
            is_erp_beta=True,
            structured_data={
                "workflow": {"stage": "DRAWING"},
                "parties": {
                    "customer": {"name": "Real Customer", "phone": "010-1234-5678"},
                    "manager": {"name": "Mango"},
                },
                "site": {"address_full": "Seoul Teheran-ro 123"},
                "items": [{"product_name": "Kitchen Set"}],
                "schedule": {
                    "measurement": {"date": "2026-03-28"},
                    "construction": {"date": "2026-04-01"},
                },
            },
        )
        db_session.add(order)
        db_session.commit()
        token = generate_wam_short_link_token(order.id)

    response = client.get(f"/w/{token}", follow_redirects=False)

    assert response.status_code == 302
    assert "/channel/wam/?entry_ticket=" in response.headers["Location"]
    assert "launch_token=" not in response.headers["Location"]

    final_response = client.get(response.headers["Location"], follow_redirects=True)
    body = final_response.get_data(as_text=True)
    assert final_response.status_code == 200
    assert "Real Customer" in body
