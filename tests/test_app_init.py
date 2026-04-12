"""Focused tests for automatic app bootstrap admin creation."""

from __future__ import annotations

from werkzeug.security import check_password_hash

import foms.services.app_init as app_init


class _FakeQuery:
    """Minimal query double for the admin bootstrap helper."""

    def __init__(self, admin) -> None:
        self._admin = admin

    def filter_by(self, **kwargs):
        assert kwargs == {"username": "admin"}
        return self

    def first(self):
        return self._admin


class _FakeSession:
    """Minimal session double for admin bootstrap tests."""

    def __init__(self, admin=None) -> None:
        self._admin = admin
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    def query(self, model):
        assert model is app_init.User
        return _FakeQuery(self._admin)

    def add(self, obj) -> None:
        self.added.append(obj)
        self._admin = obj

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def test_get_bootstrap_admin_password_returns_none_when_env_missing(monkeypatch) -> None:
    """Missing or blank env values should disable automatic admin bootstrap."""
    monkeypatch.delenv("FOMS_ADMIN_DEFAULT_PASSWORD", raising=False)
    assert app_init._get_bootstrap_admin_password() is None

    monkeypatch.setenv("FOMS_ADMIN_DEFAULT_PASSWORD", "   ")
    assert app_init._get_bootstrap_admin_password() is None


def test_ensure_default_admin_skips_without_configured_password(monkeypatch, capsys) -> None:
    """Automatic admin bootstrap should skip when no explicit password is configured."""
    monkeypatch.delenv("FOMS_ADMIN_DEFAULT_PASSWORD", raising=False)
    session = _FakeSession()

    app_init._ensure_default_admin(session)

    captured = capsys.readouterr().out
    assert session.added == []
    assert session.commits == 0
    assert session.rollbacks == 0
    assert "FOMS_ADMIN_DEFAULT_PASSWORD" in captured
    assert "admin1234" not in captured
    assert "admin/" not in captured


def test_ensure_default_admin_creates_user_from_configured_password(monkeypatch, capsys) -> None:
    """Configured bootstrap password should be hashed and never echoed back to logs."""
    monkeypatch.setenv("FOMS_ADMIN_DEFAULT_PASSWORD", "super-secret")
    session = _FakeSession()

    app_init._ensure_default_admin(session)

    captured = capsys.readouterr().out
    assert len(session.added) == 1
    assert session.commits == 1
    assert session.rollbacks == 0
    created_admin = session.added[0]
    assert created_admin.username == "admin"
    assert check_password_hash(created_admin.password, "super-secret")
    assert "configured bootstrap password" in captured
    assert "super-secret" not in captured
    assert "admin1234" not in captured
    assert "admin/" not in captured


def test_ensure_default_admin_preserves_existing_admin(monkeypatch, capsys) -> None:
    """Existing admin rows should bypass automatic creation and avoid side effects."""
    monkeypatch.setenv("FOMS_ADMIN_DEFAULT_PASSWORD", "super-secret")
    existing_admin = app_init.User(
        username="admin",
        password="already-set",
        name="관리자",
        role="ADMIN",
        is_active=True,
    )
    session = _FakeSession(admin=existing_admin)

    app_init._ensure_default_admin(session)

    captured = capsys.readouterr().out
    assert session.added == []
    assert session.commits == 0
    assert session.rollbacks == 0
    assert "Admin user exists." in captured
    assert "super-secret" not in captured
    assert "admin1234" not in captured
