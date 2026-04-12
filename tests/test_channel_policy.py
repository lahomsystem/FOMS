from __future__ import annotations

import foms.services.channel_policy as channel_policy


def test_apply_attachment_policy_caps_to_ten_items() -> None:
    files = [{"id": index} for index in range(12)]

    assert channel_policy.apply_attachment_policy(files) == files[:10]


def test_resolve_push_policy_uses_as_urgent_group_and_zero_dedupe(monkeypatch) -> None:
    monkeypatch.setenv("CHANNEL_GROUP_MEASUREMENT", "group-main")
    monkeypatch.setenv("CHANNEL_GROUP_AS", "group-as")

    policy = channel_policy.resolve_push_policy("as_urgent", {"order_id": 101})

    assert policy == {
        "group_id": "group-as",
        "dedupe_window": 0,
        "template_key": "as_urgent",
        "max_attachments": 10,
    }


def test_resolve_inbound_policy_honors_allowed_groups(monkeypatch) -> None:
    monkeypatch.setenv("CHANNEL_ALLOWED_GROUP_IDS", "group-a, group-b ")

    allowed = channel_policy.resolve_inbound_policy("group-b", "manual", create_enabled=True)
    blocked = channel_policy.resolve_inbound_policy("group-z", "manual", create_enabled=False)

    assert allowed == {"is_allowed_group": True, "can_create": True}
    assert blocked == {"is_allowed_group": False, "can_create": False}
