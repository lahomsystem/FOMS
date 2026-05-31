"""P1-02: indexed erp_phone_digits for unified mobile search.

Revision ID: add_erp_phone_digits
Revises: merge_p0_order_drafts_sketchup
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "add_erp_phone_digits"
down_revision = "merge_p0_order_drafts_sketchup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add denormalized phone digits column + btree index; backfill from legacy phone."""
    op.add_column("orders", sa.Column("erp_phone_digits", sa.String(length=20), nullable=True))
    op.create_index("ix_orders_erp_phone_digits", "orders", ["erp_phone_digits"], unique=False)
    op.execute(
        """
        UPDATE orders
        SET erp_phone_digits = NULLIF(regexp_replace(COALESCE(phone, ''), '[^0-9]', '', 'g'), '')
        WHERE erp_phone_digits IS NULL
        """
    )


def downgrade() -> None:
    """Drop phone digits index and column."""
    op.drop_index("ix_orders_erp_phone_digits", table_name="orders")
    op.drop_column("orders", "erp_phone_digits")
