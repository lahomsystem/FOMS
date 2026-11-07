"""실시간 알림 연결 — 연결 때 서버가 본인 개인 방 ``user_<id>`` 에만 넣고, 알림은 그 방으로만 간다.

사내 채팅을 지우며(CHAT-DEL-01, 2026-11-07 — docs/specs/2026-11-07-internal-chat-removal_SPEC.md) 채팅 이벤트
(``join_room`` · ``leave_room`` · ``send_message`` · ``typing`` · ``mark_read``)가 없어졌다. 이제 손님 쪽이 방을 고르는
길이 아예 없다 — 예전 ``join_room`` 으로 남의 개인 방에 들어가 알림 사본을 받던 구멍(D19)도 같이 닫힌다.
로그인 안 함 · 비활성 · 협력사 계정은 연결을 받지 않는다(INACTIVE-SESSION-01 · PARTNER-01). 모든 이름은 가짜 값이다.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from db import db_session
from foms.services.notifications.realtime_notifications import emit_erp_notification_to_users, user_room
from foms.services.sales_commission.settings import load_settings, save_freelancer
from models import PartnerOrg, User
from tests.domains.test_auth_finance import _login, _make_user


def _socketio():
    from app import socketio

    return socketio


def _snap(user) -> SimpleNamespace:
    """로그인에 쓰는 값만 미리 떠 둔다 — 소켓 연결이 끝나면 DB 세션이 닫혀 행이 떨어진다."""
    return SimpleNamespace(id=user.id, username=user.username, role=user.role)


def _connect(app, user=None):
    http = app.test_client()
    if user is not None:
        _login(http, user)
    return _socketio().test_client(app, flask_test_client=http)


def _notify(app, user_id: int, title: str) -> None:
    with app.app_context():
        emit_erp_notification_to_users([user_id], {"title": title})


def _titles(client) -> list[str]:
    return [item["args"][0]["title"] for item in client.get_received() if item["name"] == "erp_notification"]


@pytest.fixture()
def clients():
    opened = []
    yield opened
    for client in opened:
        if client.is_connected():
            client.disconnect()


def test_connect_joins_own_room_and_only_own_notifications_arrive(app, clients):
    ga, na = _snap(_make_user("STAFF", "CS")), _snap(_make_user("STAFF", "SALES"))
    a, b = _connect(app, ga), _connect(app, na)
    clients += [a, b]
    assert a.is_connected() and b.is_connected()
    assert [i["name"] for i in a.get_received()] == ["connected"]
    b.get_received()
    _notify(app, ga.id, "가에게")
    assert _titles(a) == ["가에게"]
    assert _titles(b) == []  # 대조군: 남의 알림은 안 온다


def test_old_chat_events_cannot_join_someone_elses_room(app, clients):
    ga, na = _snap(_make_user("STAFF", "CS")), _snap(_make_user("STAFF", "CS"))
    na_id = na.id
    a = _connect(app, ga)
    clients.append(a)
    a.get_received()
    for event in ("join_room", "send_message", "typing", "mark_read", "leave_room"):
        a.emit(event, {"room_id": user_room(na_id), "content": "x"})
    assert a.get_received() == []  # 처리하는 곳이 없다 — 답도 방송도 없음
    _notify(app, na_id, "나에게")
    assert _titles(a) == []


def test_freelancer_connects_and_gets_own_notifications(app, clients):
    fl = _make_user("STAFF", "SALES")
    save_freelancer(db_session, fl.id, {"match_name": "가짜프리연결", "start_month": "2020-01", "tax_type": "NONE",
                                        "active": True},
                    base_version=load_settings(db_session)[0], actor_user_id=None)
    db_session.commit()
    fl = _snap(fl)
    fl_id = fl.id
    c = _connect(app, fl)
    clients.append(c)
    assert c.is_connected()
    c.get_received()
    _notify(app, fl_id, "프리에게")
    assert _titles(c) == ["프리에게"]


def test_anonymous_inactive_and_partner_are_refused(app, clients):
    gone = _make_user("STAFF", "CS")
    gone.is_active = False
    org = PartnerOrg(name="가짜협력사연결")
    db_session.add(org)
    db_session.commit()
    partner = User(username="가짜협력사연결계정", password="x", role="PARTNER", team="CS", name="가짜협력",
                   partner_org_id=org.id, is_active=True)
    db_session.add(partner)
    db_session.commit()
    active = _snap(_make_user("STAFF", "CS"))
    for user in (None, _snap(gone), _snap(partner)):
        c = _connect(app, user)
        clients.append(c)
        assert c.is_connected() is False, getattr(user, "username", None)
    ok = _connect(app, active)  # 대조군: 같은 방법으로 만든 활성 직원은 연결된다
    clients.append(ok)
    assert ok.is_connected() is True
