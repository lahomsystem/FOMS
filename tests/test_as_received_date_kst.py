from datetime import date

from flask import session
import pytest
from werkzeug.security import generate_password_hash

from apps.api import erp_orders_as, erp_orders_structured, orders as orders_api
from db import db_session
from models import Order, User


def _login_as_admin(client, username="as-date-admin"):
    user = User(
        username=username,
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="AS Date Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role

    return user


def _create_order(*, status="RECEIVED", is_erp_beta=True, structured_data=None):
    order = Order(
        received_date="2026-04-07",
        customer_name="AS Date Tester",
        phone="010-1234-5678",
        address="Seoul",
        product="Wardrobe",
        status=status,
        manager_name="Alice",
        is_erp_beta=is_erp_beta,
        structured_data=structured_data or {
            "workflow": {"stage": status},
            "shipment": {},
        },
    )
    db_session.add(order)
    db_session.commit()
    return order


def test_as_register_uses_kst_received_date(client, monkeypatch):
    _login_as_admin(client)
    order = _create_order(
        status="AS",
        structured_data={"workflow": {"stage": "AS"}, "shipment": {}},
    )
    order_id = order.id

    monkeypatch.setattr(erp_orders_as, "get_today_kst", lambda: date(2026, 4, 8))

    response = client.post(
        f"/api/orders/{order_id}/as/register",
        json={"as_content": "Needs service"},
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["as_received_date"] == "2026-04-08"

    db_session.expire_all()
    saved_order = db_session.get(Order, order_id)
    assert saved_order is not None
    assert saved_order.as_received_date == "2026-04-08"


@pytest.mark.parametrize(
    ("old_stage", "target_stage"),
    [("RECEIVED", "AS"), ("AS", "AS_RECEIVED")],
)
def test_structured_stage_transition_uses_kst_received_date(
    app,
    client,
    monkeypatch,
    old_stage,
    target_stage,
):
    user = _login_as_admin(client, username="structured-stage-admin")
    order = _create_order(
        status=old_stage,
        structured_data={"workflow": {"stage": old_stage}, "shipment": {}},
    )
    old_sd = {"workflow": {"stage": old_stage}}
    new_sd = {"workflow": {"stage": target_stage}}

    monkeypatch.setattr(erp_orders_structured, "get_today_kst", lambda: date(2026, 4, 8))
    monkeypatch.setattr(
        erp_orders_structured,
        "check_quest_approvals_complete",
        lambda *args, **kwargs: (True, []),
    )
    monkeypatch.setattr(
        erp_orders_structured,
        "create_quest_from_template",
        lambda *args, **kwargs: None,
    )

    with app.test_request_context("/api/orders/structured"):
        session["user_id"] = user.id
        session["username"] = user.username
        erp_orders_structured._handle_stage_transition(db_session, order, old_sd, new_sd)

    assert order.status == target_stage
    assert order.as_received_date == "2026-04-08"


def test_update_order_status_uses_kst_received_date(client, monkeypatch):
    _login_as_admin(client, username="single-status-admin")
    order = _create_order(status="RECEIVED", is_erp_beta=False, structured_data={})
    order_id = order.id

    monkeypatch.setattr(orders_api, "get_today_kst", lambda: date(2026, 4, 8))

    response = client.post(
        "/api/update_order_status",
        json={"order_id": order_id, "status": "AS_RECEIVED"},
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True

    db_session.expire_all()
    saved_order = db_session.get(Order, order_id)
    assert saved_order is not None
    assert saved_order.as_received_date == "2026-04-08"


def test_bulk_update_order_status_uses_kst_received_date(client, monkeypatch):
    _login_as_admin(client, username="bulk-status-admin")
    order = _create_order(status="RECEIVED", is_erp_beta=False, structured_data={})
    order_id = order.id

    monkeypatch.setattr(orders_api, "get_today_kst", lambda: date(2026, 4, 8))

    response = client.post(
        "/api/bulk_update_order_status",
        json={"order_ids": [order_id], "status": "AS_RECEIVED"},
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["updated"] == 1

    db_session.expire_all()
    saved_order = db_session.get(Order, order_id)
    assert saved_order is not None
    assert saved_order.as_received_date == "2026-04-08"
