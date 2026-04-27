import copy

from werkzeug.security import generate_password_hash

from foms.api import erp_orders_structured
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
        "items": [{"product_name": "붙박이장"}],
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
        is_erp_order=True,
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


def test_structured_put_rejects_address_clear_before_geocode_reset(client, monkeypatch):
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

    assert response.status_code == 400
    data = response.get_json()
    assert data["success"] is False
    assert "주소" in data["message"]
    assert reset_calls == []
    assert geocode_calls == []
    assert push_calls == []

    db_session.expire_all()
    saved_order = db_session.get(Order, order_id)
    assert saved_order is not None
    assert saved_order.address == "서울 테헤란로 123"
    assert saved_order.lat == 37.5
    assert saved_order.lng == 127.0
    assert saved_order.geocode_status == "success"
    assert (saved_order.structured_data or {}).get("site", {}).get("address_full") == "서울 테헤란로 123"


def test_structured_put_skips_channel_when_payload_has_no_change_lines(client, monkeypatch):
    """채널 diff가 없으면 mark/enqueue 하지 않음 (무변경 저장 알림 방지)."""
    _login_as_admin(client, username="erp-structured-no-channel")
    order = _create_order()
    order_id = order.id

    mark_calls = []
    push_calls = []

    monkeypatch.setattr(erp_orders_structured, "_handle_stage_transition", lambda *a, **k: None)
    monkeypatch.setattr(erp_orders_structured, "_record_structured_events", lambda *a, **k: None)
    monkeypatch.setattr(erp_orders_structured, "_apply_structured_side_effects", lambda *a, **k: None)
    monkeypatch.setattr(erp_orders_structured, "_finalize_draft_state", lambda *a, **k: False)
    monkeypatch.setattr(erp_orders_structured, "sync_erp_flat_columns", lambda *a, **k: None)
    monkeypatch.setattr(
        erp_orders_structured,
        "build_structured_update_payload",
        lambda *args, **kwargs: {"event_type": "order_updated", "change_lines": []},
    )
    monkeypatch.setattr(
        channel_delivery_service,
        "mark_order_updated_for_channel",
        lambda *args, **kwargs: mark_calls.append(1) or 99,
    )
    monkeypatch.setattr(
        erp_orders_structured,
        "enqueue_channeltalk_push",
        lambda delivery_id: push_calls.append(delivery_id),
    )

    sd = copy.deepcopy(order.structured_data)
    response = client.put(
        f"/api/orders/{order_id}/structured",
        json={"structured_data": sd, "structured_schema_version": 1},
    )

    assert response.status_code == 200
    assert mark_calls == []
    assert push_calls == []


def test_erp_draft_create_is_hidden_from_active_orders_and_reused(client):
    _login_as_admin(client, username="erp-draft-hidden")

    response = client.post("/api/orders/erp/draft")

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["reused"] is False

    order_id = data["order_id"]
    db_session.expire_all()
    draft = db_session.get(Order, order_id)
    assert draft is not None
    assert draft.status == "DRAFT"
    assert (draft.structured_data or {}).get("meta", {}).get("draft") is True
    assert draft not in db_session.query(Order).filter(Order.active_filter()).all()

    reused = client.post("/api/orders/erp/draft")

    assert reused.status_code == 200
    reused_data = reused.get_json()
    assert reused_data["success"] is True
    assert reused_data["reused"] is True
    assert reused_data["order_id"] == order_id


def test_erp_draft_status_is_hidden_even_without_meta_marker(client):
    _login_as_admin(client, username="erp-draft-status-hidden")
    structured = _structured_payload("서울 테헤란로 123")
    structured["meta"] = {"draft": False}
    order = _create_order(structured_data=structured)
    order.status = "DRAFT"
    db_session.commit()

    db_session.expire_all()
    saved = db_session.get(Order, order.id)
    assert saved in db_session.query(Order).filter(Order.erp_draft_filter()).all()
    assert saved not in db_session.query(Order).filter(Order.active_filter()).all()


def test_structured_put_rejects_incomplete_draft_and_keeps_it_hidden(client):
    _login_as_admin(client, username="erp-draft-incomplete")
    created = client.post("/api/orders/erp/draft").get_json()
    order_id = created["order_id"]

    response = client.put(
        f"/api/orders/{order_id}/structured",
        json={
            "structured_data": {
                "workflow": {"stage": "RECEIVED"},
                "parties": {"customer": {"name": "홍길동", "phone": "010-1234-5678"}},
                "site": {"address_full": "서울 테헤란로 123", "address_main": "서울 테헤란로 123"},
                "items": [{"product_name": ""}],
            },
            "structured_schema_version": 1,
        },
    )

    assert response.status_code == 400
    data = response.get_json()
    assert data["success"] is False
    assert "제품명" in data["message"]

    db_session.expire_all()
    draft = db_session.get(Order, order_id)
    assert draft is not None
    assert draft.status == "DRAFT"
    assert (draft.structured_data or {}).get("meta", {}).get("draft") is True
    assert draft not in db_session.query(Order).filter(Order.active_filter()).all()


def test_structured_put_finalizes_draft_without_incoming_meta(client, monkeypatch):
    _login_as_admin(client, username="erp-draft-finalize")
    created = client.post("/api/orders/erp/draft").get_json()
    order_id = created["order_id"]

    monkeypatch.setattr(erp_orders_structured, "_record_structured_events", lambda *a, **k: None)
    monkeypatch.setattr(erp_orders_structured, "_apply_structured_side_effects", lambda *a, **k: None)
    monkeypatch.setattr(erp_orders_structured, "enqueue_geocode_order_address", lambda *a, **k: None)
    monkeypatch.setattr(erp_orders_structured, "enqueue_channeltalk_push", lambda *a, **k: None)
    monkeypatch.setattr(
        erp_orders_structured,
        "build_structured_update_payload",
        lambda *a, **k: {"event_type": "order_updated", "change_lines": []},
    )

    response = client.put(
        f"/api/orders/{order_id}/structured",
        json={
            "structured_data": _structured_payload("서울 테헤란로 123"),
            "structured_schema_version": 1,
            "received_date": "2026-04-27",
            "received_time": "09:30",
        },
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["draft_cleared"] is True

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved is not None
    assert saved.status == "RECEIVED"
    assert saved.customer_name == "홍길동"
    assert saved.phone == "010-1234-5678"
    assert saved.address == "서울 테헤란로 123"
    assert saved.product == "붙박이장"
    assert (saved.structured_data or {}).get("meta", {}).get("draft") is False
    assert saved in db_session.query(Order).filter(Order.active_filter()).all()

    with client.session_transaction() as sess:
        assert "erp_draft_order_id" not in sess


def test_payment_confirm_rejects_unfinalized_draft(client):
    _login_as_admin(client, username="erp-draft-payment")
    created = client.post("/api/orders/erp/draft").get_json()

    response = client.post(
        f"/api/orders/{created['order_id']}/payment-confirm",
        json={"type": "deposit", "confirmed": True},
    )

    assert response.status_code == 404
