"""Focused contract freezes for the legacy orders blueprint boundary."""

from werkzeug.security import generate_password_hash

import foms.api.orders as orders_api
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


def test_api_orders_nearby_success_contract_keys(client, monkeypatch) -> None:
    """Success path must expose by_distance/by_date/by_combined + radius/ref coords (no Kakao)."""
    import foms.api.orders.nearby as nearby_module

    _login_as_admin(client, "orders-contract-nearby-success")

    monkeypatch.setattr(
        nearby_module,
        "resolve_nearby_start_coordinates",
        lambda *args, **kwargs: (37.5, 127.0),
    )
    fixed = {
        "success": True,
        "by_distance": [],
        "by_date": [],
        "by_combined": [],
        "search_radius_km": 30.0,
        "ref_lat": 37.5,
        "ref_lng": 127.0,
    }
    monkeypatch.setattr(
        nearby_module,
        "compute_construction_nearby_success_payload",
        lambda **kwargs: fixed.copy(),
    )
    monkeypatch.setattr(
        nearby_module,
        "load_construction_nearby_valid_items",
        lambda *args, **kwargs: [],
    )

    response = client.get(
        "/api/orders/nearby",
        query_string={"address": "Seoul Test Ward", "date": "2026-05-10"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert set(payload.keys()) >= {
        "by_distance",
        "by_date",
        "by_combined",
        "search_radius_km",
        "ref_lat",
        "ref_lng",
    }
    assert payload["ref_lat"] == 37.5
    assert payload["ref_lng"] == 127.0


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


def test_update_order_field_allows_construction_type_for_regional_dashboard(client) -> None:
    """Regional dashboard inline construction-type edits must be reachable."""
    _login_as_admin(client, "orders-contract-construction-type-admin")
    order = _create_order(is_regional=True, construction_type=None, structured_data={})

    response = client.post(
        "/api/update_order_field",
        json={"order_id": order.id, "field": "construction_type", "value": "협력사 시공"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["normalized_value"] == "협력사 시공"

    db_session.expire_all()
    saved_order = db_session.get(Order, order.id)
    assert saved_order is not None
    assert saved_order.construction_type == "협력사 시공"


def test_update_order_field_rejects_unknown_construction_type(client) -> None:
    """Regional dashboard filters only understand the two canonical construction types."""
    _login_as_admin(client, "orders-contract-construction-type-invalid-admin")
    order = _create_order(is_regional=True, construction_type=None, structured_data={})
    order_id = order.id

    response = client.post(
        "/api/update_order_field",
        json={"order_id": order_id, "field": "construction_type", "value": "기타"},
    )

    assert response.status_code == 409
    payload = response.get_json()
    assert payload["success"] is False
    assert "시공 구분" in payload["message"]

    db_session.expire_all()
    saved_order = db_session.get(Order, order_id)
    assert saved_order is not None
    assert saved_order.construction_type is None


def test_update_order_field_rejects_blank_construction_type_for_regional_order(client) -> None:
    """Regional orders must not be left in dashboard-mismatching 미지정 state."""
    _login_as_admin(client, "orders-contract-construction-type-blank-admin")
    order = _create_order(is_regional=True, construction_type="하우드 시공", structured_data={})
    order_id = order.id

    response = client.post(
        "/api/update_order_field",
        json={"order_id": order_id, "field": "construction_type", "value": ""},
    )

    assert response.status_code == 409
    payload = response.get_json()
    assert payload["success"] is False
    assert "지방주문 구분" in payload["message"]

    db_session.expire_all()
    saved_order = db_session.get(Order, order_id)
    assert saved_order is not None
    assert saved_order.construction_type == "하우드 시공"


def test_update_order_field_rejects_construction_type_for_non_regional_order(client) -> None:
    """Non-regional orders may clear stale construction_type, but cannot set a regional bucket."""
    _login_as_admin(client, "orders-contract-construction-type-non-regional-admin")
    order = _create_order(is_regional=False, construction_type=None, structured_data={})
    order_id = order.id

    response = client.post(
        "/api/update_order_field",
        json={"order_id": order_id, "field": "construction_type", "value": "하우드 시공"},
    )

    assert response.status_code == 409
    payload = response.get_json()
    assert payload["success"] is False
    assert "비지방 주문" in payload["message"]

    db_session.expire_all()
    saved_order = db_session.get(Order, order_id)
    assert saved_order is not None
    assert saved_order.construction_type is None


def test_legacy_edit_rejects_blank_construction_type_for_regional_order(client) -> None:
    """Legacy edit form must follow the same regional construction-type contract."""
    _login_as_admin(client, "orders-contract-legacy-edit-construction-type-admin")
    order = _create_order(is_regional=True, construction_type="협력사 시공", structured_data={})
    order_id = order.id

    response = client.post(
        f"/edit/{order_id}",
        data={"is_regional": "on", "construction_type": ""},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "error"

    db_session.expire_all()
    saved_order = db_session.get(Order, order_id)
    assert saved_order is not None
    assert saved_order.is_regional is True
    assert saved_order.construction_type == "협력사 시공"


def test_update_order_field_manager_name_syncs_structured_data_for_erp_order(client) -> None:
    """ERP order manager-name updates must keep flat/structured data in sync."""
    _login_as_admin(client, "orders-contract-manager-erp-order-admin")
    order = _create_order(is_erp_order=True, structured_data={})

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
