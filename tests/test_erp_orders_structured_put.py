from werkzeug.security import generate_password_hash

from apps.api import erp_orders_structured
from db import db_session
from models import Order, User
import foms.services.channel_delivery as channel_delivery_service


def _login_as_admin(client, username="erp-structured-admin"):
    user = User(
        username=username,
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="ERP Structured Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role

    return user


def _structured_payload(address: str) -> dict:
    return {
        "workflow": {"stage": "RECEIVED"},
        "shipment": {},
        "parties": {
            "customer": {
                "name": "홍길동",
                "phone": "010-1234-5678",
            }
        },
        "site": {
            "address_full": address,
            "address_main": address,
            "address_detail": "",
        },
    }


def _create_order(*, address="서울 테헤란로 123", structured_data=None) -> Order:
    order = Order(
        received_date="2026-04-11",
        customer_name="홍길동",
        phone="010-1234-5678",
        address=address,
        product="붙박이장",
        status="RECEIVED",
        is_erp_beta=True,
        structured_data=structured_data if structured_data is not None else _structured_payload(address),
        lat=37.5,
        lng=127.0,
        geocode_status="success",
    )
    db_session.add(order)
    db_session.commit()
    return order


def test_structured_put_skips_channel_side_effects_when_structured_data_missing(client, monkeypatch):
    _login_as_admin(client)
    order = _create_order()
    order_id = order.id
    original_structured = order.structured_data

    payload_calls = []
    mark_calls = []
    geocode_calls = []
    push_calls = []

    monkeypatch.setattr(
        erp_orders_structured,
        "build_structured_update_payload",
        lambda *args, **kwargs: payload_calls.append((args, kwargs)) or {"event_type": "order_updated"},
    )
    monkeypatch.setattr(
        channel_delivery_service,
        "mark_order_updated_for_channel",
        lambda *args, **kwargs: mark_calls.append((args, kwargs)) or 99,
    )
    monkeypatch.setattr(
        erp_orders_structured,
        "enqueue_geocode_order_address",
        lambda order_id: geocode_calls.append(order_id),
    )
    monkeypatch.setattr(
        erp_orders_structured,
        "enqueue_channeltalk_push",
        lambda delivery_id: push_calls.append(delivery_id),
    )

    response = client.put(
        f"/api/orders/{order_id}/structured",
        json={"notes": "structured data 없이 메모만 수정"},
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert payload_calls == []
    assert mark_calls == []
    assert geocode_calls == []
    assert push_calls == []

    db_session.expire_all()
    saved_order = db_session.get(Order, order_id)
    assert saved_order is not None
    assert saved_order.notes == "structured data 없이 메모만 수정"
    assert saved_order.structured_data == original_structured


def test_structured_put_resets_geocode_when_address_is_cleared(client, monkeypatch):
    _login_as_admin(client, username="erp-structured-address-clear")
    order = _create_order()
    order_id = order.id

    geocode_calls = []
    push_calls = []
    reset_calls = []

    monkeypatch.setattr(erp_orders_structured, "_handle_stage_transition", lambda *args, **kwargs: None)
    monkeypatch.setattr(erp_orders_structured, "_record_structured_events", lambda *args, **kwargs: None)
    monkeypatch.setattr(erp_orders_structured, "_apply_structured_side_effects", lambda *args, **kwargs: None)
    monkeypatch.setattr(erp_orders_structured, "_finalize_draft_state", lambda *args, **kwargs: False)
    monkeypatch.setattr(erp_orders_structured, "sync_erp_flat_columns", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        erp_orders_structured,
        "build_structured_update_payload",
        lambda *args, **kwargs: {"event_type": "order_updated"},
    )
    monkeypatch.setattr(channel_delivery_service, "mark_order_updated_for_channel", lambda *args, **kwargs: None)

    original_reset = erp_orders_structured.reset_order_geocode_on_address_change

    def _capture_reset(order_obj, new_address):
        reset_calls.append(new_address)
        return original_reset(order_obj, new_address)

    monkeypatch.setattr(erp_orders_structured, "reset_order_geocode_on_address_change", _capture_reset)
    monkeypatch.setattr(
        erp_orders_structured,
        "enqueue_geocode_order_address",
        lambda order_id: geocode_calls.append(order_id),
    )
    monkeypatch.setattr(
        erp_orders_structured,
        "enqueue_channeltalk_push",
        lambda delivery_id: push_calls.append(delivery_id),
    )

    response = client.put(
        f"/api/orders/{order_id}/structured",
        json={
            "structured_data": _structured_payload(""),
            "structured_schema_version": 1,
        },
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert reset_calls == [""]
    assert geocode_calls == [order_id]
    assert push_calls == []

    db_session.expire_all()
    saved_order = db_session.get(Order, order_id)
    assert saved_order is not None
    assert saved_order.address == ""
    assert saved_order.lat is None
    assert saved_order.lng is None
    assert saved_order.geocode_status == "pending"
    assert (saved_order.structured_data or {}).get("site", {}).get("address_full") == ""
