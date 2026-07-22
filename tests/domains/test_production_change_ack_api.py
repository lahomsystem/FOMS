"""생산 변경 확인 ack API + field_update 이벤트 + 시공일 정렬 계약.

- POST /api/orders/<id>/production/change-ack: 정상 기록, 삭제 주문 허용, 권한(DRAWING 403).
- field_update scheduled_date: 값 변경 시 CONSTRUCTION_DATE_CHANGED OrderEvent 기록(근본수정).
- 생산 대시보드 정렬: erp_construction_date asc nulls last, created_at desc.
"""

from __future__ import annotations

import datetime

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderEvent, User
from foms.services.production_read_model import build_production_orders_query


def _make_user(username: str, *, role: str = "ADMIN", team: str | None = None) -> User:
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role=role,
        team=team,
        name=f"{username} 이름",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user: User) -> None:
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _make_order(*, status: str = "PRODUCTION", stage: str = "PRODUCTION", sd: dict | None = None, deleted_at: str | None = None) -> Order:
    order = Order(
        received_date="2026-07-01",
        customer_name="ack 고객",
        phone="010-0000-0000",
        address="Seoul",
        product="붙박이장",
        status=status,
        manager_name="담당",
        is_erp_order=True,
        structured_data=sd if sd is not None else {"workflow": {"stage": stage}},
        erp_stage_code=stage,
        deleted_at=deleted_at,
    )
    db_session.add(order)
    db_session.commit()
    return order


# --- ack API ----------------------------------------------------------------


def test_change_ack_records_event(client):
    user = _make_user("ack_admin", role="ADMIN")
    user_id = user.id
    _login(client, user)
    order_id = _make_order().id

    resp = client.post(f"/api/orders/{order_id}/production/change-ack")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["data"] == {"order_id": order_id}

    events = (
        db_session.query(OrderEvent)
        .filter(OrderEvent.order_id == order_id, OrderEvent.event_type == "PRODUCTION_CHANGE_ACK")
        .all()
    )
    assert len(events) == 1
    assert events[0].payload["source"] == "tablet_kanban"
    assert "deleted_at" not in events[0].payload  # 활성 주문은 마커 없음
    assert events[0].created_by_user_id == user_id


def test_change_ack_allowed_on_deleted_order(client):
    user = _make_user("ack_admin2", role="ADMIN")
    _login(client, user)
    order_id = _make_order(status="DELETED", stage="생산", deleted_at="2026-07-20 12:00:00").id

    resp = client.post(f"/api/orders/{order_id}/production/change-ack")
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True
    events = (
        db_session.query(OrderEvent)
        .filter(OrderEvent.order_id == order_id, OrderEvent.event_type == "PRODUCTION_CHANGE_ACK")
        .all()
    )
    assert len(events) == 1
    # 삭제 주문 ack 는 deleted_at 마커를 심는다(묘비 확인 판정용).
    assert events[0].payload["deleted_at"] == "2026-07-20 12:00:00"


def test_change_ack_forbidden_for_drawing_team(client):
    user = _make_user("ack_draw", role="STAFF", team="DRAWING")
    _login(client, user)
    order_id = _make_order().id
    resp = client.post(f"/api/orders/{order_id}/production/change-ack")
    assert resp.status_code == 403
    assert resp.get_json()["success"] is False


def test_change_ack_missing_order_404(client):
    user = _make_user("ack_admin3", role="ADMIN")
    _login(client, user)
    resp = client.post("/api/orders/999999/production/change-ack")
    assert resp.status_code == 404
    assert resp.get_json()["success"] is False


# --- field_update 근본수정: CONSTRUCTION_DATE_CHANGED --------------------------


def test_field_update_scheduled_date_records_construction_event(client):
    user = _make_user("fu_admin", role="ADMIN")
    _login(client, user)
    order_id = _make_order(
        sd={"workflow": {"stage": "생산"}, "schedule": {"construction": {"date": "2026-07-20"}}},
        stage="생산",
    ).id

    resp = client.post(
        "/api/update_order_field",
        json={"order_id": order_id, "field": "scheduled_date", "value": "2026-07-28"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True

    events = (
        db_session.query(OrderEvent)
        .filter(OrderEvent.order_id == order_id, OrderEvent.event_type == "CONSTRUCTION_DATE_CHANGED")
        .all()
    )
    assert len(events) == 1
    assert events[0].payload == {"from": "2026-07-20", "to": "2026-07-28"}


def test_field_update_scheduled_date_no_event_when_unchanged(client):
    user = _make_user("fu_admin2", role="ADMIN")
    _login(client, user)
    order_id = _make_order(
        sd={"workflow": {"stage": "생산"}, "schedule": {"construction": {"date": "2026-07-20"}}},
        stage="생산",
    ).id

    resp = client.post(
        "/api/update_order_field",
        json={"order_id": order_id, "field": "scheduled_date", "value": "2026-07-20"},
    )
    assert resp.status_code == 200
    events = (
        db_session.query(OrderEvent)
        .filter(OrderEvent.order_id == order_id, OrderEvent.event_type == "CONSTRUCTION_DATE_CHANGED")
        .all()
    )
    assert events == []


# --- 정렬: erp_construction_date asc nulls last -----------------------------


def test_production_sort_construction_date_asc_nulls_last(app):
    user = _make_user("sort_admin", role="ADMIN")

    def _mk(cdate: str | None, created: datetime.datetime) -> int:
        o = Order(
            received_date="2026-07-01",
            customer_name="정렬",
            phone="010-0000-0000",
            address="Seoul",
            product="p",
            status="PRODUCTION",
            is_erp_order=True,
            structured_data={"workflow": {"stage": "생산"}},
            erp_stage_code="생산",
            erp_construction_date=cdate,
            created_at=created,
        )
        db_session.add(o)
        db_session.commit()
        return o.id

    id_aug = _mk("2026-08-01", datetime.datetime(2026, 7, 1, 9, 0, 0))
    id_null = _mk(None, datetime.datetime(2026, 7, 2, 9, 0, 0))
    id_jul = _mk("2026-07-25", datetime.datetime(2026, 7, 3, 9, 0, 0))

    _q = build_production_orders_query(db_session, user, None, None, False)
    _q = _q.order_by(
        Order.erp_construction_date.asc().nulls_last(),
        Order.created_at.desc(),
    )
    ordered_ids = [o.id for o in _q.all()]
    assert ordered_ids == [id_jul, id_aug, id_null]
