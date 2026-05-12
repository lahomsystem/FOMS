"""Focused tests for automatic app bootstrap helpers."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy.exc import OperationalError
from werkzeug.security import check_password_hash

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

    import foms.api.attachments as attachments_module
    import foms.services.db_indexes as db_indexes_module
    import foms.services.order_date_sync as order_date_sync_module

    monkeypatch.setattr(app_init, "init_db", lambda: calls.append("init_db"))
    monkeypatch.setattr(
        attachments_module,
        "ensure_order_attachments_category_column",
        lambda: calls.append("attachments_category"),
    )
    monkeypatch.setattr(
        attachments_module,
        "ensure_order_attachments_item_index_column",
        lambda: calls.append("attachments_item_index"),
    )
    monkeypatch.setattr(
        attachments_module,
        "ensure_order_attachments_user_id_column",
        lambda: calls.append("attachments_user_id"),
    )
    monkeypatch.setattr(app_init, "init_wdcalculator_db", lambda: calls.append("init_wdcalculator_db"))
    monkeypatch.setattr(
        db_indexes_module,
        "apply_phase2_indexes",
        lambda: calls.append("apply_phase2_indexes"),
    )
    monkeypatch.setattr(
        db_indexes_module,
        "ensure_erp_date_columns",
        lambda: calls.append("ensure_erp_date_columns"),
    )
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
    fake_db_session = object()
    monkeypatch.setattr(app_init, "get_db", lambda: fake_db_session)
    monkeypatch.setattr(
        app_init,
        "_ensure_default_admin",
        lambda session: calls.append(("ensure_default_admin", session)),
    )

    app_init.run_auto_init(_FakeApp())

    assert calls == [
        "enter_app_context",
        "init_db",
        "attachments_category",
        "attachments_item_index",
        "attachments_user_id",
        "init_wdcalculator_db",
        "apply_phase2_indexes",
        "ensure_erp_date_columns",
        "verify_erp_flat_columns_ready",
        "backfill_erp_flat_columns",
        "register_date_sync_listener",
        ("ensure_default_admin", fake_db_session),
        "exit_app_context",
    ]


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
