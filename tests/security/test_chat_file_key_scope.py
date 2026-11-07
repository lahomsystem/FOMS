"""채팅 파일 받기 · 미리보기 key 범위 — 내가 회원인 방에 처음 올라온 ``chat/`` 첨부만 서명한다.

설계서 docs/specs/2026-11-06-freelancer-sales-commission_SPEC.md §6.4(이미 있는 구멍 — D19, 모든 직원) · §6.3 겹 5.

예전에는 ``/api/chat/download/<key>`` · ``/api/chat/preview/<key>`` 가 로그인만 보고 아무 저장소 key 에나 서명했다
(채팅과 무관한 주문 파일도 받는다). 이제 key → 첨부 줄 → 메시지 → 방 → 회원 확인. 모르는 key · 회원 아닌 방은
404(있는지 알리지 않는다), 켜진 프리랜서는 403. key 모양은 실제 업로드와 같다
(``chat/room_<id>_temp_<ms>/<날짜>_<uuid8>_<이름>`` — ``storage.generate_direct_upload_key`` · ``upload_chat_file``).
화면은 key 를 ``encodeURIComponent`` 로 감싸 부른다(``templates/partials/chat_scripts_file.html``) — 그 모양도 본다.
모든 이름은 가짜 값이다.
"""
from __future__ import annotations

from types import SimpleNamespace
from urllib.parse import quote

import pytest

from db import db_session
from foms.services.chat_room_access import chat_file_denial
from foms.services.sales_commission.settings import load_settings, save_freelancer
from models import ChatAttachment, ChatMessage, ChatRoom, ChatRoomMember, User
from tests.domains.test_auth_finance import _login, _make_user


class _FakeR2:
    """서명 URL 만 돌려주는 가짜 저장소 — 서명한 key 를 적어 둔다(거부면 서명 0번이어야 한다)."""

    storage_type = "r2"

    def __init__(self):
        self.signed: list[str] = []

    def get_download_url(self, key, expires_in=3600):
        self.signed.append(key)
        return f"https://r2.invalid/{key}?sig=fake"

    def get_file_type(self, filename):
        ext = filename.rsplit(".", 1)[-1].lower()
        return {"jpg": "image", "png": "image", "mp4": "video"}.get(ext, "file")


@pytest.fixture()
def storage(monkeypatch):
    fake = _FakeR2()
    monkeypatch.setattr("foms.api.channel.files.get_storage", lambda: fake)
    return fake


def _key(room_id: int, name: str, stamp: str = "1762400000000") -> str:
    return f"chat/room_{room_id}_temp_{stamp}/20261106_101010_ab12cd34_{name}"


def _room(name: str, *members) -> int:
    room = ChatRoom(name=name, created_by=members[0].id)
    db_session.add(room)
    db_session.commit()
    for user in members:
        db_session.add(ChatRoomMember(room_id=room.id, user_id=user.id))
    db_session.commit()
    return room.id


def _attach(room_id: int, sender_id: int, key: str, *, storage_url: str | None = None) -> None:
    """실제 보내기(send_message)와 같은 모양으로 메시지 + 첨부 줄을 만든다."""
    filename = key.rsplit("/", 1)[-1]
    url = storage_url or f"/api/files/view/{key}"
    msg = ChatMessage(room_id=room_id, user_id=sender_id, message_type="image",
                      file_info={"filename": filename, "key": key, "url": url, "file_type": "image"})
    db_session.add(msg)
    db_session.commit()
    db_session.add(ChatAttachment(message_id=msg.id, filename=filename, file_type="image", file_size=10,
                                  storage_key=key, storage_url=url))
    db_session.commit()


def _value(user) -> SimpleNamespace:
    """요청이 끝나면 세션이 닫혀 ORM 객체는 못 읽는다 — 값만 담는다."""
    return SimpleNamespace(id=user.id, username=user.username, role=user.role)


def _client(app, user):
    client = app.test_client()
    _login(client, user)
    return client


@pytest.fixture()
def world(app):
    """방 R(가 · 나) 에 사진 · 동영상, 방 R2(다 혼자)에 사진. 가는 R2 회원이 아니다."""
    ga, na, da = _make_user("STAFF", "CS"), _make_user("STAFF", "CS"), _make_user("STAFF", "DRAWING")
    room, room2 = _room("가짜방", ga, na), _room("가짜방2", da)
    photo, video, other = _key(room, "photo.jpg"), _key(room, "clip.mp4"), _key(room2, "secret.jpg", "1762400000999")
    _attach(room, na.id, photo)
    _attach(room, na.id, video, storage_url=f"/api/chat/download/{video}")  # 옛 이전 스크립트 모양
    _attach(room2, da.id, other)
    return SimpleNamespace(ga=_value(ga), na=_value(na), da=_value(da), room=room, room2=room2, photo=photo,
                           video=video, other=other)


# --------------------------------------------------------------------------
# 회원 — 허용(대조군)
# --------------------------------------------------------------------------
@pytest.mark.parametrize("encode", [False, True])
def test_member_download_and_preview_ok(app, world, storage, encode):
    client = _client(app, world.ga)
    key = quote(world.photo, safe="") if encode else world.photo
    resp = client.get(f"/api/chat/download/{key}")
    assert resp.status_code == 302 and world.photo in resp.headers["Location"]
    resp = client.get(f"/api/chat/preview/{key}")
    assert resp.status_code == 302 and world.photo in resp.headers["Location"]
    resp = client.get(f"/api/chat/preview/{quote(world.video, safe='') if encode else world.video}")
    assert resp.status_code == 200 and resp.get_json()["type"] == "video"
    assert storage.signed == [world.photo, world.photo, world.video]


def test_uploader_member_ok(app, world, storage):
    resp = _client(app, world.na).get(f"/api/chat/download/{world.photo}")
    assert resp.status_code == 302


# --------------------------------------------------------------------------
# 거부 — 서명 0번
# --------------------------------------------------------------------------
@pytest.mark.parametrize("path", ["download", "preview"])
def test_non_member_is_404(app, world, storage, path):
    resp = _client(app, world.ga).get(f"/api/chat/{path}/{world.other}")
    assert resp.status_code == 404 and resp.get_json()["success"] is False
    assert storage.signed == []
    assert _client(app, world.da).get(f"/api/chat/{path}/{world.other}").status_code == 302  # 대조군: 그 방 회원


@pytest.mark.parametrize("key", [
    "orders/1/attachments/20261106_101010_ab12cd34_contract.pdf",   # 주문 첨부(채팅과 무관)
    "order-drafts/1/20261106_sketch.jpg",
    "uploads/20261106_estimate.pdf",
    "chat/room_1_temp_1762400000000/20261106_101010_ffffffff_unknown.jpg",  # 채팅 모양이지만 첨부 줄 없음
    "chat/",
])
@pytest.mark.parametrize("path", ["download", "preview"])
def test_arbitrary_storage_key_is_404(app, world, storage, key, path):
    resp = _client(app, world.ga).get(f"/api/chat/{path}/{key}")
    assert resp.status_code == 404
    assert storage.signed == []


def test_injected_non_chat_key_in_own_room_is_404(app, world, storage):
    """``file_info.key`` 는 손님이 보내는 값 — 내 방 메시지에 주문 파일 key 를 끼워 넣어도 서명하지 않는다."""
    order_key = "orders/7/attachments/20261106_101010_ab12cd34_contract.pdf"
    _attach(world.room, world.ga.id, order_key)
    assert _client(app, world.ga).get(f"/api/chat/download/{order_key}").status_code == 404
    assert storage.signed == []


def test_injected_other_room_chat_key_is_404(app, world, storage):
    """남의 방 key 를 내 방 메시지에 끼워 넣어도 처음 올린 방이 주인이다."""
    _attach(world.room, world.ga.id, world.other)
    assert _client(app, world.ga).get(f"/api/chat/download/{world.other}").status_code == 404
    assert storage.signed == []


def test_member_removed_loses_access(app, world, storage):
    db_session.query(ChatRoomMember).filter(ChatRoomMember.room_id == world.room,
                                            ChatRoomMember.user_id == world.ga.id).delete()
    db_session.commit()
    assert _client(app, world.ga).get(f"/api/chat/download/{world.photo}").status_code == 404


@pytest.mark.parametrize("bad", ["chat/../orders/1/a.pdf", "chat/room_1/../../x.jpg"])
def test_dotdot_still_400(app, world, storage, bad):
    assert _client(app, world.ga).get(f"/api/chat/download/{bad}").status_code in (400, 404)
    assert storage.signed == []


def test_anonymous_is_rejected(app, world, storage):
    resp = app.test_client().get(f"/api/chat/download/{world.photo}")
    assert resp.status_code in (302, 401)
    assert storage.signed == []


# --------------------------------------------------------------------------
# 켜진 프리랜서 — 회원이어도 403
# --------------------------------------------------------------------------
def test_freelancer_is_403_even_as_member(app, world, storage):
    fl = _value(_make_user("STAFF", "SALES"))
    db_session.add(ChatRoomMember(room_id=world.room, user_id=fl.id))
    db_session.commit()
    save_freelancer(db_session, fl.id, {"match_name": "가짜프리파일", "start_month": "2020-01", "tax_type": "NONE",
                                        "active": True},
                    base_version=load_settings(db_session)[0], actor_user_id=None)
    db_session.commit()
    for path in ("download", "preview"):
        assert _client(app, fl).get(f"/api/chat/{path}/{world.photo}").status_code == 403
    assert storage.signed == []
    # 문지기 앞단과 별개로 판정 함수 자체도 프리랜서를 막는다(핸들러 안 방어).
    with app.test_request_context("/"):
        user = db_session.get(User, fl.id)
        assert chat_file_denial(db_session, user, world.photo)[0] == 403
        assert chat_file_denial(db_session, db_session.get(User, world.ga.id), world.photo) is None  # 대조군
