from __future__ import annotations

import foms.services.channel_policy as channel_policy


def test_apply_attachment_policy_caps_to_twenty_items() -> None:
    files = [{"id": index} for index in range(25)]

    capped = channel_policy.apply_attachment_policy(files)

    assert capped == files[:20]
    assert len(capped) == channel_policy.MAX_MANUAL_ATTACHMENTS == 20


def test_resolve_push_policy_uses_measurement_group_for_manual_push(monkeypatch) -> None:
    monkeypatch.setenv("CHANNEL_GROUP_MEASUREMENT", "group-main")

    policy = channel_policy.resolve_push_policy("manual", {"order_id": 101})

    assert policy == {
        "group_id": "group-main",
        "dedupe_window": 0,
        "template_key": "manual",
        "max_attachments": 20,
    }


def test_resolve_inbound_policy_honors_allowed_groups(monkeypatch) -> None:
    monkeypatch.setenv("CHANNEL_ALLOWED_GROUP_IDS", "group-a, group-b ")

    allowed = channel_policy.resolve_inbound_policy("group-b", "manual", create_enabled=True)
    blocked = channel_policy.resolve_inbound_policy("group-z", "manual", create_enabled=False)

    assert allowed == {"is_allowed_group": True, "can_create": True}
    assert blocked == {"is_allowed_group": False, "can_create": False}
