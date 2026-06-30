from __future__ import annotations

import foms.services.channel_dispatch as channel_dispatch


import foms.services.channel_policy as channel_policy


def test_get_routing_group_id_branches_on_push_kind(monkeypatch) -> None:
    monkeypatch.setenv("CHANNEL_GROUP_MEASUREMENT", "measure-grp")
    monkeypatch.setenv("CHANNEL_GROUP_DRAWING", "draw-grp")

    assert channel_policy.get_routing_group_id("manual", {"push_kind": "measurement"}) == "measure-grp"
    assert channel_policy.get_routing_group_id("manual", {"push_kind": "drawing"}) == "draw-grp"
    # 기본값(미지정) = 실측 그룹
    assert channel_policy.get_routing_group_id("manual", {}) == "measure-grp"


def test_get_routing_group_id_falls_back_to_production_groups(monkeypatch) -> None:
    monkeypatch.delenv("CHANNEL_GROUP_DRAWING", raising=False)
    monkeypatch.delenv("CHANNEL_GROUP_MEASUREMENT", raising=False)
    assert channel_policy.get_routing_group_id("manual", {"push_kind": "drawing"}) == "229625"
    assert channel_policy.get_routing_group_id("manual", {"push_kind": "measurement"}) == "209990"


def test_dispatch_order_event_returns_failure_when_group_missing(monkeypatch) -> None:
    monkeypatch.setattr(channel_dispatch, "get_routing_group_id", lambda event_type, data: "")

    result = channel_dispatch.dispatch_order_event("manual", {"text": "hello"})

    assert result == {"success": False, "message_id": None}


def test_dispatch_order_event_applies_attachment_policy_before_send(monkeypatch) -> None:
    captured = {}

    monkeypatch.setattr(channel_dispatch, "get_routing_group_id", lambda event_type, data: "group-1")
    monkeypatch.setattr(channel_dispatch, "build_message_template", lambda event_type, data: "body")
    monkeypatch.setattr(channel_dispatch, "build_message_blocks", lambda event_type, data: [])

    def _fake_send_group_message(**kwargs):
        captured.update(kwargs)
        return {"success": True, "message_id": "msg-1"}

    monkeypatch.setattr(channel_dispatch, "send_group_message", _fake_send_group_message)

    files = [{"fileName": f"file-{index}.jpg"} for index in range(25)]
    result = channel_dispatch.dispatch_order_event("manual", {"files": files}, raise_on_error=True)

    assert result == {"success": True, "message_id": "msg-1"}
    assert captured["group_id"] == "group-1"
    assert captured["files"] == files[:20]
    assert len(captured["files"]) == 20
    assert captured["bot_name"] == "FOMS"


def test_dispatch_order_event_uses_pushed_by_name_for_bot_name(monkeypatch) -> None:
    captured = {}

    monkeypatch.setattr(channel_dispatch, "get_routing_group_id", lambda event_type, data: "group-1")
    monkeypatch.setattr(channel_dispatch, "build_message_template", lambda event_type, data: "body")
    monkeypatch.setattr(channel_dispatch, "build_message_blocks", lambda event_type, data: [])

    def _fake_send_group_message(**kwargs):
        captured.update(kwargs)
        return {"success": True, "message_id": "msg-1"}

    monkeypatch.setattr(channel_dispatch, "send_group_message", _fake_send_group_message)

    result = channel_dispatch.dispatch_order_event(
        "manual",
        {"text": "hello", "pushed_by_name": "강민경"},
        raise_on_error=True,
    )

    assert result == {"success": True, "message_id": "msg-1"}
    assert captured["bot_name"] == "FOMS강민경"
