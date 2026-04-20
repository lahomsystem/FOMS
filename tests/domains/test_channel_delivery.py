from __future__ import annotations

from types import SimpleNamespace

from models import ChannelDeliveryLog

import foms.services.channel_delivery as channel_delivery
import foms.services.channel_policy as channel_policy


class _FakeAddOnlyDB:
    def __init__(self) -> None:
        self.added = []
        self.flushed = False

    def add(self, obj) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        self.flushed = True


class _FakeQuery:
    def __init__(self, result) -> None:
        self._result = result

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return self._result


class _FakeStatusDB:
    def __init__(self, log) -> None:
        self._log = log
        self.added = []

    def query(self, _model):
        return _FakeQuery(self._log)

    def add(self, obj) -> None:
        self.added.append(obj)


def test_create_pending_delivery_uses_policy_group_and_flushes(monkeypatch) -> None:
    monkeypatch.setattr(channel_policy, "get_routing_group_id", lambda event_type, data: "group-1")

    db = _FakeAddOnlyDB()
    order = SimpleNamespace(channel_source_seq=7)

    log = channel_delivery.create_pending_delivery(
        db,
        order_id=123,
        event_type="update",
        payload={"files": [{"url": "https://example.com/file.jpg"}]},
        order=order,
    )

    assert db.flushed is True
    assert db.added == [log]
    assert log.event_key == "order_123_update_7"
    assert log.target_id == "group-1"
    assert log.target_group_snapshot == "group-1"
    assert log.template_key == "update"
    assert log.masked_request_payload["files"][0]["url"] == "[MASKED]"


def test_mark_delivery_status_updates_message_and_sent_timestamp() -> None:
    log = ChannelDeliveryLog(status="pending")
    db = _FakeStatusDB(log)

    channel_delivery.mark_delivery_status(
        db,
        delivery_id=1,
        status="sent",
        error_msg="accepted",
        message_id="msg-1",
    )

    assert log.status == "sent"
    assert log.last_error == "accepted"
    assert log.message_id == "msg-1"
    assert log.updated_at is not None
    assert log.sent_at == log.updated_at
    assert db.added == [log]


def test_mask_payload_redacts_urls_without_mutating_input() -> None:
    payload = {
        "files": [
            {"fileName": "a.jpg", "url": "https://example.com/a.jpg"},
            {"fileName": "b.jpg"},
        ]
    }

    masked = channel_delivery.mask_payload(payload)

    assert masked["files"][0]["url"] == "[MASKED]"
    assert masked["files"][1]["fileName"] == "b.jpg"
    assert payload["files"][0]["url"] == "https://example.com/a.jpg"
