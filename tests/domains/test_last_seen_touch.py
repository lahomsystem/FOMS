"""LAST-SEEN-01: `User.last_login` must follow real activity, not just login."""

import time
from datetime import datetime, timedelta, timezone

import pytest
from flask import Flask

from foms.services.user_activity import touch_last_seen, touch_interval_seconds


class _FakeUser:
    def __init__(self, last_login=None):
        self.last_login = last_login


class _FakeDb:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


@pytest.fixture()
def app_ctx():
    app = Flask(__name__)
    app.secret_key = "test"
    with app.test_request_context("/erp/orders"):
        yield


def test_touch_writes_current_time_on_first_request(app_ctx):
    user = _FakeUser(last_login=datetime(2026, 6, 18, 8, 0, 0))
    db = _FakeDb()

    assert touch_last_seen(db, user) is True
    assert db.commits == 1
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    assert now - user.last_login < timedelta(minutes=5)


def test_touch_is_throttled_within_window(app_ctx):
    user = _FakeUser()
    db = _FakeDb()

    assert touch_last_seen(db, user) is True
    first = user.last_login
    assert touch_last_seen(db, user) is False
    assert user.last_login == first
    assert db.commits == 1


def test_touch_writes_again_after_window(app_ctx, monkeypatch):
    monkeypatch.setenv("FOMS_LAST_SEEN_TOUCH_SECONDS", "0")
    user = _FakeUser()
    db = _FakeDb()

    assert touch_last_seen(db, user) is True
    time.sleep(0.01)
    assert touch_last_seen(db, user) is True
    assert db.commits == 2


def test_touch_skips_anonymous(app_ctx):
    db = _FakeDb()
    assert touch_last_seen(db, None) is False
    assert db.commits == 0


def test_touch_swallows_db_failure(app_ctx):
    class _BoomDb(_FakeDb):
        def commit(self):
            raise RuntimeError("db down")

    db = _BoomDb()
    assert touch_last_seen(db, _FakeUser()) is False
    assert db.rollbacks == 1


def test_interval_defaults_to_five_minutes(monkeypatch):
    monkeypatch.delenv("FOMS_LAST_SEEN_TOUCH_SECONDS", raising=False)
    assert touch_interval_seconds() == 300
    monkeypatch.setenv("FOMS_LAST_SEEN_TOUCH_SECONDS", "not-a-number")
    assert touch_interval_seconds() == 300
    monkeypatch.setenv("FOMS_LAST_SEEN_TOUCH_SECONDS", "60")
    assert touch_interval_seconds() == 60


def test_request_hook_is_registered():
    """The app must touch last-seen on every non-static request."""
    import inspect

    from foms.platform import http as http_module

    src = inspect.getsource(http_module.register_http_bootstrap)
    assert "_touch_last_seen" in src
    assert "touch_last_seen(get_db(), user)" in src
    assert 'path.startswith("/static/")' in src


def test_live_request_updates_stale_last_login(login, monkeypatch):
    """A stale timestamp catches up on the next page view, without re-logging in."""
    monkeypatch.setenv("FOMS_LAST_SEEN_TOUCH_SECONDS", "0")

    from db import db_session
    from models import User

    user = db_session.query(User).filter_by(username="admin").one()
    stale = datetime(2026, 6, 18, 8, 0, 0)
    user.last_login = stale
    db_session.commit()

    login.get("/admin/users")

    db_session.expire_all()
    refreshed = db_session.query(User).filter_by(username="admin").one()
    assert refreshed.last_login > stale
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    assert now - refreshed.last_login < timedelta(minutes=5)
