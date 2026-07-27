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


def _create_as_order(*, status="AS_RECEIVED", shipment_extra=None):
    today = date.today().strftime("%Y-%m-%d")
    shipment = dict(shipment_extra or {})
    order = Order(
        received_date=today,
        customer_name="AS 빌링 고객",
        phone="010-1234-5678",
        address="Seoul",
        product="붙박이장",
        status=status,
        manager_name="Alice",
        is_erp_order=True,
        structured_data={"workflow": {"stage": status}, "shipment": shipment},
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


def test_billing_confirm_paid(client):
    # order_id는 요청 전에 확보한다. 요청 teardown이 세션을 remove 하면
    # commit으로 expire된 인스턴스가 detached 상태가 되어 재로딩이 불가능하다.
    _login_as_admin(client)
    order_id = _create_as_order(status="AS_RECEIVED").id
    res = client.post(f"/api/orders/{order_id}/as/billing",
                      json={"type": "paid", "amount": 30000})
    assert res.status_code == 200 and res.get_json()["success"] is True
    db_session.expire_all()
    b = db_session.get(Order, order_id).structured_data["shipment"]["as_billing"]
    assert b["type"] == "paid" and b["confirmed"] is True and b["amount"] == 30000
    assert b["decided_by"] and b["decided_at"]


def test_billing_transition_requires_reason(client):
    _login_as_admin(client)
    order_id = _create_as_order(
        status="AS_RECEIVED",
        shipment_extra={"as_billing": {"type": "free", "confirmed": True}},
    ).id
    res = client.post(f"/api/orders/{order_id}/as/billing", json={"type": "paid"})
    assert res.status_code == 400
    assert res.get_json()["success"] is False
    db_session.expire_all()
    b = db_session.get(Order, order_id).structured_data["shipment"]["as_billing"]
    assert b["type"] == "free"


def test_billing_transition_with_reason(client):
    """사유가 있으면 전환 성공하고 reason이 저장된다."""
    _login_as_admin(client)
    order_id = _create_as_order(
        status="AS_RECEIVED",
        shipment_extra={"as_billing": {"type": "free", "confirmed": True}},
    ).id
    res = client.post(f"/api/orders/{order_id}/as/billing",
                      json={"type": "paid", "amount": 30000, "reason": "고객 과실"})
    assert res.status_code == 200 and res.get_json()["success"] is True
    db_session.expire_all()
    b = db_session.get(Order, order_id).structured_data["shipment"]["as_billing"]
    assert b["type"] == "paid" and b["amount"] == 30000 and b["reason"] == "고객 과실"


def test_billing_invalid_amount_is_400(client):
    """검증 실패는 400 (409는 낙관/무결성 전용)."""
    _login_as_admin(client)
    order_id = _create_as_order(status="AS_RECEIVED").id
    res = client.post(f"/api/orders/{order_id}/as/billing",
                      json={"type": "paid", "amount": -1})
    assert res.status_code == 400
    assert res.get_json()["success"] is False


def test_register_preserves_existing_confirmed_billing(client):
    """재접수(지방 재상차 등)가 확정된 billing을 되돌리지 않는다. 확정/전환은 전용 API로만."""
    _login_as_admin(client, username="as-billing-preserve-admin")
    confirmed = {
        "type": "paid",
        "confirmed": True,
        "amount": 80000,
        "reason": "부품 파손 고객 과실",
        "decided_by": "CS 관리자",
        "decided_at": "2026-07-20T01:02:03",
    }
    order = _create_as_order(status="AS_RECEIVED", shipment_extra={"as_billing": dict(confirmed)})

    res = client.post(f"/api/orders/{order.id}/as/register",
                      json={"as_content": "재접수", "billing_type": "free", "amount": 0})

    assert res.status_code == 200 and res.get_json()["success"] is True
    db_session.expire_all()
    billing = db_session.get(Order, order.id).structured_data["shipment"]["as_billing"]
    assert billing == confirmed
