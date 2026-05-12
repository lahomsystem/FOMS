"""Regression tests for SQLite local-startup compatibility."""

import logging
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

import foms.api.files.legacy as attachment_legacy
import foms.services.db_indexes as db_indexes
from wdcalculator_models import Estimate, EstimateHistory, WDCalculatorBase

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MIGRATIONS_DIR = _REPO_ROOT / "scripts" / "migrations"
if str(_MIGRATIONS_DIR) not in sys.path:
    sys.path.insert(0, str(_MIGRATIONS_DIR))
import safe_schema_migration as safe_schema_migration_module  # noqa: E402
from safe_schema_migration import SafeSchemaMigration  # noqa: E402


def test_safe_schema_migration_uses_sqlite_inspector_and_json_fallback() -> None:
    """SQLite should not depend on PostgreSQL information_schema or JSONB DDL."""
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE orders (id INTEGER PRIMARY KEY)"))

    session = sessionmaker(bind=engine)()
    migration = SafeSchemaMigration()

    assert migration.check_column_exists(session, "id") is True
    assert migration.check_column_exists(session, "structured_data") is False
    assert migration._normalized_column_type(session, "JSONB") == "JSON"

    assert migration.add_column_safely(session, "structured_data", "JSONB") is True
    session.commit()

    columns = inspect(engine).get_columns("orders")
    assert any(column.get("name") == "structured_data" for column in columns)


def test_safe_schema_migration_rejects_legacy_erp_beta_schema(monkeypatch, caplog) -> None:
    """Canonical-only startup should fail loudly when legacy ERP flag columns remain."""
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE orders (
                    id INTEGER PRIMARY KEY,
                    is_erp_beta BOOLEAN DEFAULT 0
                )
                """
            )
        )

    session = sessionmaker(bind=engine)()
    migration = SafeSchemaMigration()
    monkeypatch.setattr(safe_schema_migration_module, "get_db", lambda: session)

    with caplog.at_level(logging.ERROR):
        assert migration.execute_migration() is False

    columns = {column["name"] for column in inspect(engine).get_columns("orders")}
    assert "is_erp_beta" in columns
    assert "is_erp_order" not in columns
    assert any("Automatic rename has been retired" in record.message for record in caplog.records)


def test_wdcalculator_estimate_tables_create_on_sqlite() -> None:
    """WDCalculator tables should create on SQLite without JSONB compiler errors."""
    engine = create_engine("sqlite:///:memory:")

    WDCalculatorBase.metadata.create_all(
        bind=engine,
        tables=[Estimate.__table__, EstimateHistory.__table__],
    )

    inspector = inspect(engine)
    estimate_columns = {column["name"] for column in inspector.get_columns("estimates")}
    history_columns = {
        column["name"] for column in inspector.get_columns("estimate_histories")
    }

    assert "estimate_data" in estimate_columns
    assert "estimate_data" in history_columns


def test_attachment_bootstrap_adds_columns_on_sqlite(monkeypatch) -> None:
    """Attachment bootstrap should avoid PostgreSQL-only ALTER TABLE syntax on SQLite."""
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE order_attachments (id INTEGER PRIMARY KEY)"))

    session = sessionmaker(bind=engine)()
    monkeypatch.setattr(attachment_legacy, "get_db", lambda: session)
    monkeypatch.setattr(
        attachment_legacy,
        "ensure_order_attachment_user_fk_set_null",
        lambda db: None,
    )

    assert attachment_legacy.ensure_order_attachments_category_column() is True
    assert attachment_legacy.ensure_order_attachments_item_index_column() is True
    assert attachment_legacy.ensure_order_attachments_user_id_column() is True

    columns = inspect(engine).get_columns("order_attachments")
    column_names = {column["name"] for column in columns}
    assert {"category", "item_index", "user_id"}.issubset(column_names)


def test_db_index_bootstrap_skips_postgres_only_bits_on_sqlite(monkeypatch, caplog) -> None:
    """SQLite startup should skip pg_trgm setup and still add ERP flat columns."""
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE orders (
                    id INTEGER PRIMARY KEY,
                    measurement_date VARCHAR,
                    scheduled_date VARCHAR
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE order_schedule_dates (
                    id INTEGER PRIMARY KEY,
                    date VARCHAR,
                    order_id INTEGER,
                    kind VARCHAR
                )
                """
            )
        )

    session = sessionmaker(bind=engine)()
    monkeypatch.setattr(db_indexes, "get_db", lambda: session)

    with caplog.at_level(logging.INFO):
        db_indexes.apply_phase2_indexes()
        db_indexes.ensure_erp_date_columns()

    order_columns = {column["name"] for column in inspect(engine).get_columns("orders")}
    assert "erp_measurement_date" in order_columns
    assert "erp_stage_updated_at" in order_columns
    assert "erp_owner_team_code" in order_columns
    assert any("Skipping pg_trgm indexes" in record.message for record in caplog.records)
    assert not any("Could not create trigram indexes" in record.message for record in caplog.records)
