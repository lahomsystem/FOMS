from db import db_session
from models import ChannelManagerLink, Order, User
from foms.services.channel_quick_actions import (
    STATUS_MAP,
    get_order_summary_for_wam,
    parse_foms_command,
    process_foms_command,
)
from foms.services.channel_security import generate_wam_short_link_token


ORDER_CMD = "\uc8fc\ubb38"
SCHEDULE_CMD = "\uc77c\uc815"


def _active_manager(manager_id: str, *, role: str = "STAFF") -> str:
    """CHANNEL-AUTH-01: quick action \uc740 read scope \uc788\ub294 active manager \ub9cc \uc870\ud68c \uac00\ub2a5.

    active User + active ChannelManagerLink \ub97c \ub9cc\ub4e4\uace0 manager_id \ub97c \ub3cc\ub824\uc900\ub2e4.
    """
    user = User(
        username=f"qa-mgr-{manager_id}",
        password="x",
        role=role,
        name=f"qa-{manager_id}",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.add(
        ChannelManagerLink(channel_manager_id=manager_id, user_id=user.id, is_active=True)
    )
    db_session.commit()
    return manager_id


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
    """존재하지 않는 주문 → no-data(존재 여부·order id 미노출, PII 0)."""
    with app.app_context():
        mgr = _active_manager("mgr-notfound")
        res = process_foms_command(f"{ORDER_CMD} 99999", manager_id=mgr)
        # 존재 여부 미노출: order id 를 결과에 담지 않는다.
        assert "99999" not in res["result"]["text"]


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

        mgr = _active_manager("mgr-success")
        res = process_foms_command(f"{ORDER_CMD} {order.id}", manager_id=mgr)
        text = res["result"]["text"]
        assert "Legacy Customer" in text
        assert "Legacy Product" in text

        wam_data = get_order_summary_for_wam(order.id)
        assert wam_data is not None
        assert wam_data["customer_name"] == "Legacy Customer"
        assert wam_data["status_kr"] == STATUS_MAP["RECEIVED"]


def test_process_foms_command_gates_on_canonical_identity_resolve(monkeypatch, app):
    """CHANNEL-AUTH-01: manager 인증은 canonical identity resolve 로 게이트된다.

    resolve 가 deny(None) 면 PII 없는 no-data 결과를 반환한다(fail-open 제거).
    """
    with app.app_context():
        monkeypatch.setattr(
            "foms.services.channel_quick_actions.get_user_by_manager_id",
            lambda manager_id: None,
        )

        res = process_foms_command(f"{ORDER_CMD} 123", manager_id="mgr-1")

        assert res["result"]["type"] == "text"
        assert "123" not in res["result"]["text"]  # 존재 여부 미노출


def test_get_order_summary_for_wam_uses_structured_data_for_erp_order(app):
    with app.app_context():
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


def test_channel_wam_page_is_retired(client, app):
    with app.app_context():
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

    response = client.get("/channel/wam/")

    assert response.status_code == 410
    assert "retired" in response.get_data(as_text=True)


def test_short_wam_link_redirects_to_mobile_erp_detail(client, app):
    with app.app_context():
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
    assert response.headers["Location"].endswith(f"/erp/orders/{order.id}/mobile")
    assert "launch_token=" not in response.headers["Location"]
