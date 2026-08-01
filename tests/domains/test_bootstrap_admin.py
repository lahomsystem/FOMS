"""STARTUP-ADMIN-01 — explicit-only admin bootstrap CLI contract.

``tools/ops/bootstrap_admin.py`` replaces the removed WSGI startup
auto-bootstrap: admin creation only happens when an operator runs the CLI
explicitly, the password never touches argv/env/stdout/log, and an existing
admin row is left untouched (idempotent).
"""
from __future__ import annotations

import inspect

from werkzeug.security import check_password_hash

import pytest

import foms.services.app_init as app_init
from models import User
from tools.ops.bootstrap_admin import ADMIN_USERNAME, _prompt_password, bootstrap_admin


class _FakeQuery:
    """Minimal query double for ``filter_by(username=...).first()``."""

    def __init__(self, admin) -> None:
        self._admin = admin

    def filter_by(self, **kwargs):
        assert kwargs == {"username": ADMIN_USERNAME}
        return self

    def first(self):
        return self._admin


class _FakeSession:
    """Minimal session double for the bootstrap CLI's DB interaction."""

    def __init__(self, admin=None) -> None:
        self._admin = admin
        self.added: list = []
        self.commits = 0
        self.rollbacks = 0

    def query(self, model):
        assert model is User
        return _FakeQuery(self._admin)

    def add(self, obj) -> None:
        self.added.append(obj)
        self._admin = obj

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def _refusing_prompt() -> str:
    raise AssertionError("password prompt must not run when admin already exists")


def test_explicit_run_creates_admin_with_zero_password_output(capsys) -> None:
    """Explicit CLI run creates the admin; the plaintext password is never printed."""
    session = _FakeSession()

    created = bootstrap_admin(session, password_prompt=lambda: "correct-horse-battery")

    captured = capsys.readouterr().out
    assert created is True
    assert len(session.added) == 1
    assert session.commits == 1
    assert session.rollbacks == 0
    new_admin = session.added[0]
    assert new_admin.username == ADMIN_USERNAME
    assert new_admin.role == "ADMIN"
    assert check_password_hash(new_admin.password, "correct-horse-battery")
    assert "correct-horse-battery" not in captured


def test_existing_admin_is_idempotent_no_duplicate_no_change(capsys) -> None:
    """An existing admin short-circuits: no prompt, no write, no duplicate row."""
    existing_admin = User(
        username=ADMIN_USERNAME,
        password="already-hashed",
        name="관리자",
        role="ADMIN",
        is_active=True,
    )
    session = _FakeSession(admin=existing_admin)

    created = bootstrap_admin(session, password_prompt=_refusing_prompt)

    captured = capsys.readouterr().out
    assert created is False
    assert session.added == []
    assert session.commits == 0
    assert session.rollbacks == 0
    assert "already exists" in captured


def test_password_never_appears_in_stdout_for_any_outcome(capsys) -> None:
    """Neither the create path nor the idempotent path echo the password."""
    secret = "never-log-me-1234"

    bootstrap_admin(_FakeSession(), password_prompt=lambda: secret)
    created_output = capsys.readouterr().out
    assert secret not in created_output

    existing_admin = User(
        username=ADMIN_USERNAME, password="x", name="관리자", role="ADMIN", is_active=True
    )
    bootstrap_admin(_FakeSession(admin=existing_admin), password_prompt=_refusing_prompt)
    idempotent_output = capsys.readouterr().out
    assert secret not in idempotent_output


def test_prompt_password_rejects_blank(monkeypatch) -> None:
    """A blank password is refused before it ever reaches the hasher."""
    monkeypatch.setattr("getpass.getpass", lambda _prompt: "   ")

    with pytest.raises(SystemExit, match="blank"):
        _prompt_password()


def test_prompt_password_rejects_mismatched_confirmation(monkeypatch) -> None:
    """A confirmation that doesn't match the first entry is refused."""
    responses = iter(["first-secret", "second-secret"])
    monkeypatch.setattr("getpass.getpass", lambda _prompt: next(responses))

    with pytest.raises(SystemExit, match="do not match"):
        _prompt_password()


def test_startup_auto_bootstrap_is_not_wired() -> None:
    """``run_auto_init`` must not create or reference the admin account at all.

    Admin bootstrap moved to the explicit CLI (STARTUP-ADMIN-01); the WSGI
    startup path (``foms/services/app_init.py``) must carry zero admin
    auto-create logic.
    """
    assert not hasattr(app_init, "_ensure_default_admin")
    assert not hasattr(app_init, "_get_bootstrap_admin_password")

    module_source = inspect.getsource(app_init)
    assert "from foms.persistence.main.models import User" not in module_source
    assert "generate_password_hash" not in module_source

    run_auto_init_source = inspect.getsource(app_init.run_auto_init)
    assert "_ensure_default_admin" not in run_auto_init_source
    assert "User(" not in run_auto_init_source
