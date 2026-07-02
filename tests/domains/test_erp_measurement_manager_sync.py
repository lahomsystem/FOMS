from werkzeug.security import generate_password_hash

import datetime

from db import db_session
from models import Order, User


def _login_erp_editor(client):
    user = User(
        username="measurement_admin",
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="Measurement Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role

    return user


def _create_erp_order(manager_name="Alice"):
    order = Order(
        received_date="2026-03-31",
        customer_name="ERP Order",
        phone="010-1111-2222",
        address="Seoul",
        product="ERP Order",
        status="MEASURE",
        manager_name=manager_name,
        is_erp_order=True,
        structured_data={
            "parties": {
                "customer": {
                    "name": "Customer",
                    "phone": "010-1111-2222",
                },
                "manager": {
                    "name": manager_name,
                },
            }
        },
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def test_measurement_manager_update_syncs_erp_order_fields(client):
    _login_erp_editor(client)
    order_id = _create_erp_order(manager_name="Alice")

    response = client.post(
        f"/api/erp/measurement/update/{order_id}",
        json={"field": "manager", "value": "Mango"},
    )

    assert response.status_code == 200
    assert response.get_json()["success"] is True

    order = db_session.query(Order).filter(Order.id == order_id).first()
    assert order is not None
    assert order.manager_name == "Mango"
    assert ((order.structured_data or {}).get("parties") or {}).get("manager", {}).get("name") == "Mango"


def test_measurement_manager_delete_clears_erp_order_fields(client):
    _login_erp_editor(client)
    order_id = _create_erp_order(manager_name="Alice")

    response = client.post(
        f"/api/erp/measurement/update/{order_id}",
        json={"field": "manager", "value": ""},
    )

    assert response.status_code == 200
    assert response.get_json()["success"] is True

    order = db_session.query(Order).filter(Order.id == order_id).first()
    assert order is not None
    assert order.manager_name == ""
    assert ((order.structured_data or {}).get("parties") or {}).get("manager", {}).get("name") == ""


def test_measurement_summary_returns_panel_dates(client):
    """Regression: summary must not 500 when accessing g.current_user (mine filter path)."""
    _login_erp_editor(client)
    _create_erp_order(manager_name="Alice")

    response = client.get("/api/erp/measurement/summary")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    panel_dates = payload["panel_dates"]
    assert isinstance(panel_dates, list)
    assert len(panel_dates) == 15
    assert all(
        "date" in row and "count" in row and "count_regional" in row and "count_metro" in row and "cases" in row
        for row in panel_dates
    )

    mine_response = client.get("/api/erp/measurement/summary?mine=1")
    assert mine_response.status_code == 200
    mine_payload = mine_response.get_json()
    assert mine_payload["success"] is True
    assert isinstance(mine_payload["panel_dates"], list)


def test_measurement_summary_segmented_counts(client, monkeypatch):
    """summary API는 날짜별 count_regional/count_metro를 반환한다."""
    import foms.api.measurement.routes as measurement_routes

    monkeypatch.setattr(measurement_routes.measurement_api, "get_today_kst", lambda: datetime.date(2026, 7, 2))
    _login_erp_editor(client)
    target = "2026-07-06"
    regional = Order(
        received_date=target,
        customer_name="지방 summary",
        phone="010-7777-8888",
        address="Busan",
        product="장",
        status="MEASURE",
        is_erp_order=True,
        is_regional=True,
        structured_data={"schedule": {"measurement": {"date": target}}},
    )
    metro = Order(
        received_date=target,
        customer_name="수도권 summary",
        phone="010-9999-0000",
        address="Seoul",
        product="장",
        status="MEASURE",
        is_erp_order=True,
        is_regional=False,
        structured_data={"schedule": {"measurement": {"date": target}}},
    )
    db_session.add_all([regional, metro])
    db_session.commit()

    payload = client.get("/api/erp/measurement/summary").get_json()
    row = next(item for item in payload["panel_dates"] if item["date"] == target)
    assert row["count"] == 2
    assert row["count_regional"] == 1
    assert row["count_metro"] == 1


def test_measurement_manager_update_resolves_numeric_user_id_to_name(client):
    _login_erp_editor(client)
    manager_user = User(
        username="resolved_manager",
        password=generate_password_hash("manager"),
        role="STAFF",
        team="CS",
        name="복구 담당자",
        is_active=True,
    )
    db_session.add(manager_user)
    db_session.commit()
    order_id = _create_erp_order(manager_name="Alice")

    response = client.post(
        f"/api/erp/measurement/update/{order_id}",
        json={"field": "manager", "value": str(manager_user.id)},
    )

    assert response.status_code == 200
    assert response.get_json()["success"] is True

    order = db_session.query(Order).filter(Order.id == order_id).first()
    assert order is not None
    assert order.manager_name == "복구 담당자"
    assert ((order.structured_data or {}).get("parties") or {}).get("manager", {}).get("name") == "복구 담당자"
