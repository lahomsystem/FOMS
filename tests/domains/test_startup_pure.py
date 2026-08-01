"""STARTUP-PURE-01 contract: import/startup performs zero DB write/DDL.

These tests pin the purified startup path:

* ``run_auto_init`` (WSGI/import path) invokes no ``create_all`` / backfill /
  stamp and never writes — only the read-only PostgreSQL readiness probe and the
  KST date-sync listener registration remain.
* The date-sync SQLAlchemy listener is still registered (kept wiring).
* ``verify_migrations_current`` fails closed (dev) when the database schema is
  behind the Alembic head, instead of silently auto-upgrading.
* The readiness probe is PostgreSQL-only: SQLite (tests / local QA) owns its
  schema via fixtures, so the probe short-circuits without touching the DB.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

import foms.services.app_init as app_init


class _FakeAppContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeApp:
    def app_context(self):
        return _FakeAppContext()


class _RecordingSession:
    """Session double that records SQL + write signals for the readiness probe."""

    def __init__(self, *, dialect_name: str = "postgresql") -> None:
        self.executed_sql: list[str] = []
        self.rollbacks = 0
        self.commits = 0
        self._bind = SimpleNamespace(dialect=SimpleNamespace(name=dialect_name))

    def get_bind(self):
        return self._bind

    def execute(self, statement):
        self.executed_sql.append(str(statement))
        return None

    def rollback(self) -> None:
        self.rollbacks += 1

    def commit(self) -> None:
        self.commits += 1


def _silence_startup_side_effects(monkeypatch) -> None:
    """Neutralize the readiness probe + listener so a test isolates one concern."""
    import foms.services.order_date_sync as order_date_sync_module

    monkeypatch.setattr(app_init, "_verify_erp_flat_columns_ready", lambda: None)
    monkeypatch.setattr(
        order_date_sync_module, "register_date_sync_listener", lambda: None
    )


def test_run_auto_init_invokes_no_ddl_or_backfill(monkeypatch):
    """The startup path must not call create_all baseline, wd init, or backfill."""
    calls: list[str] = []

    monkeypatch.setattr(app_init, "init_db", lambda: calls.append("init_db"))
    monkeypatch.setattr(
        app_init, "init_wdcalculator_db", lambda: calls.append("init_wdcalculator_db")
    )
    monkeypatch.setattr(
        app_init, "_backfill_erp_flat_columns", lambda: calls.append("backfill")
    )
    monkeypatch.setattr(
        app_init, "_verify_erp_flat_columns_ready", lambda: calls.append("verify")
    )
    import foms.services.order_date_sync as order_date_sync_module

    monkeypatch.setattr(
        order_date_sync_module,
        "register_date_sync_listener",
        lambda: calls.append("listener"),
    )

    app_init.run_auto_init(_FakeApp())

    assert "init_db" not in calls
    assert "init_wdcalculator_db" not in calls
    assert "backfill" not in calls
    # Only the read-only readiness probe and the listener wiring remain.
    assert calls == ["verify", "listener"]


def test_import_startup_path_calls_no_create_all(monkeypatch):
    """No table DDL (``create_all``) is emitted on the import/startup path."""
    import db as db_module
    import wdcalculator_db as wd_module

    create_all_calls: list[str] = []
    monkeypatch.setattr(
        db_module.Base.metadata,
        "create_all",
        lambda *a, **k: create_all_calls.append("main"),
    )
    monkeypatch.setattr(
        wd_module.WDCalculatorBase.metadata,
        "create_all",
        lambda *a, **k: create_all_calls.append("wd"),
    )
    _silence_startup_side_effects(monkeypatch)

    app_init.run_auto_init(_FakeApp())

    assert create_all_calls == []


def test_run_auto_init_registers_date_listener(monkeypatch):
    """STARTUP-PURE-01 keeps the KST date-sync listener wiring."""
    registered: list[bool] = []
    import foms.services.order_date_sync as order_date_sync_module

    monkeypatch.setattr(app_init, "_verify_erp_flat_columns_ready", lambda: None)
    monkeypatch.setattr(
        order_date_sync_module,
        "register_date_sync_listener",
        lambda: registered.append(True),
    )

    app_init.run_auto_init(_FakeApp())

    assert registered == [True]


def test_run_auto_init_readiness_probe_performs_no_write(monkeypatch):
    """The only DB touch on startup is a read-only probe — zero commits."""
    session = _RecordingSession(dialect_name="postgresql")
    monkeypatch.setattr(app_init, "get_db", lambda: session)
    import foms.services.order_date_sync as order_date_sync_module

    monkeypatch.setattr(
        order_date_sync_module, "register_date_sync_listener", lambda: None
    )

    app_init.run_auto_init(_FakeApp())

    assert session.commits == 0
    assert all("INSERT" not in sql and "UPDATE" not in sql for sql in session.executed_sql)


def test_verify_erp_flat_columns_ready_skips_non_postgres(monkeypatch, capsys):
    """SQLite owns its schema via fixtures; the readiness probe short-circuits."""
    session = _RecordingSession(dialect_name="sqlite")
    monkeypatch.setattr(app_init, "get_db", lambda: session)

    app_init._verify_erp_flat_columns_ready()

    captured = capsys.readouterr().out
    assert not any("erp_measurement_date" in sql for sql in session.executed_sql)
    assert session.rollbacks == 1
    assert "skipped" in captured.lower()


def test_verify_migrations_current_raises_when_pending(monkeypatch):
    """dev fail-closed: head != DB revision must raise (no silent upgrade)."""
    monkeypatch.setattr(app_init, "_alembic_heads", lambda: {"head_b"})
    monkeypatch.setattr(app_init, "_db_current_revisions", lambda engine: {"head_a"})
    engine = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

    with pytest.raises(app_init.StartupReadinessError):
        app_init.verify_migrations_current(engine)


def test_verify_migrations_current_passes_when_at_head(monkeypatch):
    """Zero-pending schema boots without complaint (no auto-init revival)."""
    monkeypatch.setattr(app_init, "_alembic_heads", lambda: {"head_b"})
    monkeypatch.setattr(app_init, "_db_current_revisions", lambda engine: {"head_b"})
    engine = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

    app_init.verify_migrations_current(engine)  # must not raise


def test_verify_migrations_current_skips_non_postgres(monkeypatch):
    """SQLite/local QA is not Alembic-managed; the check short-circuits."""
    touched: list[str] = []
    monkeypatch.setattr(
        app_init, "_alembic_heads", lambda: touched.append("heads") or {"x"}
    )
    monkeypatch.setattr(
        app_init,
        "_db_current_revisions",
        lambda engine: touched.append("current") or set(),
    )
    engine = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))

    app_init.verify_migrations_current(engine)  # must not raise

    assert touched == []


def test_run_startup_tasks_fails_closed_on_pending(monkeypatch):
    """run.py dev boot propagates the fail-closed signal instead of upgrading."""
    import run

    def _raise(engine):
        raise app_init.StartupReadinessError("pending migrations")

    monkeypatch.setattr(app_init, "verify_migrations_current", _raise)

    with pytest.raises(app_init.StartupReadinessError):
        run._run_startup_tasks(_FakeApp(), logging.getLogger("test_startup_pure"))


def test_run_startup_tasks_performs_no_ddl(monkeypatch):
    """run.py dev boot no longer runs init_db / wd init / safe migration."""
    import run

    monkeypatch.setattr(app_init, "verify_migrations_current", lambda engine: None)

    # Any residual DDL import would raise on access; a clean pass proves removal.
    run._run_startup_tasks(_FakeApp(), logging.getLogger("test_startup_pure"))
