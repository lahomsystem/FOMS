"""WSGI startup-time automatic DB initialization helpers."""

from __future__ import annotations

from pathlib import Path

from foms.persistence.main.db import get_db, init_db  # noqa: F401  # init_db: startup-purity spy seam (run_auto_init must NOT call it)
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from wdcalculator_db import init_wdcalculator_db  # noqa: F401  # spy seam (startup must NOT create wdcalculator tables)

__all__ = ["run_auto_init"]

# Repo-root ``alembic.ini`` (foms/services/app_init.py -> parents[2] == repo root).
_ALEMBIC_INI_PATH = Path(__file__).resolve().parents[2] / "alembic.ini"


class StartupReadinessError(RuntimeError):
    """Raised when startup-safe bootstrap detects an unsupported DB readiness state."""


_BACKFILL_LOCK_TIMEOUT_MS = 1000
_BACKFILL_STATEMENT_TIMEOUT_MS = 5000
_BACKFILL_BATCH_SIZE = 200


def _session_dialect_name(db_session: Session) -> str | None:
    """Return the SQLAlchemy dialect name bound to ``db_session`` (or None)."""
    try:
        bind = db_session.get_bind()
    except Exception:
        bind = getattr(db_session, "bind", None)
    return getattr(getattr(bind, "dialect", None), "name", None)


def _apply_postgresql_timeouts(
    db_session: Session,
    *,
    lock_timeout_ms: int,
    statement_timeout_ms: int,
) -> None:
    """Apply bounded PostgreSQL timeouts for startup maintenance queries."""
    if _session_dialect_name(db_session) != "postgresql":
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
    """Fail closed (read-only) when the required ERP flat columns are absent.

    PostgreSQL-only: SQLite (local QA / pytest) owns its schema via test
    fixtures / ``create_all``, not Alembic, so the probe short-circuits there
    instead of failing on an intentionally partial table.
    """
    db_session = get_db()
    if _session_dialect_name(db_session) != "postgresql":
        db_session.rollback()
        print("[AUTO-INIT] ERP flat-column readiness check skipped (non-PostgreSQL).")
        return
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
    """Wire startup-only side effects on WSGI import — never write or issue DDL.

    STARTUP-PURE-01: the import/startup path performs **zero** DB mutation. No
    ``create_all`` baseline, no ERP flat-column backfill, no ``alembic stamp`` —
    the schema is owned entirely by Alembic (``alembic upgrade head`` runs once
    in ``predeploy.sh`` before any replica boots). Startup keeps only:

    * ``_verify_erp_flat_columns_ready`` — a read-only PostgreSQL probe that
      fails the app closed when the required flat columns are absent, so a
      replica never serves against an unmigrated schema (and never self-heals).
    * ``register_date_sync_listener`` — pure SQLAlchemy listener wiring (no DB
      write) for KST date synchronization.
    * ``register_payment_sync_listener`` — pure SQLAlchemy listener wiring (no
      DB write) for the ``PAYMENT_CHANGED`` audit-event SSOT.

    Excluded on purpose: schema DDL (STARTUP-SCHEMA-01 → Alembic/predeploy),
    flat-column backfill (STARTUP-BACKFILL-01 → operator CLI), and admin
    bootstrap (STARTUP-ADMIN-01 → ``tools/ops/bootstrap_admin.py``). None of
    these are revived here when the schema is already current.
    """
    try:
        with app.app_context():
            # Read-only, PostgreSQL-only fail-closed readiness check. On a
            # missing/unmigrated schema this raises StartupReadinessError rather
            # than silently creating anything.
            _verify_erp_flat_columns_ready()

            from foms.services.order_date_sync import register_date_sync_listener

            register_date_sync_listener()

            from foms.services.order_payment_sync import register_payment_sync_listener

            register_payment_sync_listener()
    except StartupReadinessError:
        raise
    except Exception as e:
        print(f"[AUTO-INIT] Startup wiring failed: {e}")


def _alembic_heads() -> set[str]:
    """Return the Alembic migration script head revision id(s)."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config(str(_ALEMBIC_INI_PATH))
    return set(ScriptDirectory.from_config(config).get_heads())


def _db_current_revisions(engine) -> set[str]:
    """Return the Alembic revision id(s) currently stamped in ``engine``'s DB."""
    from alembic.migration import MigrationContext

    with engine.connect() as connection:
        return set(MigrationContext.configure(connection).get_current_heads())


def verify_migrations_current(engine) -> None:
    """Fail closed (dev) when the database schema is behind the Alembic head(s).

    Compares the migration script head(s) against the revision recorded in the
    database's ``alembic_version`` table. When they differ the local dev server
    refuses to boot instead of silently upgrading — the developer runs
    ``alembic upgrade head`` explicitly. When they match, nothing is created or
    backfilled (no auto-init revival).

    PostgreSQL-only: non-PostgreSQL engines (SQLite tests / local QA) are not
    Alembic-managed, so the check short-circuits without touching the DB.

    Args:
        engine: The SQLAlchemy engine bound to the database to verify.

    Raises:
        StartupReadinessError: When pending migrations are detected on
            PostgreSQL (silent auto-upgrade is disabled).
    """
    if getattr(getattr(engine, "dialect", None), "name", None) != "postgresql":
        return
    heads = _alembic_heads()
    current = _db_current_revisions(engine)
    if current != heads:
        raise StartupReadinessError(
            "Pending database migrations "
            f"(alembic head={sorted(heads)}, database={sorted(current)}). "
            "Run `alembic upgrade head` before starting the dev server; "
            "startup no longer performs a silent auto-upgrade."
        )
