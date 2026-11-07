"""실시간 방 회원 확인 — 개인 알림 방은 본인만, 채팅방은 회원만, 켜진 프리랜서는 채팅 이벤트 전부 거부.

설계서 docs/specs/2026-11-06-freelancer-sales-commission_SPEC.md §6.4(이미 있는 구멍 — D19, 모든 직원) · §6.3 겹 5 ·
§6.5 "Socket: 프리랜서 join_room 거부", 검수 원장 A5.

예전에는 ``join_room`` 이 아무 방 이름이나 받아, 직원이면 남의 개인 방 ``user_<id>`` 에 들어가 그 사람의 실시간 알림 ·
채팅 사본을 받았다. ``typing`` 도 회원 확인이 없었다. 거부마다 같은 모집단의 허용 대조군을 같이 둔다.
모든 이름은 가짜 값이다.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from db import db_session
from foms.services.notifications.realtime_notifications import emit_erp_notification_to_users
from foms.services.sales_commission.settings import load_settings, save_freelancer
from models import ChatMessage, ChatRoom, ChatRoomMember
from tests.domains.test_auth_finance import _login, _make_user


def _ws(app, user):
    from app import socketio

    http = app.test_client()
    _login(http, user)
    client = socketio.test_client(app, flask_test_client=http)
    assert client.is_connected() is True
    client.get_received()  # 'connected' 인사 비우기
    return client


def _room(name: str, *members) -> int:
    room = ChatRoom(name=name, created_by=members[0].id)
    db_session.add(room)
    db_session.commit()
    for user in members:
        db_session.add(ChatRoomMember(room_id=room.id, user_id=user.id))
    db_session.commit()
    return room.id


def _names(received) -> list[str]:
    return [item["name"] for item in received]


def _events(received, name: str) -> list:
    return [item["args"][0] for item in received if item["name"] == name]


def _designate(user, match: str) -> None:
    save_freelancer(db_session, user.id, {"match_name": match, "start_month": "2020-01", "tax_type": "NONE",
                                          "active": True},
                    base_version=load_settings(db_session)[0], actor_user_id=None)
    db_session.commit()


def _value(user) -> SimpleNamespace:
    return SimpleNamespace(id=user.id, username=user.username, role=user.role)


@pytest.fixture()
def world(app):
    """직원 셋(CS 둘 · 영업 하나) + 켜진 프리랜서 하나. 방 R = 가 · 나 · 프리랜서, 방 R2 = 다 혼자."""
    ga, na, da = _make_user("STAFF", "CS"), _make_user("STAFF", "CS"), _make_user("STAFF", "SALES")
    fl = _make_user("STAFF", "SALES")
    _designate(fl, "가짜프리소켓")
    room = _room("가짜방", ga, na, fl)  # 프리랜서는 지정 뒤 다른 직원이 다시 넣은 경우
    room2 = _room("가짜방2", da)
    clients = []

    def connect(user):
        client = _ws(app, user)
        clients.append(client)
        return client

    yield SimpleNamespace(ga=_value(ga), na=_value(na), da=_value(da), fl=_value(fl), room=room, room2=room2,
                          connect=connect)
    for client in clients:
        if client.is_connected():
            client.disconnect()


def _notify(app, user_id: int, title: str) -> None:
    with app.app_context():
        emit_erp_notification_to_users([user_id], {"title": title})


# --------------------------------------------------------------------------
# 개인 알림 방
# --------------------------------------------------------------------------
def test_own_user_room_join_ok_and_notifications_arrive(app, world):
    ga = world.connect(world.ga)
    ga.emit("join_room", {"room_id": f"user_{world.ga.id}"})
    got = ga.get_received()
    assert "error" not in _names(got) and _events(got, "joined_room")
    _notify(app, world.ga.id, "가에게")
    assert [p["title"] for p in _events(ga.get_received(), "erp_notification")] == ["가에게"]


def test_other_user_room_join_denied_and_no_copy(app, world):
    ga, na = world.connect(world.ga), world.connect(world.na)
    ga.emit("join_room", {"room_id": f"user_{world.na.id}"})
    got = ga.get_received()
    assert _events(got, "error") and not _events(got, "joined_room")
    _notify(app, world.na.id, "나에게만")
    assert _events(ga.get_received(), "erp_notification") == []          # 남의 알림 사본 없음
    assert [p["title"] for p in _events(na.get_received(), "erp_notification")] == ["나에게만"]  # 대조군


@pytest.mark.parametrize("value", ["user_x", "lobby", "-3", "0", "", None, "1 OR 1=1"])
def test_non_room_strings_are_not_joined(app, world, value):
    ga = world.connect(world.ga)
    ga.emit("join_room", {"room_id": value})
    assert not _events(ga.get_received(), "joined_room")


def test_join_room_body_not_dict_is_ignored(app, world):
    ga = world.connect(world.ga)
    ga.emit("join_room", "user_1")
    assert not _events(ga.get_received(), "joined_room")


# --------------------------------------------------------------------------
# 채팅방
# --------------------------------------------------------------------------
def test_member_chat_room_join_ok_and_receives_messages(app, world):
    ga, na = world.connect(world.ga), world.connect(world.na)
    ga.emit("join_room", {"room_id": world.room})
    got = ga.get_received()
    assert "error" not in _names(got) and _events(got, "joined_room")
    na.emit("send_message", {"room_id": world.room, "content": "안녕"})
    assert "안녕" in [m.get("content") for m in _events(ga.get_received(), "new_message")]


def test_non_member_chat_room_join_denied_and_no_broadcast(app, world):
    ga, da = world.connect(world.ga), world.connect(world.da)
    ga.emit("join_room", {"room_id": world.room2})
    got = ga.get_received()
    assert _events(got, "error") and not _events(got, "joined_room")
    da.emit("join_room", {"room_id": world.room2})
    da.emit("send_message", {"room_id": world.room2, "content": "다만봄"})
    assert _events(ga.get_received(), "new_message") == []               # 방 방송을 못 받는다
    assert "다만봄" in [m.get("content") for m in _events(da.get_received(), "new_message")]  # 대조군


def test_string_room_id_member_ok(app, world):
    """화면은 숫자를 보내지만 글자 숫자도 같은 방이다(대조군)."""
    ga = world.connect(world.ga)
    ga.emit("join_room", {"room_id": str(world.room)})
    assert _events(ga.get_received(), "joined_room")


def test_typing_requires_membership(app, world):
    ga, na, da = world.connect(world.ga), world.connect(world.na), world.connect(world.da)
    da.emit("join_room", {"room_id": world.room2})
    na.emit("join_room", {"room_id": world.room})
    da.get_received(), na.get_received()
    ga.emit("typing", {"room_id": world.room2, "is_typing": True})    # 회원 아님
    assert _events(ga.get_received(), "error")
    assert _events(da.get_received(), "user_typing") == []
    ga.emit("typing", {"room_id": world.room, "is_typing": True})     # 회원 — 대조군
    assert [e["user_id"] for e in _events(na.get_received(), "user_typing")] == [world.ga.id]


def test_send_message_non_member_denied(app, world):
    ga = world.connect(world.ga)
    ga.emit("send_message", {"room_id": world.room2, "content": "끼어들기"})
    assert _events(ga.get_received(), "error")
    assert db_session.query(ChatMessage).filter(ChatMessage.room_id == world.room2).count() == 0


def test_leave_room_non_member_does_not_broadcast(app, world):
    ga, da = world.connect(world.ga), world.connect(world.da)
    da.emit("join_room", {"room_id": world.room2})
    da.get_received()
    ga.emit("leave_room", {"room_id": world.room2})
    assert _events(da.get_received(), "user_left") == []


# --------------------------------------------------------------------------
# 켜진 프리랜서 — 채팅 이벤트 전부 거부, 개인 알림 방만
# --------------------------------------------------------------------------
def test_freelancer_connects_and_gets_own_notifications(app, world):
    fl = world.connect(world.fl)
    _notify(app, world.fl.id, "배정됐어요")
    assert [p["title"] for p in _events(fl.get_received(), "erp_notification")] == ["배정됐어요"]


def test_freelancer_chat_events_denied_even_as_member(app, world):
    fl, ga = world.connect(world.fl), world.connect(world.ga)
    ga.emit("join_room", {"room_id": world.room})
    ga.get_received()
    before = db_session.query(ChatRoomMember).filter(ChatRoomMember.room_id == world.room,
                                                     ChatRoomMember.user_id == world.fl.id).one().last_read_at

    fl.emit("join_room", {"room_id": world.room})
    got = fl.get_received()
    assert _events(got, "error") and not _events(got, "joined_room")
    fl.emit("send_message", {"room_id": world.room, "content": "프리랜서말"})
    fl.emit("typing", {"room_id": world.room, "is_typing": True})
    fl.emit("mark_read", {"room_id": world.room})
    got = fl.get_received()
    assert len(_events(got, "error")) == 3
    seen = ga.get_received()
    assert _events(seen, "new_message") == [] and _events(seen, "user_typing") == [] \
        and _events(seen, "message_read") == []
    db_session.expire_all()
    assert db_session.query(ChatMessage).filter(ChatMessage.room_id == world.room).count() == 0
    after = db_session.query(ChatRoomMember).filter(ChatRoomMember.room_id == world.room,
                                                    ChatRoomMember.user_id == world.fl.id).one().last_read_at
    assert after == before


def test_new_message_copy_skips_freelancer_member(app, world):
    """직원이 프리랜서를 방에 다시 넣어도 새 메시지 사본이 프리랜서 개인 방으로 가지 않는다(A5)."""
    fl, na, ga = world.connect(world.fl), world.connect(world.na), world.connect(world.ga)
    ga.emit("send_message", {"room_id": world.room, "content": "직원끼리"})
    assert _events(fl.get_received(), "new_message") == []
    assert "직원끼리" in [m.get("content") for m in _events(na.get_received(), "new_message")]  # 대조군(개인 방 사본)
