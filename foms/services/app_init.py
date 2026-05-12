"""WSGI startup-time automatic DB initialization helpers."""

from __future__ import annotations

import os

from foms.persistence.main.db import get_db, init_db
from foms.persistence.main.models import User
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from wdcalculator_db import init_wdcalculator_db
from werkzeug.security import generate_password_hash

__all__ = ["run_auto_init"]


class StartupReadinessError(RuntimeError):
    """Raised when startup-safe bootstrap detects an unsupported DB readiness state."""


_BACKFILL_LOCK_TIMEOUT_MS = 1000
_BACKFILL_STATEMENT_TIMEOUT_MS = 5000
_BACKFILL_BATCH_SIZE = 200


def _apply_postgresql_timeouts(
    db_session: Session,
    *,
    lock_timeout_ms: int,
    statement_timeout_ms: int,
) -> None:
    """Apply bounded PostgreSQL timeouts for startup maintenance queries."""
    try:
        bind = db_session.get_bind()
    except Exception:
        bind = getattr(db_session, "bind", None)
    dialect_name = getattr(getattr(bind, "dialect", None), "name", None)
    if dialect_name != "postgresql":
        return
    db_session.execute(text(f"SET LOCAL lock_timeout = '{lock_timeout_ms}ms'"))
    db_session.execute(text(f"SET LOCAL statement_timeout = '{statement_timeout_ms}ms'"))


def _backfill_erp_flat_columns() -> None:
    """Backfill a bounded batch of active ERP rows during startup."""
    try:
        from foms.persistence.main.models import Order
        from foms.services.erp_sync_columns import sync_erp_flat_columns

        db_session = get_db()
        _apply_postgresql_timeouts(
            db_session,
            lock_timeout_ms=_BACKFILL_LOCK_TIMEOUT_MS,
            statement_timeout_ms=_BACKFILL_STATEMENT_TIMEOUT_MS,
        )
        targets = (
            db_session.query(Order)
            .filter(Order.active_filter(), Order.is_erp_order.is_(True))
            .order_by(Order.created_at.desc())
            .limit(_BACKFILL_BATCH_SIZE)
            .all()
        )
        if not targets:
            db_session.rollback()
            return
        count = 0
        for order in targets:
            if order.structured_data is None:
                continue
            sync_erp_flat_columns(order, order.structured_data)
            count += 1
        if count:
            db_session.commit()
            print(f"[AUTO-INIT] Backfilled ERP flat columns for {count} recent active ERP orders.")
        else:
            db_session.rollback()
    except OperationalError as e:
        if "db_session" in locals():
            db_session.rollback()
        pgcode = getattr(getattr(e, "orig", None), "pgcode", None)
        orig_name = type(getattr(e, "orig", None)).__name__
        if pgcode == "55P03" or orig_name == "LockNotAvailable":
            print("[AUTO-INIT] ERP flat-column backfill skipped due to lock timeout.")
            return
        print(f"[AUTO-INIT] ERP flat-column backfill failed: {e}")
    except Exception as e:
        if "db_session" in locals():
            db_session.rollback()
        print(f"[AUTO-INIT] ERP flat-column backfill failed: {e}")


def _verify_erp_flat_columns_ready() -> None:
    """Fail fast when automatic startup repair cannot confirm required ERP flat columns."""
    db_session = get_db()
    try:
        _apply_postgresql_timeouts(
            db_session,
            lock_timeout_ms=1000,
            statement_timeout_ms=3000,
        )

        db_session.execute(
            text(
                """
                SELECT
                    erp_measurement_date,
                    erp_construction_date,
                    erp_stage_code,
                    erp_urgent,
                    erp_drawing_updated_at,
                    erp_stage_updated_at,
                    erp_owner_team_code
                FROM orders
                WHERE 1 = 0
                """
            )
        )
        print("[AUTO-INIT] ERP flat-column readiness verified.")
    except OperationalError as exc:
        pgcode = getattr(getattr(exc, "orig", None), "pgcode", None)
        orig_name = type(getattr(exc, "orig", None)).__name__
        if pgcode == "55P03" or orig_name == "LockNotAvailable":
            print(
                "[AUTO-INIT] ERP flat-column readiness check skipped due to lock timeout; "
                "continuing bounded startup policy."
            )
            return
        raise StartupReadinessError(
            "ERP flat columns are unavailable after automatic startup repair."
        ) from exc
    except Exception as exc:
        raise StartupReadinessError(
            "ERP flat columns are unavailable after automatic startup repair."
        ) from exc
    finally:
        db_session.rollback()


def _get_bootstrap_admin_password() -> str | None:
    """Return the configured bootstrap password for automatic admin creation."""
    password = (os.environ.get("FOMS_ADMIN_DEFAULT_PASSWORD") or "").strip()
    return password or None


def _ensure_default_admin(db_session: Session) -> None:
    """Create the default admin only when an explicit bootstrap password is set."""
    try:
        admin = db_session.query(User).filter_by(username="admin").first()
        if admin:
            print("[AUTO-INIT] Admin user exists.")
            return

        password = _get_bootstrap_admin_password()
        if not password:
            print(
                "[AUTO-INIT] Admin user missing; skipping automatic admin bootstrap "
                "because FOMS_ADMIN_DEFAULT_PASSWORD is not set."
            )
            return

        print("[AUTO-INIT] Creating default admin user from configured bootstrap password.")
        new_admin = User(
            username="admin",
            password=generate_password_hash(password),
            name="관리자",
            role="ADMIN",
            is_active=True,
        )
        db_session.add(new_admin)
        db_session.commit()
    except Exception as e:
        print(f"[AUTO-INIT] Failed to create admin user: {e}")
        db_session.rollback()


def run_auto_init(app) -> None:
    """Ensure DB tables and optionally bootstrap the admin account on WSGI startup."""
    try:
        with app.app_context():
            print("[AUTO-INIT] Checking database tables...")
            init_db()
            from foms.api.attachments import (
                ensure_order_attachments_category_column,
                ensure_order_attachments_item_index_column,
                ensure_order_attachments_user_id_column,
            )

            ensure_order_attachments_category_column()
            ensure_order_attachments_item_index_column()
            ensure_order_attachments_user_id_column()
            init_wdcalculator_db()
            from foms.services.db_indexes import apply_phase2_indexes, ensure_erp_date_columns

            apply_phase2_indexes()
            ensure_erp_date_columns()
            _verify_erp_flat_columns_ready()
            _backfill_erp_flat_columns()

            from foms.services.order_date_sync import register_date_sync_listener

            register_date_sync_listener()

            db_session = get_db()
            _ensure_default_admin(db_session)
    except StartupReadinessError:
        raise
    except Exception as e:
        print(f"[AUTO-INIT] Database initialization failed: {e}")
