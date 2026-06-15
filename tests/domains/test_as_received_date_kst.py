from datetime import date
import importlib
from pathlib import Path

from flask import session
import pytest
from werkzeug.security import generate_password_hash

from foms.api import erp_orders_structured
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


def _login_as_construction(client, username="as-register-construction"):
    user = User(
        username=username,
        password=generate_password_hash("worker"),
        role="USER",
        team="CONSTRUCTION",
        name="확정시공자",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role

    return user


def _create_order(*, status="RECEIVED", is_erp_order=True, structured_data=None):
    order = Order(
        received_date="2026-04-07",
        customer_name="AS Date Tester",
        phone="010-1234-5678",
        address="Seoul",
        product="Wardrobe",
        status=status,
        manager_name="Alice",
        is_erp_order=is_erp_order,
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

    as_orders = importlib.import_module("foms.api.cs.as_orders")
    monkeypatch.setattr(as_orders, "get_today_kst", lambda: date(2026, 4, 8))

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


def test_as_register_clears_erp_draft_so_as_dashboard_lists_order(client, monkeypatch):
    """Draft ERP order finalized on AS register must pass active_filter (AS tab visibility)."""
    _login_as_admin(client)
    order = Order(
        received_date="2026-04-07",
        customer_name="Draft AS Customer",
        phone="010-9999-8888",
        address="Seoul Draft",
        product="Wardrobe",
        status="DRAFT",
        manager_name="Alice",
        is_erp_order=True,
        structured_data={
            "meta": {"draft": True, "created_via": "ADD_ORDER"},
            "workflow": {"stage": "RECEIVED"},
            "shipment": {},
        },
    )
    db_session.add(order)
    db_session.commit()
    order_id = order.id

    as_orders = importlib.import_module("foms.api.cs.as_orders")
    monkeypatch.setattr(as_orders, "get_today_kst", lambda: date(2026, 4, 8))

    response = client.post(
        f"/api/orders/{order_id}/as/register",
        json={"as_content": "Door hinge broken"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload.get("draft_cleared") is True

    db_session.expire_all()
    saved_order = db_session.get(Order, order_id)
    assert saved_order is not None
    assert saved_order.status == "AS_RECEIVED"
    assert saved_order.structured_data["meta"]["draft"] is False
    assert saved_order.structured_data["workflow"]["stage"] == "AS_RECEIVED"

    visible = (
        db_session.query(Order)
        .filter(Order.id == order_id, Order.active_filter())
        .count()
    )
    assert visible == 1


def test_as_register_matches_confirmed_construction_worker(client, monkeypatch):
    _login_as_construction(client)
    order = _create_order(
        status="AS",
        structured_data={
            "workflow": {"stage": "AS"},
            "shipment": {"construction_workers": ["출고배정자"]},
        },
    )
    order_id = order.id

    as_orders = importlib.import_module("foms.api.cs.as_orders")
    monkeypatch.setattr(as_orders, "get_today_kst", lambda: date(2026, 4, 8))

    response = client.post(
        f"/api/orders/{order_id}/as/register",
        json={
            "as_content": "Needs service",
            "source_screen": "erp_construction_dashboard",
        },
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["construction_workers"] == ["확정시공자"]

    db_session.expire_all()
    saved_order = db_session.get(Order, order_id)
    assert saved_order is not None
    assert saved_order.structured_data["shipment"]["construction_workers"] == ["확정시공자"]


def test_construction_dashboard_as_register_marks_source_screen():
    src = (
        Path(__file__).resolve().parents[2] / "templates/construction/partials/scripts.html"
    ).read_text(encoding="utf-8")
    assert "source_screen: 'erp_construction_dashboard'" in src


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
    order = _create_order(status="RECEIVED", is_erp_order=False, structured_data={})
    order_id = order.id

    orders_mod = importlib.import_module("foms.api.orders")
    monkeypatch.setattr(orders_mod, "get_today_kst", lambda: date(2026, 4, 8))

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
    order = _create_order(status="RECEIVED", is_erp_order=False, structured_data={})
    order_id = order.id

    orders_mod = importlib.import_module("foms.api.orders")
    monkeypatch.setattr(orders_mod, "get_today_kst", lambda: date(2026, 4, 8))

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
