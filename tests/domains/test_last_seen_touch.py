"""LAST-SEEN-01: `User.last_login` must follow real activity, not just login."""

import time
from datetime import datetime, timedelta, timezone

import pytest
from flask import Flask

from foms.services.user_activity import touch_last_seen, touch_interval_seconds


def _stale():
    return datetime(2026, 6, 18, 8, 0, 0)


@pytest.fixture()
def app_ctx(app):
    """Request context on the real test app, so the engine points at the test DB."""
    with app.test_request_context("/erp/orders"):
        yield


def _make_user(username, last_login=None):
    from db import db_session
    from models import User

    user = User(
        username=username,
        password="x",
        role="admin",
        name=username,
        last_login=last_login,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _stored_last_login(user_id):
    from db import db_session
    from models import User

    db_session.expire_all()
    return db_session.query(User).filter_by(id=user_id).one().last_login


def test_touch_writes_current_time_on_first_request(app_ctx):
    user = _make_user("touch1", last_login=_stale())

    assert touch_last_seen(user) is True
    stored = _stored_last_login(user.id)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    assert stored > _stale()
    assert now - stored < timedelta(minutes=5)


def test_touch_is_throttled_within_window(app_ctx):
    user = _make_user("touch2")

    assert touch_last_seen(user) is True
    first = _stored_last_login(user.id)
    assert touch_last_seen(user) is False
    assert _stored_last_login(user.id) == first


def test_touch_writes_again_after_window(app_ctx, monkeypatch):
    monkeypatch.setenv("FOMS_LAST_SEEN_TOUCH_SECONDS", "0")
    user = _make_user("touch3")

    assert touch_last_seen(user) is True
    first = _stored_last_login(user.id)
    time.sleep(0.01)
    assert touch_last_seen(user) is True
    assert _stored_last_login(user.id) >= first


def test_touch_skips_anonymous(app_ctx):
    assert touch_last_seen(None) is False


def test_touch_does_not_expire_request_session_objects(app_ctx):
    """The write must not disturb rows the request already holds (CI red 2026-09-03)."""
    from db import db_session
    from models import User

    user = _make_user("touch4")
    other = db_session.query(User).filter_by(username="touch4").one()

    assert touch_last_seen(user) is True

    db_session.close()  # teardown-equivalent: previously left the row detached
    assert other.username == "touch4"  # no refresh needed -> no DetachedInstanceError


def test_touch_swallows_db_failure(app_ctx, monkeypatch):
    import foms.services.user_activity as mod

    class _BoomEngine:
        def begin(self):
            raise RuntimeError("db down")

    monkeypatch.setattr("db.engine", _BoomEngine(), raising=True)
    user = _make_user("touch5")
    assert mod.touch_last_seen(user) is False


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
    assert "touch_last_seen(user)" in src
    assert 'path.startswith("/static/")' in src


def test_live_request_updates_stale_last_login(login, monkeypatch):
    """A stale timestamp catches up on the next page view, without re-logging in."""
    monkeypatch.setenv("FOMS_LAST_SEEN_TOUCH_SECONDS", "0")

    from db import db_session
    from models import User

    user = db_session.query(User).filter_by(username="admin").one()
    user.last_login = _stale()
    db_session.commit()

    login.get("/admin/users")

    assert _stored_last_login(user.id) > _stale()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    assert now - _stored_last_login(user.id) < timedelta(minutes=5)
