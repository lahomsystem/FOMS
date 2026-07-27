"""AS 접수 시 무상/유상 추정(as_billing) 저장 계약 테스트."""
from datetime import date

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, User


def _login_as_admin(client, username="as-billing-admin"):
    user = User(
        username=username,
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="AS Billing Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role

    return user


def _create_as_order(*, status="AS_RECEIVED"):
    today = date.today().strftime("%Y-%m-%d")
    order = Order(
        received_date=today,
        customer_name="AS 빌링 고객",
        phone="010-1234-5678",
        address="Seoul",
        product="붙박이장",
        status=status,
        manager_name="Alice",
        is_erp_order=True,
        structured_data={"workflow": {"stage": status}, "shipment": {}},
    )
    db_session.add(order)
    db_session.commit()
    return order


def test_register_defaults_free_unconfirmed(client):
    _login_as_admin(client, username="as-billing-default-admin")
    order = _create_as_order(status="CS")
    res = client.post(f"/api/orders/{order.id}/as/register", json={"as_content": "문틀 뒤틀림"})
    assert res.status_code == 200 and res.get_json()["success"] is True
    db_session.expire_all()
    billing = db_session.get(Order, order.id).structured_data["shipment"]["as_billing"]
    assert billing["type"] == "free"
    assert billing["confirmed"] is False
    assert billing["amount"] is None


def test_register_paid_estimate_with_amount(client):
    _login_as_admin(client, username="as-billing-paid-admin")
    order = _create_as_order(status="CS")
    res = client.post(f"/api/orders/{order.id}/as/register",
                      json={"as_content": "부품 교체", "billing_type": "paid", "amount": 50000})
    assert res.get_json()["success"] is True
    db_session.expire_all()
    billing = db_session.get(Order, order.id).structured_data["shipment"]["as_billing"]
    assert billing["type"] == "paid" and billing["amount"] == 50000 and billing["confirmed"] is False
