"""생산팀 벨 알림 서비스·훅 계약 (B1).

- 게이트: 비생산 단계·비ERP → 무알림.
- 생성 + fan_out: 생산 단계 → PRODUCTION_ORDER_CHANGED, PRODUCTION 팀 유저 state 생성.
- debounce: 같은 order+type 60초 내 → 기존 row 갱신(신규 없음, actor 무관).
- 취소 알림: kind='cancelled'.
- 훅 4곳(구조화 PUT 헬퍼·field_update·도면 전달·휴지통 삭제) 각 1건.
"""

from __future__ import annotations

from werkzeug.security import generate_password_hash

from db import db_session
from models import Notification, NotificationUserState, Order, User
from foms.services.notifications.production_change import (
    NOTIFICATION_TYPE,
    apply_production_change_alert,
    finalize_production_change_alert,
)


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


def _make_order(
    *, stage: str = "생산", status: str | None = None, sd: dict | None = None, is_erp: bool = True
) -> Order:
    order = Order(
        received_date="2026-07-01",
        customer_name="알림 고객",
        phone="010-0000-0000",
        address="Seoul",
        product="붙박이장",
        status=status or ("PRODUCTION" if stage in ("생산", "PRODUCTION") else "RECEIVED"),
        manager_name="담당",
        is_erp_order=is_erp,
        structured_data=sd if sd is not None else {"workflow": {"stage": stage}, "parties": {"customer": {"name": "홍길동"}}},
        erp_stage_code=stage,
    )
    db_session.add(order)
    db_session.commit()
    return order


def _notifs(order_id: int) -> list[Notification]:
    return (
        db_session.query(Notification)
        .filter(Notification.order_id == order_id, Notification.notification_type == NOTIFICATION_TYPE)
        .all()
    )


# --- 게이트 ----------------------------------------------------------------


def test_gate_blocks_non_production_stage(app):
    order = _make_order(stage="MEASURE", status="MEASURE")
    notif, created = apply_production_change_alert(
        db_session, order, "construction_date", "7/20 → 7/28",
        actor_user_id=None, actor_name="tester",
    )
    assert notif is None and created is False
    assert _notifs(order.id) == []


def test_gate_blocks_non_erp(app):
    order = _make_order(stage="생산", is_erp=False)
    notif, created = apply_production_change_alert(
        db_session, order, "construction_date", "x",
        actor_user_id=None, actor_name="tester",
    )
    assert notif is None and created is False


# --- 생성 + fan_out --------------------------------------------------------


def test_creates_notification_and_fans_out_to_production_team(app):
    prod_user = _make_user("prod_bell", role="STAFF", team="PRODUCTION")
    order = _make_order(stage="생산")
    notif, created = apply_production_change_alert(
        db_session, order, "construction_date", "7/20 → 7/28",
        actor_user_id=None, actor_name="실측담당",
    )
    assert created is True
    assert notif is not None
    assert notif.notification_type == NOTIFICATION_TYPE
    assert notif.target_team == "PRODUCTION"
    assert "시공일 변경" in notif.title
    assert "7/20 → 7/28" in notif.message
    # PRODUCTION 팀 유저에게 state 생성(fan_out).
    states = (
        db_session.query(NotificationUserState)
        .filter(
            NotificationUserState.notification_id == notif.id,
            NotificationUserState.user_id == prod_user.id,
        )
        .all()
    )
    assert len(states) == 1


# --- debounce --------------------------------------------------------------


def test_debounce_updates_existing_within_60s(app):
    _make_user("prod_bell2", role="STAFF", team="PRODUCTION")
    order = _make_order(stage="생산")
    n1, c1 = apply_production_change_alert(
        db_session, order, "construction_date", "7/20 → 7/28",
        actor_user_id=1, actor_name="A",
    )
    db_session.commit()
    # 다른 actor 여도 같은 order+type 이면 병합(생산 알림은 팀 공지 성격).
    n2, c2 = apply_production_change_alert(
        db_session, order, "construction_date", "7/28 → 8/2",
        actor_user_id=2, actor_name="B",
    )
    assert c1 is True and c2 is False
    assert n1 is not None and n2 is not None and n1.id == n2.id
    assert len(_notifs(order.id)) == 1
    assert "8/2" in n2.message


def test_cancelled_kind_alert(app):
    order = _make_order(stage="생산", status="DELETED")
    notif, created = apply_production_change_alert(
        db_session, order, "cancelled", "",
        actor_user_id=None, actor_name="admin",
    )
    assert created is True
    assert "주문 취소" in notif.title


def test_finalize_is_safe(app):
    _make_user("prod_bell3", role="STAFF", team="PRODUCTION")
    order = _make_order(stage="생산")
    with app.test_request_context():
        notif, created = apply_production_change_alert(
            db_session, order, "drawing", "도면 재전달",
            actor_user_id=None, actor_name="도면팀",
        )
        db_session.commit()
        # push/realtime 미구성 환경에서도 예외 없이 통과해야 한다.
        finalize_production_change_alert(db_session, notif, created_new=created)


# --- 훅 4곳 ----------------------------------------------------------------


def test_hook_structured_helper_emits(app):
    from foms.api.erp_orders_structured import _emit_production_change_if_needed

    order = _make_order(stage="생산")
    old_sd = {"schedule": {"construction": {"date": "2026-07-20"}}}
    new_sd = {"schedule": {"construction": {"date": "2026-07-28"}}}
    with app.test_request_context():
        notif, created = _emit_production_change_if_needed(db_session, order, old_sd, new_sd)
    assert created is True
    assert notif is not None and notif.notification_type == NOTIFICATION_TYPE
    assert "7/20 → 7/28" in notif.message


def test_hook_field_update_scheduled_date(client):
    user = _make_user("fu_bell", role="ADMIN")
    _login(client, user)
    order_id = _make_order(
        stage="생산",
        sd={"workflow": {"stage": "생산"}, "schedule": {"construction": {"date": "2026-07-20"}}, "parties": {"customer": {"name": "홍"}}},
    ).id

    resp = client.post(
        "/api/update_order_field",
        json={"order_id": order_id, "field": "scheduled_date", "value": "2026-07-28"},
    )
    assert resp.status_code == 200
    assert len(_notifs(order_id)) == 1


def test_hook_drawing_transfer(app):
    from foms.api.drawing.erp_orders_drawing import perform_drawing_transfer

    user = _make_user("tr_bell", role="ADMIN")
    order = _make_order(
        stage="생산",
        sd={
            "workflow": {"stage": "생산"},
            "parties": {"customer": {"name": "홍"}, "manager": {"name": "영업 김"}},
            "assignments": {"drawing_assignee_user_ids": [user.id]},
        },
    )
    with app.test_request_context():
        payload, status = perform_drawing_transfer(
            db_session, order, order.id, user, user.id,
            note="재전달", files=[{"key": "k1", "filename": "d1.png"}],
        )
    assert payload.get("success") is True
    assert len(_notifs(order.id)) == 1


def test_hook_trash_delete_order(client):
    user = _make_user("trash_bell", role="ADMIN")
    _login(client, user)
    order_id = _make_order(stage="생산").id

    resp = client.get(f"/delete/{order_id}", follow_redirects=False)
    assert resp.status_code in (302, 303)
    notifs = _notifs(order_id)
    assert len(notifs) == 1
    assert "주문 취소" in notifs[0].title
