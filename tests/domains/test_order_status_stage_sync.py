"""단건/벌크 주문 상태 변경의 ERP stage 동기화 계약.

STATE-LEGACY-01 이후 **순수 메인 파이프라인 전이**(예: MEASURE→DRAWING)는 canonical
전이 엔진(``SET_MAIN_STAGE``)을 경유한다 — legacy ``STAGE_CHANGED`` event(payload from/to)
+ mutation_version++ + STATE_SET_MAIN_STAGE receipt + canonical projection(order.status)을
원자 기록한다. payload 의 ``manual``/``bulk`` 표식은 canonical 계약에서 제거됐고
(소비자 production_change_alerts/timeline 은 from/to 만 사용), ``command``/``emergency_override``
로 대체된다.

- 단건 POST /api/update_order_status(ERP 메인): canonical 전이 + STAGE_CHANGED from/to.
- 비ERP 주문 단건 변경: canonical 대상 아님 — structured_data 무터치 + STAGE_CHANGED 없음.
- 벌크 POST /api/bulk_update_order_status(ERP 메인): 주문별 canonical 전이 + STAGE_CHANGED.
"""

from __future__ import annotations

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderEvent, OrderMutationReceipt, User


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
    """단건 변경(메인 파이프라인): canonical 전이 + workflow.stage 동기화 + STAGE_CHANGED."""
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
    assert saved.mutation_version == 2  # canonical 전이 1회 bump(direct 배정 아님)
    assert (
        db_session.query(OrderMutationReceipt)
        .filter_by(policy_id="STATE_SET_MAIN_STAGE")
        .count()
        == 1
    )

    events = _stage_events(order_id)
    assert len(events) == 1
    assert events[0].payload["from"] == "MEASURE"
    assert events[0].payload["to"] == "DRAWING"
    assert events[0].payload["command"] == "SET_MAIN_STAGE"
    assert events[0].payload["emergency_override"] is False
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
    """벌크 변경(메인 파이프라인): 주문별 canonical 전이 + stage 동기화 + STAGE_CHANGED."""
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
    assert saved.mutation_version == 2  # canonical 전이 1회 bump

    events = _stage_events(order_id)
    assert len(events) == 1
    assert events[0].payload["from"] == "MEASURE"
    assert events[0].payload["to"] == "DRAWING"
    assert events[0].payload["command"] == "SET_MAIN_STAGE"
    assert events[0].created_by_user_id == user_id
