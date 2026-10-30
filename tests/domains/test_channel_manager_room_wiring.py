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
# 라우트 몸통은 ERP · 협력사 API 가 같이 쓰는 run_manual_push 로 옮겼다(2026-10-29).
from foms.api.channel.channel_integration import run_manual_push as api_channel_push_manual
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


def test_preview_reports_the_manager_room_without_sending() -> None:
    """미리보기가 개인방까지 말한다 — 누르기 전에 어디로 가는지 알아야 하고,
    발송 없이 매칭을 확인할 수 있는 유일한 자리다."""
    from foms.api.channel.channel_integration import _drawing_room_preview_payload

    source = inspect.getsource(_drawing_room_preview_payload)
    assert "resolve_manager_room" in source, "미리보기가 전송과 다른 방식으로 방을 정한다"
    for key in ("manager_room_group_id", "manager_name", "manager_room_note"):
        assert key in source, f"미리보기 payload 에 {key} 가 없다"


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


def test_push_stops_before_sending_when_manager_is_unresolved() -> None:
    """담당자가 비었거나 계정 없는 이름이면 보내기 **전에** 멈추고 확인을 받는다.

    운영 실측(2026-10-20~30): 개인방을 놓친 건은 전부 누른 순간 담당자가 비었던 주문이었다.
    멈춤이 슬롯 잡기·발송보다 뒤에 있으면 이미 공용방에 나간 뒤라 소용이 없다.
    """
    source = inspect.getsource(api_channel_push_manual)
    stop = source.index("_manager_room_stop_message(db, order)")
    assert stop < source.index("_try_claim_push_slot"), "멈춤이 슬롯을 잡은 뒤에 있다"
    assert stop < source.index("result = dispatch_order_event"), "멈춤이 발송 뒤에 있다"
    assert "allow_without_manager_room" in source, "확인 뒤 그래도 보내는 길이 없다"
    assert "'manager_room_unresolved'" in source


def test_push_sends_to_every_manager_room() -> None:
    """담당자 여럿이면 찾은 방 전부로 보낸다."""
    source = inspect.getsource(api_channel_push_manual)
    assert "for room_group_id in lookup.group_ids" in source


def test_stop_message_covers_empty_and_unknown_manager(monkeypatch) -> None:
    """멈춤 대상은 도면팀이 담당자 칸만 고치면 풀리는 두 경우뿐이다."""
    import foms.api.channel.channel_integration as mod
    from foms.services.channel_manager_room import ManagerRoomLookup

    cases = {
        "empty": ManagerRoomLookup(None, "", "no_manager", "x"),
        "unknown": ManagerRoomLookup(None, "벡제현", "no_user", "x", missing_users=("벡제현",)),
        "partial": ManagerRoomLookup(None, "백재현/선종현", "partial", "x",
                                     group_ids=("438709",), missing_users=("선종현",)),
        "unregistered": ManagerRoomLookup(None, "강민경", "not_registered", "x"),
        "ambiguous": ManagerRoomLookup(None, "김세연", "ambiguous", "x"),
        "dormant": ManagerRoomLookup(None, "강민경", "dormant", None),
        "ok": ManagerRoomLookup("438709", "백재현"),
    }
    for key, lookup in cases.items():
        monkeypatch.setattr(mod, "resolve_manager_room", lambda db, order, _l=lookup: _l)
        message = mod._manager_room_stop_message(None, object())
        if key in ("empty", "unknown", "partial"):
            assert message, f"{key} 인데 멈추지 않는다"
        else:
            assert message is None, f"{key} 는 도면팀이 고칠 수 없는데 멈춘다"
    monkeypatch.setattr(mod, "resolve_manager_room", lambda db, order: cases["partial"])
    assert "선종현" in mod._manager_room_stop_message(None, object())


def test_both_push_screens_confirm_and_retry_with_the_flag() -> None:
    """작업실·마법사 둘 다 멈춤을 받으면 확인창을 띄우고, 확인하면 플래그로 다시 보낸다."""
    for rel in ("templates/drawing/partials/workbench_detail_body.html", "static/js/drawing/wizard.js"):
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert "manager_room_unresolved" in text, f"{rel} 가 멈춤 응답을 모른다"
        assert "allow_without_manager_room" in text, f"{rel} 가 확인 뒤 다시 보내지 못한다"
