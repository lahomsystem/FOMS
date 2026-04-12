"""Focused contract freezes for the legacy orders blueprint boundary."""

from werkzeug.security import generate_password_hash

from apps.api import orders as orders_api
from db import db_session
from foms.api.orders import field_update as field_update_module
from models import Order, User


def _login_as_admin(client, username: str) -> User:
    """Create an admin user and attach it to the test client session."""
    user = User(
        username=username,
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="Orders Contract Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role

    return user


def _create_order(**overrides) -> Order:
    """Create a minimal order row for orders boundary contract tests."""
    payload = {
        "received_date": "2026-04-11",
        "customer_name": "Orders Boundary Tester",
        "phone": "010-1111-2222",
        "address": "Seoul",
        "product": "Wardrobe",
        "status": "RECEIVED",
        "is_regional": False,
        "is_self_measurement": False,
        "structured_data": {},
    }
    payload.update(overrides)
    order = Order(**payload)
    db_session.add(order)
    db_session.commit()
    return order


def test_apps_api_orders_reexports_expected_contract_symbols() -> None:
    """The legacy wrapper must keep exporting the stable helper surface."""
    exported = set(getattr(orders_api, "__all__", []))
    assert {"orders_bp", "can_edit_erp", "enqueue_geocode_order_address", "get_today_kst"} <= exported


def test_api_orders_returns_raw_json_list(client) -> None:
    """`/api/orders` must keep the legacy FullCalendar list contract."""
    _login_as_admin(client, "orders-contract-list-admin")

    response = client.get("/api/orders")

    assert response.status_code == 200
    payload = response.get_json()
    assert isinstance(payload, list)


def test_api_orders_nearby_requires_address(client) -> None:
    """Nearby endpoint must keep the legacy 400 error payload when address is missing."""
    _login_as_admin(client, "orders-contract-nearby-admin")

    response = client.get("/api/orders/nearby")

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert "message" in payload
    assert "error" in payload


def test_update_regional_status_rejects_non_regional_order(client) -> None:
    """Regional status route must reject non-regional orders with a 404 contract."""
    _login_as_admin(client, "orders-contract-regional-status-admin")
    order = _create_order(is_regional=False, is_self_measurement=False)

    response = client.post(
        "/api/update_regional_status",
        json={"order_id": order.id, "field": "measurement_completed", "value": True},
    )

    assert response.status_code == 404
    payload = response.get_json()
    assert payload["success"] is False
    assert "유효하지 않은 주문" in payload["message"]


def test_update_regional_memo_rejects_non_regional_order(client) -> None:
    """Regional memo route must preserve the same invalid-order contract."""
    _login_as_admin(client, "orders-contract-regional-memo-admin")
    order = _create_order(is_regional=False, is_self_measurement=False)

    response = client.post(
        "/api/update_regional_memo",
        json={"order_id": order.id, "memo": "memo"},
    )

    assert response.status_code == 404
    payload = response.get_json()
    assert payload["success"] is False
    assert "유효하지 않은 주문" in payload["message"]


def test_update_order_field_address_is_rejected_by_allowlist(client) -> None:
    """Address updates are not part of the current legacy allowlist contract."""
    _login_as_admin(client, "orders-contract-field-admin")
    order = _create_order(structured_data={"site": {"address_full": "Seoul"}})

    response = client.post(
        "/api/update_order_field",
        json={"order_id": order.id, "field": "address", "value": "Busan"},
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert "허용되지 않은 필드입니다" in payload["message"]

    db_session.expire_all()
    saved_order = db_session.get(Order, order.id)
    assert saved_order is not None
    assert saved_order.address == "Seoul"
    assert saved_order.structured_data["site"]["address_full"] == "Seoul"


def test_update_order_field_manager_name_keeps_legacy_success_shape(client) -> None:
    """Reachable manager-name updates must preserve the legacy success payload."""
    _login_as_admin(client, "orders-contract-manager-admin")
    order = _create_order(structured_data={})

    response = client.post(
        "/api/update_order_field",
        json={"order_id": order.id, "field": "manager_name", "value": "Bob"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["normalized_value"] == "Bob"
    assert payload["status"] == "RECEIVED"
    assert {
        "message",
        "status_label",
        "as_completed_date",
        "as_visit_date",
        "as_pending",
        "as_blueprint",
        "sales_delivery",
    } <= payload.keys()

    db_session.expire_all()
    saved_order = db_session.get(Order, order.id)
    assert saved_order is not None
    assert saved_order.manager_name == "Bob"
    assert saved_order.structured_data == {}


def test_update_order_field_manager_name_syncs_structured_data_for_erp_beta(client) -> None:
    """ERP beta manager-name updates must keep flat/structured data in sync."""
    _login_as_admin(client, "orders-contract-manager-beta-admin")
    order = _create_order(is_erp_beta=True, structured_data={})

    response = client.post(
        "/api/update_order_field",
        json={"order_id": order.id, "field": "manager_name", "value": "Bob"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["normalized_value"] == "Bob"

    db_session.expire_all()
    saved_order = db_session.get(Order, order.id)
    assert saved_order is not None
    assert saved_order.manager_name == "Bob"
    assert saved_order.structured_data["parties"]["manager"]["name"] == "Bob"


def test_field_update_structured_sync_fields_match_reachable_contract() -> None:
    """Structured sync hints must not advertise unreachable legacy fields."""
    assert field_update_module.STRUCTURED_SYNC_FIELDS <= set(
        field_update_module.ORDER_UPDATE_ALLOWED_FIELDS
    )
