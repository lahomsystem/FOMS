"""Legacy schema bootstrap helpers for attachments."""

from sqlalchemy import inspect, text

from db import get_db
from foms.services.user_deletion import ensure_order_attachment_user_fk_set_null


def _column_exists(db, table_name: str, column_name: str) -> bool:
    """Return whether a table already has the target column."""
    bind = db.get_bind()
    inspector = inspect(bind)
    return any(
        column.get("name") == column_name
        for column in inspector.get_columns(table_name)
    )


def _ensure_order_attachment_column(column_name: str, ddl_suffix: str) -> bool:
    """Add an attachment column only when it does not already exist."""
    db = None
    try:
        db = get_db()
        if _column_exists(db, "order_attachments", column_name):
            return True

        db.execute(
            text(
                "ALTER TABLE order_attachments "
                f"ADD COLUMN {ddl_suffix}"
            )
        )
        db.commit()
        return True
    except Exception as e:
        try:
            if db is not None:
                db.rollback()
        except Exception:
            pass
        print(f"[AUTO-MIGRATION] Failed to ensure order_attachments.{column_name}: {e}")
        return False


def ensure_order_attachments_category_column():
    """레거시 DB용: order_attachments.category 컬럼 존재 보장."""
    return _ensure_order_attachment_column(
        "category",
        "category VARCHAR(50) NOT NULL DEFAULT 'measurement'",
    )


def ensure_order_attachments_item_index_column():
    """레거시 DB용: order_attachments.item_index 컬럼 존재 보장."""
    return _ensure_order_attachment_column(
        "item_index",
        "item_index INTEGER NULL",
    )


def ensure_order_attachments_user_id_column():
    """레거시 DB용: order_attachments.user_id 컬럼 존재 보장."""
    db = None
    try:
        db = get_db()
        if not _column_exists(db, "order_attachments", "user_id"):
            db.execute(
                text(
                    "ALTER TABLE order_attachments "
                    "ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE SET NULL"
                )
            )
        ensure_order_attachment_user_fk_set_null(db)
        db.commit()
        return True
    except Exception as e:
        try:
            if db is not None:
                db.rollback()
        except Exception:
            pass
        print(f"[AUTO-MIGRATION] Failed to ensure order_attachments.user_id: {e}")
        return False


__all__ = [
    "ensure_order_attachments_category_column",
    "ensure_order_attachments_item_index_column",
    "ensure_order_attachments_user_id_column",
]
