import datetime

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderAttachment, User


def _login_as_admin(client, username="order-copy-admin"):
    user = User(
        username=username,
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="Order Copy Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role

    return user


def _create_erp_order() -> Order:
    order = Order(
        received_date="2026-07-08",
        received_time="09:10",
        customer_name="원본 고객",
        phone="010-1111-2222",
        address="서울 원본 주소",
        product="원본 제품",
        notes="원본 비고",
        status="DRAWING",
        is_regional=True,
        is_self_measurement=True,
        is_erp_order=True,
        raw_order_text="원본 주문 원문",
        structured_data={
            "workflow": {"stage": "DRAWING", "stage_updated_at": "2026-07-07T10:00:00"},
            "assignments": {
                "owner_team": "DRAWING",
                "drawing_assignee_user_ids": [99],
            },
            "shipment": {"construction_workers": ["원본 시공자"]},
            "flags": {"urgent": True, "urgent_reason": "테스트 긴급"},
            "schedule": {
                "measurement": {"date": "2026-07-13"},
                "construction": {"date": "2026-07-20"},
            },
            "parties": {
                "customer": {"name": "구조 고객", "phone": "010-3333-4444"},
                "manager": {"name": "구조 담당"},
            },
            "site": {"address_full": "대구 구조 주소"},
            "items": [{"product_name": "구조 제품", "price": "1,200,000"}],
            "payment": {"deposit": "300,000"},
            "totals": {"shipping_price": "1,200,000"},
            "drawing_current_files": [{"key": "drawing/original.png"}],
            "drawing_transfer_history": [{"at": "2026-07-07T11:00:00"}],
            "quests": [{"stage": "DRAWING", "title": "원본 퀘스트"}],
            "meta": {
                "draft": False,
                "created_via": "ERP_ORDER",
                "wdc_estimate_id": 123,
            },
        },
        structured_schema_version=1,
        structured_confidence="high",
    )
    db_session.add(order)
    db_session.flush()
    db_session.add(
        OrderAttachment(
            order_id=order.id,
            filename="original.png",
            file_type="image",
            category="drawing",
            storage_key="orders/original.png",
            file_size=1,
        )
    )
    db_session.commit()
    return order


def test_copy_orders_api_creates_new_erp_order_number_without_operational_state(client, monkeypatch):
    _login_as_admin(client)
    original = _create_erp_order()
    original_id = original.id
    import foms.services.order_copy as order_copy_service

    monkeypatch.setattr(
        order_copy_service,
        "now_kst",
        lambda: datetime.datetime(2026, 7, 8, 12, 34),
    )

    response = client.post("/api/orders/copy", json={"order_ids": [original_id]})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["copied"] == 1
    new_id = payload["orders"][0]["new_order_id"]
    assert new_id != original_id

    db_session.expire_all()
    copied = db_session.get(Order, new_id)
    original_saved = db_session.get(Order, original_id)

    assert copied is not None
    assert original_saved is not None
    assert copied.is_erp_order is True
    assert copied.status == "RECEIVED"
    assert copied.customer_name == "구조 고객"
    assert copied.phone == "010-3333-4444"
    assert copied.address == "대구 구조 주소"
    assert copied.product == "구조 제품"
    assert copied.received_date == "2026-07-08"

    sd = copied.structured_data
    assert sd["workflow"]["stage"] == "RECEIVED"
    assert sd["assignments"] == {}
    assert sd["shipment"] == {}
    assert sd["schedule"]["measurement"]["date"] == "2026-07-13"
    assert sd["schedule"]["construction"]["date"] == "2026-07-20"
    assert sd["payment"]["deposit"] == "300,000"
    assert sd["totals"]["shipping_price"] == "1,200,000"
    assert sd["meta"]["created_via"] == "ORDER_COPY"
    assert sd["meta"]["copied_from_order_id"] == original_id
    assert "wdc_estimate_id" not in sd["meta"]
    assert "drawing_current_files" not in sd
    assert "drawing_transfer_history" not in sd
    assert "quests" not in sd

    assert copied.erp_stage_code == "RECEIVED"
    assert copied.measurement_date == "2026-07-13"
    assert copied.scheduled_date == "2026-07-20"
    assert original_saved.structured_data["workflow"]["stage"] == "DRAWING"

    copied_attachments = (
        db_session.query(OrderAttachment).filter(OrderAttachment.order_id == new_id).count()
    )
    assert copied_attachments == 0


def test_copy_orders_api_rejects_empty_selection(client):
    _login_as_admin(client, username="order-copy-empty-admin")

    response = client.post("/api/orders/copy", json={"order_ids": []})

    assert response.status_code == 400
    assert response.get_json()["success"] is False


def test_copy_orders_api_keeps_success_when_cache_invalidation_fails(client, monkeypatch):
    _login_as_admin(client, username="order-copy-cache-admin")
    original = _create_erp_order()
    original_id = original.id

    import foms.api.orders.copy as copy_api

    monkeypatch.setattr(
        copy_api,
        "invalidate_all_dashboard_slice_caches",
        lambda: (_ for _ in ()).throw(RuntimeError("cache unavailable")),
    )

    response = client.post("/api/orders/copy", json={"order_ids": [original_id]})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["copied"] == 1
