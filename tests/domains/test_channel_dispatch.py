from __future__ import annotations

import foms.services.channel_dispatch as channel_dispatch


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

    files = [{"fileName": f"file-{index}.jpg"} for index in range(12)]
    result = channel_dispatch.dispatch_order_event("manual", {"files": files}, raise_on_error=True)

    assert result == {"success": True, "message_id": "msg-1"}
    assert captured["group_id"] == "group-1"
    assert captured["files"] == files[:10]
