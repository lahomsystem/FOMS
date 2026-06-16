"""Completion dashboard API: search q + focus_order must not depend on browse window."""

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, User


def _login(client, username: str = "completion_search_user") -> None:
    user = User(
        username=username,
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="Completion Search User",
    )
    db_session.add(user)
    db_session.commit()
    client.post(
        "/login",
        data={"username": username, "password": "admin"},
        follow_redirects=True,
    )


def _seed_completion_orders(count: int, *, customer_prefix: str = "고객") -> list[Order]:
    rows: list[Order] = []
    for idx in range(count):
        order = Order(
            received_date="2026-01-01",
            customer_name=f"{customer_prefix}{idx}",
            phone=f"010-1000-{idx:04d}",
            address="Seoul",
            product="붙박이",
            status="COMPLETED",
            is_erp_order=True,
            structured_data={
                "parties": {"customer": {"name": f"{customer_prefix}{idx}", "phone": f"010-1000-{idx:04d}"}}
            },
        )
        db_session.add(order)
        rows.append(order)
    db_session.commit()
    return rows


def test_completion_api_search_q_not_limited_by_browse_window(client, app) -> None:
    """q= filter hits old orders outside latest browse window."""
    with app.app_context():
        _login(client)
        old = Order(
            received_date="2024-01-01",
            customer_name="장성민",
            phone="010-4781-6447",
            address="Busan",
            product="주방",
            status="COMPLETED",
            is_erp_order=True,
            structured_data={
                "parties": {"customer": {"name": "장성민", "phone": "010-4781-6447"}}
            },
        )
        db_session.add(old)
        db_session.commit()
        old_id = old.id
        _seed_completion_orders(250, customer_prefix="최근")

        browse = client.get("/api/orders/completion")
        assert browse.status_code == 200
        browse_ids = {row["id"] for row in browse.get_json()["orders"]}
        assert old_id not in browse_ids

        searched = client.get("/api/orders/completion?q=장성민")
        assert searched.status_code == 200
        hits = searched.get_json()["orders"]
        assert len(hits) == 1
        assert hits[0]["id"] == old_id
        assert hits[0]["customer_name"] == "장성민"


def test_completion_api_focus_order_outside_browse_window(client, app) -> None:
    """focus_order= PK fetch — works even when order id is below browse cutoff."""
    with app.app_context():
        _login(client, "completion_focus_user")
        target = Order(
            received_date="2024-06-01",
            customer_name="장성민",
            phone="010-4781-6447",
            address="Daegu",
            product="거실",
            status="AS_RECEIVED",
            is_erp_order=True,
            structured_data={
                "parties": {"customer": {"name": "장성민", "phone": "010-4781-6447"}}
            },
        )
        db_session.add(target)
        db_session.commit()
        target_id = target.id
        _seed_completion_orders(250, customer_prefix="신규")

        resp = client.get(f"/api/orders/completion?focus_order={target_id}")
        assert resp.status_code == 200
        orders = resp.get_json()["orders"]
        assert orders[0]["id"] == target_id
        assert orders[0]["customer_name"] == "장성민"
