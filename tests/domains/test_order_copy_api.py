"""ORDER-COPY-01 API 계약 (SQLite domains lane).

주문 복사가 raw ``Order()`` column clone 대신 create_order 를 경유해 **fresh identity**
(mutation_version=1·새 SALES owner 배정·RECEIVED quest·item UUID·GEOCODE outbox)를 부여하고,
서버 소유/운영 상태(상태·일정·도면·배정·견적 링크)와 첨부를 복제하지 않으며, 다건 복사가
all-or-none 임을 Flask 테스트 client + SQLite 로 고정한다. 실 PostgreSQL FOR UPDATE 정렬
lock·deadlock-free 는 ``tests/postgres/test_order_copy.py`` 가 담당한다.
"""

import datetime

from werkzeug.security import generate_password_hash

from db import db_session
from models import (
    DomainSideEffectOutbox,
    Order,
    OrderAssignment,
    OrderAttachment,
    OrderEvent,
    OrderItemIdentity,
    User,
)


def _make_user(username, *, role="ADMIN", team="CS", is_active=True) -> User:
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role=role,
        team=team,
        name=username,
        is_active=is_active,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user) -> None:
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


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


def test_copy_creates_fresh_erp_identity_and_drops_operational_state(client, monkeypatch):
    admin = _make_user("order-copy-admin", role="ADMIN", team="CS")
    sales = _make_user("order-copy-sales", role="STAFF", team="SALES")
    sales_id = sales.id
    _login(client, admin)
    original = _create_erp_order()
    original_id = original.id

    import foms.services.order_copy as order_copy_service

    monkeypatch.setattr(
        order_copy_service, "now_kst", lambda: datetime.datetime(2026, 7, 8, 12, 34)
    )

    response = client.post(
        "/api/orders/copy",
        json={"order_ids": [original_id], "owner_user_id": sales_id},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["copied"] == 1
    new_id = payload["orders"][0]["new_order_id"]
    assert new_id != original_id

    db_session.expire_all()
    copied = db_session.get(Order, new_id)
    original_saved = db_session.get(Order, original_id)

    # server-owned reset + fresh flat projection
    assert copied.is_erp_order is True
    assert copied.status == "RECEIVED"
    assert copied.mutation_version == 1
    assert copied.customer_name == "구조 고객"
    assert copied.phone == "010-3333-4444"
    assert copied.address == "대구 구조 주소"
    assert copied.product == "구조 제품"
    assert copied.received_date == "2026-07-08"
    assert copied.erp_stage_code == "RECEIVED"
    # 일정 미복사: schedule 을 버렸으므로 flat 실측/시공일도 비어야 한다.
    assert copied.measurement_date == ""
    assert copied.scheduled_date == ""

    sd = copied.structured_data
    assert sd["workflow"]["stage"] == "RECEIVED"
    assert "assignments" not in sd
    assert "shipment" not in sd
    assert "schedule" not in sd
    assert sd["flags"]["urgent"] is True
    assert sd["payment"]["deposit"] == "300,000"
    # totals 는 서버가 items/payment 로 재계산한다(클라이언트 값 폐기).
    assert sd["totals"]["items_total"] == 1200000
    assert sd["totals"]["shipping_price"] == 1200000
    assert sd["meta"]["created_via"] == "ORDER_COPY"
    assert sd["meta"]["copied_from_order_id"] == original_id
    assert "wdc_estimate_id" not in sd["meta"]
    assert "drawing_current_files" not in sd
    assert "drawing_transfer_history" not in sd
    # quest 는 원본(DRAWING)이 아니라 RECEIVED 로 새로 seed 된다.
    assert any(q.get("stage") == "RECEIVED" for q in sd["quests"])
    assert all(q.get("stage") != "DRAWING" for q in sd["quests"])

    # 원본은 불변(operational state 유출 0).
    assert original_saved.structured_data["workflow"]["stage"] == "DRAWING"

    # fresh identity: 새 SALES owner 배정·생성 event·item UUID·geocode outbox.
    owner_rows = (
        db_session.query(OrderAssignment)
        .filter_by(order_id=new_id, domain="SALES", active=True)
        .all()
    )
    assert len(owner_rows) == 1
    assert owner_rows[0].user_id == sales_id
    assert owner_rows[0].source == "INITIAL_OWNER"
    assert (
        db_session.query(OrderEvent)
        .filter_by(order_id=new_id, event_type="ORDER_CREATED")
        .count()
        == 1
    )
    assert (
        db_session.query(OrderItemIdentity)
        .filter_by(order_id=new_id, is_active=True)
        .count()
        == 1
    )
    assert (
        db_session.query(OrderEvent)
        .filter_by(order_id=new_id, event_type="ADDRESS_CHANGED")
        .count()
        == 1
    )
    assert (
        db_session.query(DomainSideEffectOutbox)
        .filter_by(effect_type="GEOCODE", status="PENDING")
        .count()
        == 1
    )

    # 첨부 미복사.
    assert (
        db_session.query(OrderAttachment).filter(OrderAttachment.order_id == new_id).count()
        == 0
    )


def test_copy_staff_self_owner_without_explicit_owner(client):
    staff = _make_user("order-copy-staff", role="STAFF", team="SALES")
    staff_id = staff.id
    _login(client, staff)
    original = _create_erp_order()

    response = client.post("/api/orders/copy", json={"order_ids": [original.id]})

    assert response.status_code == 200
    new_id = response.get_json()["orders"][0]["new_order_id"]
    owner = (
        db_session.query(OrderAssignment)
        .filter_by(order_id=new_id, domain="SALES", active=True)
        .one()
    )
    assert owner.user_id == staff_id


def test_copy_admin_without_owner_is_rejected(client):
    admin = _make_user("order-copy-noowner-admin", role="ADMIN", team="CS")
    _login(client, admin)
    original = _create_erp_order()

    response = client.post("/api/orders/copy", json={"order_ids": [original.id]})

    assert response.status_code == 403
    assert response.get_json()["success"] is False


def test_copy_all_or_none_on_missing_order(client):
    admin = _make_user("order-copy-aon-admin", role="ADMIN", team="CS")
    sales = _make_user("order-copy-aon-sales", role="STAFF", team="SALES")
    _login(client, admin)
    original = _create_erp_order()
    before = db_session.query(Order).count()

    response = client.post(
        "/api/orders/copy",
        json={"order_ids": [original.id, 999_999], "owner_user_id": sales.id},
    )

    assert response.status_code == 404
    assert response.get_json()["success"] is False
    db_session.expire_all()
    # 하나라도 없으면 전체 abort — partial commit 0(주문 수 불변).
    assert db_session.query(Order).count() == before


def test_copy_rejects_empty_selection(client):
    admin = _make_user("order-copy-empty-admin", role="ADMIN", team="CS")
    _login(client, admin)

    response = client.post("/api/orders/copy", json={"order_ids": []})

    assert response.status_code == 400
    assert response.get_json()["success"] is False


def test_copy_keeps_success_when_cache_invalidation_fails(client, monkeypatch):
    admin = _make_user("order-copy-cache-admin", role="ADMIN", team="CS")
    sales = _make_user("order-copy-cache-sales", role="STAFF", team="SALES")
    _login(client, admin)
    original = _create_erp_order()

    import foms.api.orders.copy as copy_api

    monkeypatch.setattr(
        copy_api,
        "invalidate_all_dashboard_slice_caches",
        lambda: (_ for _ in ()).throw(RuntimeError("cache unavailable")),
    )

    response = client.post(
        "/api/orders/copy",
        json={"order_ids": [original.id], "owner_user_id": sales.id},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["copied"] == 1
