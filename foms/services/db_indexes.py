"""Database index and flat-column bootstrap helpers."""

from __future__ import annotations

import logging
import re

from sqlalchemy import inspect, text

from db import get_db

__all__ = [
    "apply_phase2_indexes",
    "ensure_erp_date_columns",
]

_log = logging.getLogger(__name__)


def _get_bind(db):
    """Return the active SQLAlchemy bind when available."""
    try:
        return db.get_bind()
    except Exception:
        return getattr(db, "bind", None)


def _dialect_name(db) -> str:
    """Best-effort dialect lookup, defaulting to PostgreSQL for fake test doubles."""
    bind = _get_bind(db)
    name = getattr(getattr(bind, "dialect", None), "name", None)
    return name or "postgresql"


def _column_exists(db, table_name: str, column_name: str) -> bool:
    """Return whether a table already has the target column."""
    bind = _get_bind(db)
    if bind is None:
        return False
    inspector = inspect(bind)
    return any(
        column.get("name") == column_name
        for column in inspector.get_columns(table_name)
    )


def _ensure_column(db, table_name: str, column_name: str, ddl_suffix: str) -> None:
    """Add a column only when it does not already exist."""
    if _column_exists(db, table_name, column_name):
        return
    db.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl_suffix}"))


def apply_phase2_indexes() -> None:
    """Apply Phase 2~4 PostgreSQL indexes that are not managed in model metadata."""
    db = get_db()

    if _dialect_name(db) == "postgresql":
        try:
            db.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm;"))
            db.commit()
            _log.info("[AUTO-INIT] pg_trgm extension verified.")

            db.execute(text("CREATE INDEX IF NOT EXISTS idx_order_measure_date_trgm ON orders USING gin (measurement_date gin_trgm_ops);"))
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_order_schedule_date_trgm ON orders USING gin (scheduled_date gin_trgm_ops);"))
            db.commit()
            _log.info("[AUTO-INIT] Phase 2: Trigram Indexes verified/created successfully.")
        except Exception as e:
            db.rollback()
            _log.warning("[AUTO-INIT] Warning: Could not create trigram indexes (or pg_trgm not supported): %s", e, exc_info=True)
    else:
        _log.info("[AUTO-INIT] Skipping pg_trgm indexes on non-PostgreSQL database.")

    try:
        db.execute(
            text(
                """
            CREATE INDEX IF NOT EXISTS ix_osd_measurement_date
            ON order_schedule_dates (date, order_id)
            WHERE kind = 'measurement';
        """
            )
        )
        db.execute(
            text(
                """
            CREATE INDEX IF NOT EXISTS ix_osd_construction_date
            ON order_schedule_dates (date, order_id)
            WHERE kind = 'construction';
        """
            )
        )
        db.execute(
            text(
                """
            CREATE INDEX IF NOT EXISTS ix_osd_as_visit_date
            ON order_schedule_dates (date, order_id)
            WHERE kind = 'as_visit';
        """
            )
        )
        db.commit()
        _log.info("[AUTO-INIT] Phase 4: OrderScheduleDate Partial Indexes verified/created successfully.")
    except Exception as e:
        db.rollback()
        _log.warning("[AUTO-INIT] Warning: Could not create OrderScheduleDate partial indexes: %s", e, exc_info=True)


def ensure_erp_date_columns() -> None:
    """Ensure denormalized ERP flat columns used by large-list filters and paging."""
    db = get_db()
    try:
        _ensure_column(db, "orders", "erp_measurement_date", "VARCHAR(10)")
        _ensure_column(db, "orders", "erp_construction_date", "VARCHAR(10)")
        db.execute(text("CREATE INDEX IF NOT EXISTS ix_orders_erp_measurement_date ON orders (erp_measurement_date)"))
        db.execute(text("CREATE INDEX IF NOT EXISTS ix_orders_erp_construction_date ON orders (erp_construction_date)"))

        _ensure_column(db, "orders", "erp_stage_code", "VARCHAR(30)")
        _ensure_column(db, "orders", "erp_urgent", "BOOLEAN DEFAULT FALSE NOT NULL")
        _ensure_column(db, "orders", "erp_drawing_updated_at", "TIMESTAMP")
        _ensure_column(db, "orders", "erp_owner_team_code", "VARCHAR(20)")

        db.execute(text("CREATE INDEX IF NOT EXISTS ix_orders_erp_stage_code ON orders (erp_stage_code)"))
        db.execute(text("CREATE INDEX IF NOT EXISTS ix_orders_erp_urgent ON orders (erp_urgent)"))
        db.execute(text("CREATE INDEX IF NOT EXISTS ix_orders_erp_owner_team_code ON orders (erp_owner_team_code)"))

        db.commit()
        _log.info("[AUTO-INIT] Phase B & D flat columns verified.")
    except Exception as e:
        db.rollback()
        _log.warning("[AUTO-INIT] Failed to add erp_date/flat columns: %s", e)
