"""생산 담당 팀 벨 알림 서비스·훅 계약 (B1).

- 게이트: 비생산 단계·비ERP → 무알림.
- 생성 + fan_out: 생산 단계 → PRODUCTION_ORDER_CHANGED, **TARGET_TEAMS 팀마다 row 1개**와
  그 팀 유저 state 생성.
- 무음 회귀 차단: 활성 사용자가 0명인 팀을 대상으로 삼으면 fan_out 이 0건이 되어 알림이
  아무에게도 안 간다(원래 PRODUCTION 팀이 그 상태였다). 팀 선택과 push 유형 등록을
  테스트로 고정한다.
- debounce: 같은 order+type+팀 60초 내 → 기존 row 갱신(신규 없음, actor 무관).
- 취소 알림: kind='cancelled'.
- 훅 4곳(구조화 PUT 헬퍼·field_update·도면 전달·휴지통 삭제) 각 팀 수만큼.
"""

from __future__ import annotations

from werkzeug.security import generate_password_hash

from db import db_session
from models import Notification, NotificationUserState, Order, User
from foms.services.notifications.production_change import (
    NOTIFICATION_TYPE,
    TARGET_TEAMS,
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


# --- 수신 팀 선택 (무음 회귀 차단) ------------------------------------------


def test_target_teams_are_teams_that_actually_have_users():
    """수신 팀은 PRODUCTION_EDIT 권한 팀 중 **실사용자가 있는** 팀이어야 한다.

    운영 DB 실측(2026-08-05): PRODUCTION·SHIPMENT 팀은 활성 사용자 0명이다. 그 팀을
    target 으로 두면 fan_out 이 0건 = notification_user_states 0행 = 무음 알림이 된다
    (ADMIN 은 팬아웃 대상이 아니라 관리자도 못 본다).
    """
    from foms.services.orders.order_mutation_policy import POLICY_REGISTRY

    policy_teams = set(POLICY_REGISTRY["PRODUCTION_EDIT"].teams)
    assert set(TARGET_TEAMS) <= policy_teams, "생산 권한이 없는 팀에 알림을 보내고 있다"
    assert "PRODUCTION" not in TARGET_TEAMS, "활성 사용자 0명인 팀 = 무음 알림"
    assert "SHIPMENT" not in TARGET_TEAMS, "활성 사용자 0명인 팀 = 무음 알림"
    assert TARGET_TEAMS, "수신 팀이 비어 있으면 알림이 통째로 사라진다"


def test_push_type_is_registered():
    """``_DEFAULT_P1_TYPES`` 미등재면 enqueue 해도 조용히 no-op 된다(푸시 무음)."""
    from foms.services.notifications.push_sender import _DEFAULT_P1_TYPES, _deep_link

    assert NOTIFICATION_TYPE in _DEFAULT_P1_TYPES

    # DB 없이 순수 객체로 판정한다(세션을 건드리면 실패가 다음 테스트로 번진다).
    notif = Notification(
        order_id=1, notification_type=NOTIFICATION_TYPE, target_type="TEAM",
        target_team=TARGET_TEAMS[0], title="t", message="m",
    )
    # 딥링크는 주문 상세가 아니라 생산 칸반이어야 한다(이 알림의 작업 화면).
    assert _deep_link(notif) == "/erp/production/dashboard"


# --- 게이트 ----------------------------------------------------------------


def test_gate_blocks_non_production_stage(app):
    order = _make_order(stage="MEASURE", status="MEASURE")
    notifs, created = apply_production_change_alert(
        db_session, order, "construction_date", "7/20 → 7/28",
        actor_user_id=None, actor_name="tester",
    )
    assert notifs == [] and created is False
    assert _notifs(order.id) == []


def test_gate_blocks_non_erp(app):
    order = _make_order(stage="생산", is_erp=False)
    notifs, created = apply_production_change_alert(
        db_session, order, "construction_date", "x",
        actor_user_id=None, actor_name="tester",
    )
    assert notifs == [] and created is False


# --- 생성 + fan_out --------------------------------------------------------


def test_creates_one_notification_per_team_and_fans_out(app):
    members = {
        team: _make_user(f"prod_bell_{team.lower()}", role="STAFF", team=team)
        for team in TARGET_TEAMS
    }
    order = _make_order(stage="생산")
    notifs, created = apply_production_change_alert(
        db_session, order, "construction_date", "7/20 → 7/28",
        actor_user_id=None, actor_name="실측담당",
    )
    assert created is True
    assert len(notifs) == len(TARGET_TEAMS)
    assert {n.target_team for n in notifs} == set(TARGET_TEAMS)
    for notif in notifs:
        assert notif.notification_type == NOTIFICATION_TYPE
        assert "시공일 변경" in notif.title
        assert "7/20 → 7/28" in notif.message
        # 그 팀 유저에게만 state 생성(fan_out) — 한 사용자는 팀 하나라 벨엔 1건.
        state_user_ids = {
            uid
            for (uid,) in db_session.query(NotificationUserState.user_id).filter(
                NotificationUserState.notification_id == notif.id
            )
        }
        assert state_user_ids == {members[notif.target_team].id}


def test_fan_out_reaches_every_target_team_member(app):
    """무음 회귀의 최종 판정 — 알림 1회로 전 대상 팀 사용자가 state 를 갖는다."""
    users = [
        _make_user(f"prod_fan_{team.lower()}", role="STAFF", team=team) for team in TARGET_TEAMS
    ]
    order = _make_order(stage="생산")
    notifs, _ = apply_production_change_alert(
        db_session, order, "construction_date", "7/20 → 7/28",
        actor_user_id=None, actor_name="실측담당",
    )
    reached = {
        uid
        for (uid,) in db_session.query(NotificationUserState.user_id).filter(
            NotificationUserState.notification_id.in_([n.id for n in notifs])
        )
    }
    assert reached == {u.id for u in users}


# --- debounce --------------------------------------------------------------


def test_debounce_updates_existing_within_60s(app):
    for team in TARGET_TEAMS:
        _make_user(f"prod_bell2_{team.lower()}", role="STAFF", team=team)
    order = _make_order(stage="생산")
    first, c1 = apply_production_change_alert(
        db_session, order, "construction_date", "7/20 → 7/28",
        actor_user_id=1, actor_name="A",
    )
    db_session.commit()
    # 다른 actor 여도 같은 order+type+팀 이면 병합(생산 알림은 팀 공지 성격).
    second, c2 = apply_production_change_alert(
        db_session, order, "construction_date", "7/28 → 8/2",
        actor_user_id=2, actor_name="B",
    )
    assert c1 is True and c2 is False
    assert [n.id for n in first] == [n.id for n in second]
    # 팀당 정확히 1개 — 팀을 debounce 조건에서 빼면 여기가 늘어난다.
    assert len(_notifs(order.id)) == len(TARGET_TEAMS)
    assert all("8/2" in n.message for n in second)


def test_cancelled_kind_alert(app):
    order = _make_order(stage="생산", status="DELETED")
    notifs, created = apply_production_change_alert(
        db_session, order, "cancelled", "",
        actor_user_id=None, actor_name="admin",
    )
    assert created is True
    assert all("주문 취소" in n.title for n in notifs)


def test_finalize_is_safe(app):
    for team in TARGET_TEAMS:
        _make_user(f"prod_bell3_{team.lower()}", role="STAFF", team=team)
    order = _make_order(stage="생산")
    with app.test_request_context():
        notifs, created = apply_production_change_alert(
            db_session, order, "drawing", "도면 재전달",
            actor_user_id=None, actor_name="도면팀",
        )
        db_session.commit()
        # push/realtime 미구성 환경에서도 예외 없이 통과해야 한다.
        finalize_production_change_alert(db_session, notifs, created_new=created)
        # 빈 리스트·None·구 계약(단일 객체) 전부 무예외.
        finalize_production_change_alert(db_session, [], created_new=False)
        finalize_production_change_alert(db_session, None, created_new=False)
        finalize_production_change_alert(db_session, notifs[0], created_new=False)


# --- 훅 4곳 ----------------------------------------------------------------


def test_hook_structured_helper_emits(app):
    from foms.api.erp_orders_structured import _emit_production_change_if_needed

    order = _make_order(stage="생산")
    old_sd = {"schedule": {"construction": {"date": "2026-07-20"}}}
    new_sd = {"schedule": {"construction": {"date": "2026-07-28"}}}
    with app.test_request_context():
        notifs, created = _emit_production_change_if_needed(db_session, order, old_sd, new_sd)
    assert created is True
    assert len(notifs) == len(TARGET_TEAMS)
    assert all(n.notification_type == NOTIFICATION_TYPE for n in notifs)
    assert all("7/20 → 7/28" in n.message for n in notifs)


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
    assert len(_notifs(order_id)) == len(TARGET_TEAMS)


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
    assert len(_notifs(order.id)) == len(TARGET_TEAMS)


def test_hook_trash_delete_order(client):
    user = _make_user("trash_bell", role="ADMIN")
    _login(client, user)
    order_id = _make_order(stage="생산").id

    resp = client.post(f"/delete/{order_id}", follow_redirects=False)
    assert resp.status_code in (302, 303)
    notifs = _notifs(order_id)
    assert len(notifs) == len(TARGET_TEAMS)
    assert all("주문 취소" in n.title for n in notifs)
