"""WSGI startup-time automatic DB initialization helpers."""

from __future__ import annotations

import os

from foms.persistence.main.db import get_db, init_db
from foms.persistence.main.models import User
from sqlalchemy.orm import Session
from wdcalculator_db import init_wdcalculator_db
from werkzeug.security import generate_password_hash

__all__ = ["run_auto_init"]


def _backfill_erp_flat_columns(app) -> None:
    """Backfill ERP flat columns when structured ERP stage data diverges."""
    try:
        from foms.persistence.main.models import Order
        from foms.services.erp_sync_columns import sync_erp_flat_columns

        db_session = get_db()
        targets = (
            db_session.query(Order)
            .filter(Order.active_filter(), Order.is_erp_beta.is_(True))
            .all()
        )
        if not targets:
            return
        count = 0
        for order in targets:
            if not order.structured_data:
                continue
            sd_stage = ((order.structured_data or {}).get("workflow") or {}).get("stage")
            if order.erp_stage_code != sd_stage:
                sync_erp_flat_columns(order, order.structured_data)
                count += 1
        if count:
            db_session.commit()
            print(f"[AUTO-INIT] Backfilled erp_stage_code for {count} orders.")
    except Exception as e:
        if "db_session" in locals():
            db_session.rollback()
        print(f"[AUTO-INIT] erp_stage_code backfill failed: {e}")


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

            _backfill_erp_flat_columns(app)

            from foms.services.order_date_sync import register_date_sync_listener

            register_date_sync_listener()

            db_session = get_db()
            _ensure_default_admin(db_session)
    except Exception as e:
        print(f"[AUTO-INIT] Database initialization failed: {e}")
