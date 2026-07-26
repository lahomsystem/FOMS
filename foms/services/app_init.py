"""WSGI startup-time automatic DB initialization helpers."""

from __future__ import annotations

from foms.persistence.main.db import get_db, init_db
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from wdcalculator_db import init_wdcalculator_db

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


def run_auto_init(app) -> None:
    """Ensure DB tables exist and repair bounded ERP flat-column drift on WSGI startup.

    Admin bootstrap is intentionally excluded (STARTUP-ADMIN-01): run
    ``tools/ops/bootstrap_admin.py`` explicitly to create the admin account.
    """
    try:
        with app.app_context():
            print("[AUTO-INIT] Checking database tables...")
            init_db()
            init_wdcalculator_db()
            # STARTUP-SCHEMA-01: web replica 는 ensure-repair DDL 을 실행하지 않는다.
            # 컬럼/인덱스 스키마는 predeploy.sh 의 ``alembic upgrade head``(마이그레이션
            # startup_schema_00)가 replica 부팅 전에 확정한다. 아래 readiness 체크는
            # 스키마가 없으면 StartupReadinessError 로 앱을 fail-closed 시킨다(조용히 생성 금지).
            _verify_erp_flat_columns_ready()
            _backfill_erp_flat_columns()

            from foms.services.order_date_sync import register_date_sync_listener

            register_date_sync_listener()
            # STARTUP-ADMIN-01: admin bootstrap is explicit-only (operator runs
            # tools/ops/bootstrap_admin.py). Startup never auto-creates admin.
    except StartupReadinessError:
        raise
    except Exception as e:
        print(f"[AUTO-INIT] Database initialization failed: {e}")
