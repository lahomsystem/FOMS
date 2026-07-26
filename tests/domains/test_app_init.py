"""Focused tests for automatic app bootstrap helpers."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy.exc import OperationalError

import foms.services.app_init as app_init


class _FakeReadinessSession:
    """Minimal session double for flat-column readiness checks."""

    def __init__(self, *, fail_mode: str | None = None, dialect_name: str = "postgresql") -> None:
        self.fail_mode = fail_mode
        self.executed_sql = []
        self.rollbacks = 0
        self._bind = SimpleNamespace(dialect=SimpleNamespace(name=dialect_name))

    def get_bind(self):
        return self._bind

    def execute(self, statement):
        sql = str(statement)
        self.executed_sql.append(sql)
        if self.fail_mode == "missing" and "SELECT" in sql:
            raise RuntimeError("missing-flat-columns")
        if self.fail_mode == "lock_timeout" and "SELECT" in sql:
            orig = SimpleNamespace(pgcode="55P03")
            raise OperationalError(sql, None, orig)
        return None

    def rollback(self) -> None:
        self.rollbacks += 1


def test_verify_erp_flat_columns_ready_executes_zero_row_probe(monkeypatch, capsys):
    session = _FakeReadinessSession()
    monkeypatch.setattr(app_init, "get_db", lambda: session)

    app_init._verify_erp_flat_columns_ready()

    captured = capsys.readouterr().out
    assert any("SET LOCAL lock_timeout" in sql for sql in session.executed_sql)
    assert any("erp_measurement_date" in sql for sql in session.executed_sql)
    assert any("erp_stage_updated_at" in sql for sql in session.executed_sql)
    assert session.rollbacks == 1
    assert "ERP flat-column readiness verified." in captured


def test_verify_erp_flat_columns_ready_raises_when_probe_fails(monkeypatch):
    session = _FakeReadinessSession(fail_mode="missing")
    monkeypatch.setattr(app_init, "get_db", lambda: session)

    with pytest.raises(app_init.StartupReadinessError):
        app_init._verify_erp_flat_columns_ready()

    assert session.rollbacks == 1


def test_verify_erp_flat_columns_ready_tolerates_lock_timeout(monkeypatch, capsys):
    session = _FakeReadinessSession(fail_mode="lock_timeout")
    monkeypatch.setattr(app_init, "get_db", lambda: session)

    app_init._verify_erp_flat_columns_ready()

    captured = capsys.readouterr().out
    assert session.rollbacks == 1
    assert "lock timeout" in captured


class _FakeBackfillFlag:
    def is_(self, value):
        assert value is True
        return ("is", value)


class _FakeOrderByColumn:
    def desc(self):
        return "created_at_desc"


class _FakeBackfillOrderModel:
    is_erp_order = _FakeBackfillFlag()
    created_at = _FakeOrderByColumn()

    @staticmethod
    def active_filter():
        return "active"


class _FakeBackfillQuery:
    def __init__(self, rows) -> None:
        self.rows = rows
        self.filters = None
        self.ordering = None
        self.limit_value = None

    def filter(self, *criteria):
        self.filters = criteria
        return self

    def order_by(self, *ordering):
        self.ordering = ordering
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    def all(self):
        return self.rows


class _FakeBackfillSession:
    def __init__(self, rows) -> None:
        self.rows = rows
        self.commits = 0
        self.rollbacks = 0

    def query(self, model):
        assert model is _FakeBackfillOrderModel
        return _FakeBackfillQuery(self.rows)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def test_backfill_erp_flat_columns_resyncs_all_structured_rows(monkeypatch):
    rows = [
        SimpleNamespace(
            structured_data={"workflow": {"stage": "MEASURE"}},
            erp_stage_code="MEASURE",
        ),
        SimpleNamespace(structured_data={}, erp_stage_code="STALE"),
        SimpleNamespace(structured_data=None, erp_stage_code=None),
    ]
    session = _FakeBackfillSession(rows)
    sync_calls = []

    monkeypatch.setattr(app_init, "get_db", lambda: session)

    import foms.persistence.main.models as models_module
    import foms.services.erp_sync_columns as sync_module

    monkeypatch.setattr(models_module, "Order", _FakeBackfillOrderModel)
    monkeypatch.setattr(
        sync_module,
        "sync_erp_flat_columns",
        lambda order, structured_data: sync_calls.append((order, structured_data)),
    )

    app_init._backfill_erp_flat_columns()

    assert sync_calls == [
        (rows[0], rows[0].structured_data),
        (rows[1], rows[1].structured_data),
    ]
    assert session.commits == 1
    assert session.rollbacks == 0


def test_backfill_erp_flat_columns_skips_lock_timeout(monkeypatch, capsys):
    class _LockTimeoutSession:
        def __init__(self) -> None:
            self.rollbacks = 0
            self._bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

        def get_bind(self):
            return self._bind

        def execute(self, statement):
            sql = str(statement)
            if "SELECT" in sql:
                orig = SimpleNamespace(pgcode="55P03")
                raise OperationalError(sql, None, orig)
            return None

        def query(self, model):
            raise AssertionError("query should not run after lock timeout")

        def rollback(self) -> None:
            self.rollbacks += 1

    session = _LockTimeoutSession()
    monkeypatch.setattr(app_init, "get_db", lambda: session)

    app_init._backfill_erp_flat_columns()

    captured = capsys.readouterr().out
    assert session.rollbacks == 1
    assert "lock timeout" in captured


def test_run_auto_init_uses_internal_startup_policy(monkeypatch):
    calls = []

    class _FakeAppContext:
        def __enter__(self):
            calls.append("enter_app_context")
            return self

        def __exit__(self, exc_type, exc, tb):
            calls.append("exit_app_context")
            return False

    class _FakeApp:
        def app_context(self):
            return _FakeAppContext()

    import foms.services.order_date_sync as order_date_sync_module

    # STARTUP-SCHEMA-01: run_auto_init no longer invokes any ensure-schema DDL helper
    # (attachment columns / erp flat columns / phase-2 indexes are owned by Alembic
    # migration startup_schema_00, applied in predeploy). Only the create_all baseline
    # and the fail-closed readiness probe remain on the schema path.
    monkeypatch.setattr(app_init, "init_db", lambda: calls.append("init_db"))
    monkeypatch.setattr(app_init, "init_wdcalculator_db", lambda: calls.append("init_wdcalculator_db"))
    monkeypatch.setattr(
        app_init,
        "_verify_erp_flat_columns_ready",
        lambda: calls.append("verify_erp_flat_columns_ready"),
    )
    monkeypatch.setattr(
        app_init,
        "_backfill_erp_flat_columns",
        lambda: calls.append("backfill_erp_flat_columns"),
    )
    monkeypatch.setattr(
        order_date_sync_module,
        "register_date_sync_listener",
        lambda: calls.append("register_date_sync_listener"),
    )
    app_init.run_auto_init(_FakeApp())

    assert calls == [
        "enter_app_context",
        "init_db",
        "init_wdcalculator_db",
        "verify_erp_flat_columns_ready",
        "backfill_erp_flat_columns",
        "register_date_sync_listener",
        "exit_app_context",
    ]
