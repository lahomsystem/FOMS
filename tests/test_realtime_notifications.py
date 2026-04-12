import logging

from flask import Flask

import foms.services.realtime_notifications as realtime_notifications


class _FakeSocketIO:
    def __init__(self):
        self.calls = []

    def emit(self, event, data, room=None):
        self.calls.append((event, data, room))


def test_emit_erp_notification_to_users_returns_zero_when_user_ids_empty():
    app = Flask(__name__)

    with app.app_context():
        assert realtime_notifications.emit_erp_notification_to_users([], {"urgent": True}) == 0


def test_emit_erp_notification_to_users_returns_zero_and_logs_when_socketio_missing(caplog):
    app = Flask(__name__)

    with app.app_context(), caplog.at_level(logging.WARNING):
        sent = realtime_notifications.emit_erp_notification_to_users([1], {"urgent": True})

    assert sent == 0
    assert "_SOCKETIO_INSTANCE is None" in caplog.text


def test_emit_erp_notification_to_users_sends_to_valid_rooms_and_sets_default_kind():
    socketio = _FakeSocketIO()
    app = Flask(__name__)
    app.config["_SOCKETIO_INSTANCE"] = socketio

    with app.app_context():
        sent = realtime_notifications.emit_erp_notification_to_users(
            [1, "2", "bad", None],
            {"urgent": True, "message": "ping"},
        )

    assert sent == 2
    assert socketio.calls == [
        ("erp_notification", {"urgent": True, "message": "ping", "kind": "erp_notification"}, "user_1"),
        ("erp_notification", {"urgent": True, "message": "ping", "kind": "erp_notification"}, "user_2"),
    ]
