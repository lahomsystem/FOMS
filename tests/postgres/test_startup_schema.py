"""STARTUP-SCHEMA-01: runtime ensure-schema DDL -> Alembic + fail-closed startup.

Two layers:

* Static (no DB): the ensure-repair DDL is gone from ``run_auto_init`` (web startup
  DDL 0), a missing schema fails closed instead of self-healing, the migration is
  a single head on top of ``wdc_link_backfill_00``, it is expand-only, and its
  downgrade is a non-destructive no-op.
* PostgreSQL lane (opt-in via ``FOMS_TEST_DATABASE_URL``): the migration's DDL,
  applied to a database whose columns/indexes were dropped to simulate legacy
  drift, recreates them and is idempotent on re-run.

No credentials are embedded — the PG lane DSN comes from the environment.
"""
from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

import foms.services.app_init as app_init

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MIGRATION_PATH = (
    _REPO_ROOT / "migrations" / "versions" / "startup_schema_00_ensure_orders_flat_and_indexes.py"
)

# The runtime ensure-repair helpers that must no longer run at web startup.
_ENSURE_HELPER_NAMES = (
    "apply_phase2_indexes",
    "ensure_erp_date_columns",
    "ensure_order_attachments_category_column",
    "ensure_order_attachments_item_index_column",
    "ensure_order_attachments_user_id_column",
)


def _load_migration():
    """Import the startup_schema_00 migration module by file path."""
    spec = importlib.util.spec_from_file_location("startup_schema_00_mig", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------- #
# Static: web startup issues zero ensure-schema DDL, and fails closed.
# --------------------------------------------------------------------------- #


def test_run_auto_init_invokes_no_ensure_schema_helper() -> None:
    """No ensure-repair DDL helper is called from run_auto_init (web startup DDL 0)."""
    source = inspect.getsource(app_init.run_auto_init)
    for name in _ENSURE_HELPER_NAMES:
        assert name not in source, f"{name} must not run at web startup"


def test_run_auto_init_keeps_fail_closed_readiness_probe() -> None:
    """The fail-closed readiness probe stays wired so a missing schema is fatal."""
    source = inspect.getsource(app_init.run_auto_init)
    assert "_verify_erp_flat_columns_ready()" in source


def test_run_auto_init_propagates_readiness_error(monkeypatch) -> None:
    """A missing flat-column schema fails app startup instead of silently creating it."""

    class _FakeAppContext:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _FakeApp:
        def app_context(self):
            return _FakeAppContext()

    monkeypatch.setattr(app_init, "init_db", lambda: None)
    monkeypatch.setattr(app_init, "init_wdcalculator_db", lambda: None)

    def _raise() -> None:
        raise app_init.StartupReadinessError("erp flat columns missing")

    monkeypatch.setattr(app_init, "_verify_erp_flat_columns_ready", _raise)

    with pytest.raises(app_init.StartupReadinessError):
        app_init.run_auto_init(_FakeApp())


# --------------------------------------------------------------------------- #
# Static: single head, additive expand, non-destructive downgrade.
# --------------------------------------------------------------------------- #


def test_migration_chains_onto_current_head() -> None:
    """startup_schema_00 revises the batch head wdc_link_backfill_00."""
    module = _load_migration()
    assert module.revision == "startup_schema_00"
    assert module.down_revision == "wdc_link_backfill_00"


def test_alembic_has_single_head() -> None:
    """The script directory resolves to exactly one head (no branching).

    이 불변식은 "분기 없는 단일 head"이지 특정 revision 핀이 아니다 — 정상 마이그레이션은
    head 를 이동시키므로 값 하드코딩은 stale 회귀를 만든다. 개수만 검증한다.
    """
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config(str(_REPO_ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(config)
    assert len(script.get_heads()) == 1, script.get_heads()


def test_upgrade_is_expand_only() -> None:
    """Upgrade adds columns/indexes only — no destructive DDL."""
    module = _load_migration()
    for statement in module._COLUMN_DDL:
        upper = statement.upper()
        assert "ADD COLUMN IF NOT EXISTS" in upper
        assert "DROP" not in upper
    for statement in module._INDEX_DDL:
        upper = statement.upper()
        assert upper.startswith("CREATE EXTENSION") or "CREATE INDEX" in upper
        assert "IF NOT EXISTS" in upper
        assert "DROP" not in upper


def test_downgrade_is_non_destructive_noop() -> None:
    """Additive migration: downgrade body must be a pure no-op (never drops)."""
    import ast
    import textwrap

    module = _load_migration()
    tree = ast.parse(textwrap.dedent(inspect.getsource(module.downgrade)))
    func = tree.body[0]
    assert isinstance(func, ast.FunctionDef)
    body = func.body
    # Strip the docstring (its prose explains *why* we refuse to drop).
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    # Whatever remains must be nothing but `pass` — no op.drop_*, no executed DDL.
    assert body, "downgrade should contain an explicit pass"
    assert all(isinstance(node, ast.Pass) for node in body), (
        "downgrade must be a no-op; additive migration may not drop schema"
    )


# --------------------------------------------------------------------------- #
# PostgreSQL lane: the migration DDL recreates dropped schema, idempotently.
# --------------------------------------------------------------------------- #


def test_migration_ddl_recreates_dropped_schema(pg_engine) -> None:
    """Dropping ensure-owned columns/indexes then applying the migration restores them."""
    module = _load_migration()

    dropped_columns = {
        "orders": "erp_phone_digits",
        "order_attachments": "user_id",
    }
    # Indexes the migration solely owns (not created by create_all / ORM models).
    migration_only_indexes = {
        "idx_order_measure_date_trgm",
        "idx_order_schedule_date_trgm",
        "ix_osd_measurement_date",
        "ix_osd_construction_date",
        "ix_osd_as_visit_date",
    }

    with pg_engine.connect() as conn:
        ac = conn.execution_options(isolation_level="AUTOCOMMIT")

        # Simulate a legacy/drifted database: strip a representative column pair
        # (their btree indexes drop with them) and any pre-existing migration-only
        # indexes so the migration is proven to be their creator.
        ac.exec_driver_sql("ALTER TABLE orders DROP COLUMN IF EXISTS erp_phone_digits")
        ac.exec_driver_sql("ALTER TABLE order_attachments DROP COLUMN IF EXISTS user_id")
        for index_name in migration_only_indexes:
            ac.exec_driver_sql(f"DROP INDEX IF EXISTS {index_name}")

        # Apply the migration DDL twice to prove idempotency (IF NOT EXISTS).
        for _ in range(2):
            for statement in module._COLUMN_DDL:
                ac.exec_driver_sql(statement)
            for statement in module._INDEX_DDL:
                ac.exec_driver_sql(statement)

        # Columns are back.
        for table, column in dropped_columns.items():
            present = ac.exec_driver_sql(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = %(t)s AND column_name = %(c)s",
                {"t": table, "c": column},
            ).fetchone()
            assert present is not None, f"{table}.{column} was not recreated"

        # Every index the migration ensures now exists.
        index_rows = ac.exec_driver_sql(
            "SELECT indexname FROM pg_indexes WHERE schemaname = 'public'"
        ).fetchall()
        index_names = {row[0] for row in index_rows}
        expected_indexes = migration_only_indexes | {
            "ix_orders_erp_measurement_date",
            "ix_orders_erp_construction_date",
            "ix_orders_erp_stage_code",
            "ix_orders_erp_urgent",
            "ix_orders_erp_stage_updated_at",
            "ix_orders_erp_owner_team_code",
            "ix_orders_erp_phone_digits",
        }
        missing = expected_indexes - index_names
        assert not missing, f"migration did not create indexes: {sorted(missing)}"
