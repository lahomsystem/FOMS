"""알림 받는 사람 공통 규칙 · 프리랜서 지정 옆길(FCOMM-01 겹 5).

설계서 docs/specs/2026-11-06-freelancer-sales-commission_SPEC.md §6.3 겹 5 · §6.5 "알림: 팀 대상 알림 · 공지 · 도면 전달
(담당 불일치)에서 프리랜서 소켓 전송 0", 검수 원장 A4 · A5.

* 전체 · 역할 · 팀 대상: 켜진 프리랜서는 state 줄(종 · 폰)에도, 실시간 소켓 대상에도 없다. 두 집합은 같다.
* 담당 이름 대상: 이름이 같아도 연결 줄이 없는 주문이면 프리랜서는 받지 않는다(J8). 연결된 주문이면 받는다.
* 사람 지정(USER) 대상: 그대로 받는다.
* 공지 팀 펼침(``/erp/api/notifications/send``): 프리랜서 줄 · 소켓 전송 0.
* 지정: 채팅방 회원 해제 · 옛 알림 숨김 · 감사 줄 숫자 · 두 번 저장해도 같음 · 열린 실시간 연결 끊김.
대조군(같은 모집단): 프리랜서 아닌 영업 직원 · 관리자. 모든 이름은 가짜 값이다.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from db import db_session
from foms.api.notifications import resolve_notification_recipient_user_ids
from foms.services.auth.freelancer_designation import keeps_notification
from foms.services.datetime_kst import get_today_kst
from foms.services.notifications.recipients import fan_out_new_notification, resolve_recipients_for_notification
from foms.services.sales_commission.settings import load_settings, save_freelancer
from models import (
    ChatRoom,
    ChatRoomMember,
    Notification,
    NotificationRecipientSource,
    NotificationUserState,
    Order,
    OrderFreelancerLink,
    SecurityLog,
)
from tests.domains.test_auth_finance import _login, _make_user

MATCH = "가짜프리N"        # 프리랜서 설정의 맞출 이름
USER_NAME = "가짜영업N"    # 프리랜서 계정 표시 이름 — 이 이름이 담당인 남의 주문이 있다
WRITE_HEADERS = {"X-FOMS-Notification-Write": "1"}
API = "/api/admin/sales-freelancers"


def _order(customer: str, manager: str) -> int:
    today = get_today_kst().isoformat()
    sd = {"parties": {"manager": {"name": manager}, "customer": {"name": customer}, "orderer": {"name": "라홈"}},
          "workflow": {"stage": "MEASURE"}}
    order = Order(received_date=today, customer_name=customer, phone="010-0000-0000", address="가짜시",
                  product="가짜장", status="MEASURE", manager_name=manager, is_erp_order=True, structured_data=sd,
                  erp_stage_code="MEASURE")
    db_session.add(order)
    db_session.commit()
    return order.id


def _designate(user_id: int, match: str) -> None:
    save_freelancer(db_session, user_id, {"match_name": match, "start_month": "2020-01", "tax_type": "NONE",
                                          "active": True},
                    base_version=load_settings(db_session)[0], actor_user_id=None)
    db_session.commit()


def _named(role: str, team, name: str) -> SimpleNamespace:
    user = _make_user(role, team)
    user.name = name
    db_session.commit()
    return SimpleNamespace(id=user.id, username=user.username, role=role, team=team, name=name)


def _notification(**kw) -> Notification:
    base = {"notification_type": "TEST_NOTE", "target_type": "ORDER", "title": "가짜 알림"}
    base.update(kw)
    note = Notification(**base)
    db_session.add(note)
    db_session.flush()
    return note


def _state_ids(note) -> set[int]:
    return {uid for uid, _src in resolve_recipients_for_notification(db_session, note)}


def _realtime_ids(note, include_admin: bool) -> set[int]:
    """같은 알림을 실시간 쪽 함수에 넣었을 때의 대상(호출하는 곳들이 넘기는 인자 그대로)."""
    return resolve_notification_recipient_user_ids(
        db_session, target_type=note.target_type, target_team=note.target_team,
        target_manager_name=note.target_manager_name, target_role=note.target_role,
        target_user_ids=[note.target_user_id] if note.target_user_id else None,
        include_admin=include_admin, order_id=note.order_id,
    )


@pytest.fixture()
def world(app):
    """프리랜서(계정 이름 USER_NAME · 맞출 이름 MATCH) · 영업 직원 · 관리자 + 내 주문 · 남의 주문(담당 = 내 계정 이름)."""
    fl = _named("STAFF", "SALES", USER_NAME)
    _designate(fl.id, MATCH)
    staff = _named("STAFF", "SALES", "다른영업N")
    admin = _named("ADMIN", "CS", "가짜관리N")
    own = _order("본인고객N", MATCH)          # 저장 훅이 MANAGER_PRIMARY 연결
    other = _order("남고객N", USER_NAME)      # 이름만 같은 남의 주문 — 연결 없음
    assert db_session.query(OrderFreelancerLink).filter_by(order_id=own, user_id=fl.id).count() == 1
    assert db_session.query(OrderFreelancerLink).filter_by(order_id=other, user_id=fl.id).count() == 0
    return SimpleNamespace(fl=fl, staff=staff, admin=admin, own=own, other=other)


# --------------------------------------------------------------------------
# 넓은 경로 — state 줄과 실시간 대상이 같고, 프리랜서는 둘 다 없다
# --------------------------------------------------------------------------
@pytest.mark.parametrize("kw", [
    {"target_type": "TEAM", "target_team": "SALES"},
    {"target_type": "TEAM", "target_team": "MEASURE"},
    {"target_type": "ALL"},
    {"target_type": "ROLE", "target_role": "STAFF"},
    {"target_type": "ORDER", "target_team": "SALES"},  # 도면 전달 담당 불일치 → 영업팀 대상(A4)
])
def test_broad_targets_exclude_freelancer_in_states_and_realtime(app, world, kw):
    note = _notification(order_id=world.own, **kw)
    states = _state_ids(note)
    realtime = _realtime_ids(note, include_admin=False)
    assert world.fl.id not in states and world.fl.id not in realtime
    assert world.staff.id in states                      # 대조군: 프리랜서 아닌 영업 직원
    assert realtime == states                            # 소켓 대상 == state 수신자
    with_admin = _realtime_ids(note, include_admin=True)
    assert world.fl.id not in with_admin and with_admin - states <= {world.admin.id}
    db_session.rollback()


def test_fan_out_states_skip_freelancer(app, world):
    note = _notification(target_type="TEAM", target_team="SALES")
    created = {s.user_id for s in fan_out_new_notification(db_session, note)}
    db_session.commit()
    assert world.staff.id in created and world.fl.id not in created


# --------------------------------------------------------------------------
# 담당 이름 경로 — 연결 줄이 있어야
# --------------------------------------------------------------------------
@pytest.mark.parametrize("target_name,order_attr,expected", [
    (MATCH, "own", True),          # 맞출 이름 · 연결된 주문
    (USER_NAME, "own", True),      # 계정 이름이어도 연결된 주문이면
    (USER_NAME, "other", False),   # 이름만 같은 남의 주문(J8)
    (MATCH, "other", False),       # 맞출 이름이어도 연결이 없으면
    (USER_NAME, None, False),      # 주문을 모르면 받지 않는다
])
def test_manager_name_target_needs_link(app, world, target_name, order_attr, expected):
    order_id = getattr(world, order_attr) if order_attr else None
    note = _notification(target_manager_name=f"{target_name}, 다른영업N", order_id=order_id)
    states = _state_ids(note)
    realtime = _realtime_ids(note, include_admin=False)
    assert (world.fl.id in states) is expected
    assert realtime == states
    assert world.staff.id in states                      # 대조군: 이름이 같은 직원은 그대로
    db_session.rollback()


def test_manager_name_state_source_is_manager_name(app, world):
    note = _notification(target_manager_name=MATCH, order_id=world.own)
    assert dict(resolve_recipients_for_notification(db_session, note)) == {
        world.fl.id: NotificationRecipientSource.TARGET_MANAGER_NAME}
    db_session.rollback()


def test_user_target_unchanged(app, world):
    note = _notification(target_type="USER", target_user_id=world.fl.id, order_id=world.own)
    assert _state_ids(note) == {world.fl.id} == _realtime_ids(note, include_admin=False)
    db_session.rollback()


def test_drawing_transfer_mismatch_realtime_excludes_freelancer(app, world):
    """도면 전달 실시간 경로(erp_orders_drawing)가 넘기는 인자 그대로 — 영업팀 대상 + 관리자."""
    ids = resolve_notification_recipient_user_ids(db_session, target_team="SALES", target_manager_name=None,
                                                  include_admin=True, order_id=world.other)
    assert world.fl.id not in ids and {world.staff.id, world.admin.id} <= ids


# --------------------------------------------------------------------------
# 공지 팀 펼침 + 실제 소켓 전송
# --------------------------------------------------------------------------
def _ws(app, user):
    from app import socketio

    http = app.test_client()
    _login(http, user)
    client = socketio.test_client(app, flask_test_client=http)
    assert client.is_connected() is True
    client.get_received()
    return client


@pytest.mark.parametrize("body", [
    {"target_type": "TEAM", "target_team": "SALES"},
    {"target_type": "ALL"},
])
def test_notice_team_expansion_skips_freelancer_rows_and_socket(app, world, body):
    fl_ws, staff_ws = _ws(app, world.fl), _ws(app, world.staff)
    try:
        client = app.test_client()
        _login(client, world.admin)
        resp = client.post("/erp/api/notifications/send", json={"title": "가짜 공지", **body}, headers=WRITE_HEADERS)
        assert resp.status_code == 200, resp.get_data(as_text=True)
        rows = db_session.query(Notification).filter(Notification.title == "가짜 공지").all()
        targets = {n.target_user_id for n in rows}
        assert world.fl.id not in targets and world.staff.id in targets
        assert db_session.query(NotificationUserState).filter_by(user_id=world.fl.id).count() == 0
        assert [e for e in fl_ws.get_received() if e["name"] == "erp_notification"] == []
        assert [e for e in staff_ws.get_received() if e["name"] == "erp_notification"]  # 대조군
    finally:
        fl_ws.disconnect()
        staff_ws.disconnect()


def test_notice_user_target_still_reaches_freelancer(app, world):
    client = app.test_client()
    _login(client, world.admin)
    resp = client.post("/erp/api/notifications/send",
                       json={"title": "콕 집은 공지", "target_type": "USER", "target_user_ids": [world.fl.id]},
                       headers=WRITE_HEADERS)
    assert resp.status_code == 200
    assert db_session.query(NotificationUserState).filter_by(user_id=world.fl.id).count() == 1


# --------------------------------------------------------------------------
# 지정 옆길 — 채팅 회원 해제 · 옛 알림 숨김 · 감사 · 두 번 저장 · 실시간 연결 끊기
# --------------------------------------------------------------------------
def test_keeps_notification_rule():
    linked = {10}
    user, mgr = NotificationRecipientSource.TARGET_USER, NotificationRecipientSource.TARGET_MANAGER_NAME
    assert keeps_notification(user, 10, None, linked) is True
    assert keeps_notification(mgr, 10, None, linked) is True
    assert keeps_notification(user, None, None, linked) is True
    assert keeps_notification(user, 11, None, linked) is False
    assert keeps_notification(mgr, None, None, linked) is False
    assert keeps_notification(user, None, "SALES", linked) is False   # 팀 펼침 공지
    for broad in (NotificationRecipientSource.TARGET_TEAM, NotificationRecipientSource.TARGET_ROLE,
                  NotificationRecipientSource.TARGET_ALL, NotificationRecipientSource.LEGACY_BACKFILL):
        assert keeps_notification(broad, 10, None, linked) is False


def _state(user_id: int, **kw) -> int:
    note = _notification(**kw)
    fan_out_new_notification(db_session, note)
    db_session.commit()
    row = db_session.query(NotificationUserState).filter_by(notification_id=note.id, user_id=user_id).one()
    return row.id


def test_designation_removes_memberships_and_hides_old_states(app, world):
    from app import socketio

    sales = _named("STAFF", "SALES", MATCH + "2")  # 곧 프리랜서가 될 영업 직원(계정 이름 = 맞출 이름)
    match = sales.name
    admin_client = app.test_client()
    _login(admin_client, world.admin)
    own = _order("지정본인고객", match)            # 지정하면 연결된다
    other = _order("지정남고객", "아무개")
    for name in ("방1", "방2"):
        room = ChatRoom(name=name, created_by=world.staff.id)
        db_session.add(room)
        db_session.commit()
        db_session.add_all([ChatRoomMember(room_id=room.id, user_id=sales.id),
                            ChatRoomMember(room_id=room.id, user_id=world.staff.id)])
    db_session.commit()
    keep = {
        "direct": _state(sales.id, target_type="USER", target_user_id=sales.id),
        "direct_own": _state(sales.id, target_type="USER", target_user_id=sales.id, order_id=own),
        "manager_own": _state(sales.id, target_manager_name=match, order_id=own),
    }
    hide = {
        "team": _state(sales.id, target_type="TEAM", target_team="SALES"),
        "all": _state(sales.id, target_type="ALL"),
        "role": _state(sales.id, target_type="ROLE", target_role="STAFF"),
        "team_order": _state(sales.id, target_team="SALES", order_id=own),
        "direct_other": _state(sales.id, target_type="USER", target_user_id=sales.id, order_id=other),
        "manager_other": _state(sales.id, target_manager_name=match, order_id=other),
        "team_notice": _state(sales.id, target_type="USER", target_user_id=sales.id, target_team="SALES"),
    }
    staff_states_before = db_session.query(NotificationUserState).filter(
        NotificationUserState.user_id == world.staff.id, NotificationUserState.archived_at.is_(None)).count()
    ws = _ws(app, sales)
    assert ws.is_connected() is True

    version = load_settings(db_session)[0]
    resp = admin_client.post(API, json={"user_id": sales.id, "match_name": match, "start_month": "2020-01",
                                        "tax_type": "NONE", "active": True, "version": version})
    assert resp.status_code == 200, resp.get_json()
    db_session.expire_all()

    assert db_session.query(ChatRoomMember).filter_by(user_id=sales.id).count() == 0
    assert db_session.query(ChatRoomMember).filter_by(user_id=world.staff.id).count() == 2   # 대조군
    states = {s.id: s for s in db_session.query(NotificationUserState).filter_by(user_id=sales.id)}
    assert all(states[sid].archived_at is None for sid in keep.values()), keep
    assert all(states[sid].archived_at is not None for sid in hide.values()), hide
    assert db_session.query(NotificationUserState).filter(
        NotificationUserState.user_id == world.staff.id,
        NotificationUserState.archived_at.is_(None)).count() == staff_states_before   # 남의 state 는 그대로
    log = db_session.query(SecurityLog).filter_by(action="SALES_FREELANCER_SAVED", target_id=sales.id).one()
    assert log.detail["chat_memberships_removed"] == 2 and log.detail["notifications_hidden"] == len(hide)
    assert ws.is_connected() is False                   # 열린 실시간 연결을 끊었다
    assert not list(socketio.server.manager.get_participants("/", f"user_{sales.id}"))

    sales_client = app.test_client()
    _login(sales_client, sales)
    badge = sales_client.get("/erp/api/notifications/badge").get_json()
    assert badge["count"] == len(keep)

    # 두 번 저장해도 같다(이미 지운 회원 · 이미 숨긴 알림은 다시 세지 않는다).
    archived_at = {sid: states[sid].archived_at for sid in hide.values()}
    resp = admin_client.post(API, json={"user_id": sales.id, "match_name": match, "start_month": "2020-01",
                                        "tax_type": "NONE", "active": True, "version": version + 1})
    assert resp.status_code == 200, resp.get_json()
    db_session.expire_all()
    logs = db_session.query(SecurityLog).filter_by(action="SALES_FREELANCER_SAVED", target_id=sales.id) \
        .order_by(SecurityLog.id).all()
    assert logs[-1].detail["chat_memberships_removed"] == 0 and logs[-1].detail["notifications_hidden"] == 0
    again = {s.id: s.archived_at for s in db_session.query(NotificationUserState).filter_by(user_id=sales.id)}
    assert {sid: again[sid] for sid in hide.values()} == archived_at


def test_turning_off_does_not_touch_memberships(app, world):
    """끄는 저장(active=false)은 옆길 정리를 하지 않는다(대조군 — 지정할 때만)."""
    sales = _named("STAFF", "SALES", "끌영업N")
    room = ChatRoom(name="끌방", created_by=sales.id)
    db_session.add(room)
    db_session.commit()
    db_session.add(ChatRoomMember(room_id=room.id, user_id=sales.id))
    db_session.commit()
    admin_client = app.test_client()
    _login(admin_client, world.admin)
    resp = admin_client.post(API, json={"user_id": sales.id, "match_name": "끌영업N", "start_month": "2020-01",
                                        "tax_type": "NONE", "active": False,
                                        "version": load_settings(db_session)[0]})
    assert resp.status_code == 200, resp.get_json()
    assert db_session.query(ChatRoomMember).filter_by(user_id=sales.id).count() == 1
