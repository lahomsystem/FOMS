from werkzeug.security import generate_password_hash

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


def _create_erp_beta_order(manager_name="Alice"):
    order = Order(
        received_date="2026-03-31",
        customer_name="ERP Beta",
        phone="010-1111-2222",
        address="Seoul",
        product="ERP Beta",
        status="MEASURE",
        manager_name=manager_name,
        is_erp_beta=True,
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


def test_measurement_manager_update_syncs_erp_beta_fields(client):
    _login_erp_editor(client)
    order_id = _create_erp_beta_order(manager_name="Alice")

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


def test_measurement_manager_delete_clears_erp_beta_fields(client):
    _login_erp_editor(client)
    order_id = _create_erp_beta_order(manager_name="Alice")

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
