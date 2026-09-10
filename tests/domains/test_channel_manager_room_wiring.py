"""담당자 개인 도면방 배선 계약 — 발송 경로·사용자 관리 화면.

* `dispatch_order_event` 가 명시 그룹을 받으면 그 방으로 보낸다(기존 호출부는 무영향).
* 도면방 PUSH 라우트가 공용방 전송 뒤 개인방을 시도하고, 실패해도 공용방 전송을
  되돌리지 않으며 응답으로 알린다.
* 사용자 관리(목록·편집)에 방 번호 칸이 있고 감사 대상 필드에 올라가 있다.
"""
from __future__ import annotations

import inspect
from pathlib import Path

import foms.services.channel_dispatch as dispatch_mod
from foms.api.channel.channel_integration import api_channel_push_manual
from foms.web.auth.routes import _AUDITED_USER_FIELDS

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_dispatch_uses_explicit_group_when_given(monkeypatch) -> None:
    """`group_id` 를 주면 정책 대신 그 방으로 보낸다."""
    seen: dict[str, object] = {}
    monkeypatch.setattr(dispatch_mod, "build_message_template", lambda *a, **k: "본문")
    monkeypatch.setattr(dispatch_mod, "build_message_blocks", lambda *a, **k: [])
    monkeypatch.setattr(dispatch_mod, "apply_attachment_policy", lambda files: files)
    monkeypatch.setattr(dispatch_mod, "build_channel_bot_name", lambda *a, **k: "bot")
    monkeypatch.setattr(
        dispatch_mod,
        "get_routing_group_id",
        lambda *a, **k: "230331",
    )

    def _fake_send(group_id, **kwargs):
        seen["group_id"] = group_id
        return {"success": True, "message_id": "m1"}

    monkeypatch.setattr(dispatch_mod, "send_group_message", _fake_send)

    dispatch_mod.dispatch_order_event("manual", {"push_kind": "drawing_room", "group_id": "567925"})
    assert seen["group_id"] == "567925", "명시 그룹을 무시하고 공용방으로 보냈다"


def test_dispatch_falls_back_to_policy_without_group(monkeypatch) -> None:
    """`group_id` 가 없으면 기존대로 종류별 정책이 방을 정한다."""
    seen: dict[str, object] = {}
    monkeypatch.setattr(dispatch_mod, "build_message_template", lambda *a, **k: "본문")
    monkeypatch.setattr(dispatch_mod, "build_message_blocks", lambda *a, **k: [])
    monkeypatch.setattr(dispatch_mod, "apply_attachment_policy", lambda files: files)
    monkeypatch.setattr(dispatch_mod, "build_channel_bot_name", lambda *a, **k: "bot")
    monkeypatch.setattr(dispatch_mod, "get_routing_group_id", lambda *a, **k: "230331")
    monkeypatch.setattr(
        dispatch_mod,
        "send_group_message",
        lambda group_id, **kwargs: seen.setdefault("group_id", group_id) or {"success": True},
    )

    dispatch_mod.dispatch_order_event("manual", {"push_kind": "drawing_room"})
    assert seen["group_id"] == "230331"


def test_route_sends_manager_room_after_the_shared_room() -> None:
    """공용방 전송이 끝난 뒤에 개인방을 시도한다 — 순서가 뒤집히면 부분 실패 의미가 달라진다."""
    source = inspect.getsource(api_channel_push_manual)
    assert "resolve_manager_room" in source, "라우트가 담당자 개인방을 찾지 않는다"
    first_send = source.index("result = dispatch_order_event")
    room_send = source.index("resolve_manager_room")
    assert first_send < room_send, "개인방을 공용방보다 먼저 보내고 있다"
    assert "manager_room_sent" in source, "개인방 전송 여부를 응답에 싣지 않는다"


def test_manager_room_failure_does_not_fail_the_whole_push() -> None:
    """개인방 실패는 공용방 성공을 뒤집지 않는다 — 이미 나간 메시지는 되돌릴 수 없다."""
    source = inspect.getsource(api_channel_push_manual)
    room_block = source[source.index("resolve_manager_room"):]
    assert "manager_room_note = (" in room_block, "실패 사유를 응답에 담지 않는다"
    # 개인방 실패 경로가 500 으로 빠지면 공용방 성공이 실패로 보고된다.
    assert "raise" not in room_block.split("manager_room_note = (")[0].split("except")[-1]


def test_user_admin_screens_expose_the_room_field() -> None:
    """사용자 관리에서 등록·확인이 가능해야 담당자 추가·삭제에 대응할 수 있다."""
    edit = (REPO_ROOT / "templates/auth/edit_user.html").read_text(encoding="utf-8")
    assert 'name="channel_drawing_group_id"' in edit, "편집 화면에 입력칸이 없다"
    assert "담당자 도면방" in edit

    listing = (REPO_ROOT / "templates/auth/user_list.html").read_text(encoding="utf-8")
    assert "user.channel_drawing_group_id" in listing, "목록에서 등록 여부를 볼 수 없다"


def test_room_change_is_audited() -> None:
    """방 번호는 발송 대상을 바꾸는 값이라 누가 언제 바꿨는지 남아야 한다."""
    assert "channel_drawing_group_id" in _AUDITED_USER_FIELDS
