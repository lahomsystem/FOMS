from __future__ import annotations

from models import ChannelDeliveryLog

import foms.services.channel_delivery as channel_delivery


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
