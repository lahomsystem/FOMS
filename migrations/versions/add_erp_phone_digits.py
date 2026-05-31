"""P1-02: indexed erp_phone_digits for unified mobile search.

Revision ID: add_erp_phone_digits
Revises: merge_p0_order_drafts_sketchup
"""

from __future__ import annotations

import re

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision = "add_erp_phone_digits"
down_revision = "merge_p0_order_drafts_sketchup"
branch_labels = None
depends_on = None

_DIGIT_RE = re.compile(r"[^0-9]")


def _is_postgresql(conn) -> bool:
    return getattr(getattr(conn, "dialect", None), "name", None) == "postgresql"


def _backfill_erp_phone_digits(conn) -> None:
    """SQLite/CI: Python backfill (PostgreSQL ``regexp_replace`` unavailable)."""
    rows = conn.execute(
        text("SELECT id, phone FROM orders WHERE erp_phone_digits IS NULL")
    ).fetchall()
    for row in rows:
        raw = row.phone if row.phone is not None else ""
        digits = _DIGIT_RE.sub("", str(raw).strip()) or None
        conn.execute(
            text("UPDATE orders SET erp_phone_digits = :digits WHERE id = :id"),
            {"digits": digits, "id": row.id},
        )


def upgrade() -> None:
    """Add denormalized phone digits column + btree index; backfill from legacy phone."""
    op.add_column("orders", sa.Column("erp_phone_digits", sa.String(length=20), nullable=True))
    op.create_index("ix_orders_erp_phone_digits", "orders", ["erp_phone_digits"], unique=False)
    conn = op.get_bind()
    if _is_postgresql(conn):
        op.execute(
            """
            UPDATE orders
            SET erp_phone_digits = NULLIF(regexp_replace(COALESCE(phone, ''), '[^0-9]', '', 'g'), '')
            WHERE erp_phone_digits IS NULL
            """
        )
    else:
        _backfill_erp_phone_digits(conn)


def downgrade() -> None:
    """Drop phone digits index and column."""
    op.drop_index("ix_orders_erp_phone_digits", table_name="orders")
    op.drop_column("orders", "erp_phone_digits")
