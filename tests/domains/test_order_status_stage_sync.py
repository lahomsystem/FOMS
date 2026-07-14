"""단건/벌크 주문 상태 변경의 ERP stage 동기화 계약 (_sync_erp_stage 공용 헬퍼).

- 단건 POST /api/update_order_status: ERP 주문이면 workflow.stage 동기화 +
  STAGE_CHANGED(manual:true, bulk:false) 기록 (single/bulk 불일치 결함 봉합)
- 비ERP 주문 단건 변경: structured_data 무터치 + STAGE_CHANGED 없음
- 벌크 POST /api/bulk_update_order_status: 기존 동작 불변(stage 동기화 + bulk:true)
"""

from __future__ import annotations

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderEvent, User


def _login_admin(client, username: str) -> User:
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role="ADMIN",
        team="CS",
        name=f"{username} 이름",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _make_order(*, status: str = "MEASURE", is_erp_order: bool = True) -> Order:
    order = Order(
        received_date="2026-07-01",
        customer_name="스테이지 동기화 고객",
        phone="010-0000-0000",
        address="Seoul",
        product="붙박이장",
        status=status,
        manager_name="Alice",
        is_erp_order=is_erp_order,
        structured_data={"workflow": {"stage": status}, "shipment": {}},
    )
    db_session.add(order)
    db_session.commit()
    return order


def _stage_events(order_id: int) -> list[OrderEvent]:
    return (
        db_session.query(OrderEvent)
        .filter(OrderEvent.order_id == order_id, OrderEvent.event_type == "STAGE_CHANGED")
        .all()
    )


def test_single_update_syncs_erp_stage_and_records_event(client):
    """단건 변경(G2 핸드오프 플로우): stage 동기화 + STAGE_CHANGED bulk:false."""
    user_id = _login_admin(client, "stage_sync_admin").id
    order_id = _make_order(status="MEASURE").id

    resp = client.post(
        "/api/update_order_status",
        json={"order_id": order_id, "status": "DRAWING"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.status == "DRAWING"
    assert saved.structured_data["workflow"]["stage"] == "DRAWING"
    assert saved.structured_data["workflow"]["stage_updated_at"]

    events = _stage_events(order_id)
    assert len(events) == 1
    assert events[0].payload["from"] == "MEASURE"
    assert events[0].payload["to"] == "DRAWING"
    assert events[0].payload["manual"] is True
    assert events[0].payload["bulk"] is False
    assert events[0].created_by_user_id == user_id


def test_single_update_non_erp_order_leaves_sd_untouched(client):
    """비ERP 주문 단건 변경: status 만 바뀌고 sd 무터치, STAGE_CHANGED 없음."""
    _login_admin(client, "stage_sync_admin2")
    order_id = _make_order(status="MEASURE", is_erp_order=False).id

    resp = client.post(
        "/api/update_order_status",
        json={"order_id": order_id, "status": "DRAWING"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.status == "DRAWING"
    assert saved.structured_data["workflow"]["stage"] == "MEASURE"  # 무터치
    assert "stage_updated_at" not in saved.structured_data["workflow"]
    assert _stage_events(order_id) == []


def test_bulk_update_erp_stage_sync_unchanged(client):
    """벌크 변경 기존 동작 불변: stage 동기화 + STAGE_CHANGED bulk:true."""
    user_id = _login_admin(client, "stage_sync_admin3").id
    order_id = _make_order(status="MEASURE").id

    resp = client.post(
        "/api/bulk_update_order_status",
        json={"order_ids": [order_id], "status": "DRAWING"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["updated"] == 1

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.status == "DRAWING"
    assert saved.structured_data["workflow"]["stage"] == "DRAWING"

    events = _stage_events(order_id)
    assert len(events) == 1
    assert events[0].payload["from"] == "MEASURE"
    assert events[0].payload["to"] == "DRAWING"
    assert events[0].payload["manual"] is True
    assert events[0].payload["bulk"] is True
    assert events[0].created_by_user_id == user_id
