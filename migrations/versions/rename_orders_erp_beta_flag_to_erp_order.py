"""Rename orders ERP flag column to canonical is_erp_order.

Revision ID: rename_orders_erp_order_flag
Revises: 2502107448c0
Create Date: 2026-04-17
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


revision: str = "rename_orders_erp_order_flag"
down_revision: Union[str, None] = "2502107448c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(conn, table_name: str, column_name: str) -> bool:
    inspector = inspect(conn)
    return any(column.get("name") == column_name for column in inspector.get_columns(table_name))


def _has_index(conn, table_name: str, index_name: str) -> bool:
    inspector = inspect(conn)
    return any(index.get("name") == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    conn = op.get_bind()
    has_legacy = _has_column(conn, "orders", "is_erp_beta")
    has_canonical = _has_column(conn, "orders", "is_erp_order")

    if has_legacy and not has_canonical:
        op.alter_column(
            "orders",
            "is_erp_beta",
            new_column_name="is_erp_order",
            existing_type=sa.Boolean(),
            existing_nullable=False,
            existing_server_default=sa.text("false"),
        )
    elif has_legacy and has_canonical:
        conn.execute(
            text(
                """
                UPDATE orders
                SET is_erp_order = (COALESCE(is_erp_order, FALSE) OR COALESCE(is_erp_beta, FALSE))
                """
            )
        )
        op.drop_column("orders", "is_erp_beta")
    elif not has_canonical:
        op.add_column(
            "orders",
            sa.Column("is_erp_order", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )

    if _has_index(conn, "orders", "ix_orders_is_erp_beta"):
        if _has_column(conn, "orders", "is_erp_order") and not _has_index(conn, "orders", "ix_orders_is_erp_order"):
            op.execute(text("ALTER INDEX ix_orders_is_erp_beta RENAME TO ix_orders_is_erp_order"))
        elif not _has_column(conn, "orders", "is_erp_beta"):
            op.drop_index("ix_orders_is_erp_beta", table_name="orders")

    if _has_column(conn, "orders", "is_erp_order") and not _has_index(conn, "orders", "ix_orders_is_erp_order"):
        op.create_index("ix_orders_is_erp_order", "orders", ["is_erp_order"])


def downgrade() -> None:
    conn = op.get_bind()
    has_legacy = _has_column(conn, "orders", "is_erp_beta")
    has_canonical = _has_column(conn, "orders", "is_erp_order")

    if has_canonical and not has_legacy:
        op.alter_column(
            "orders",
            "is_erp_order",
            new_column_name="is_erp_beta",
            existing_type=sa.Boolean(),
            existing_nullable=False,
            existing_server_default=sa.text("false"),
        )
    elif has_canonical and has_legacy:
        conn.execute(
            text(
                """
                UPDATE orders
                SET is_erp_beta = (COALESCE(is_erp_beta, FALSE) OR COALESCE(is_erp_order, FALSE))
                """
            )
        )
        op.drop_column("orders", "is_erp_order")
    elif not has_legacy:
        op.add_column(
            "orders",
            sa.Column("is_erp_beta", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )

    if _has_index(conn, "orders", "ix_orders_is_erp_order"):
        if _has_column(conn, "orders", "is_erp_beta") and not _has_index(conn, "orders", "ix_orders_is_erp_beta"):
            op.execute(text("ALTER INDEX ix_orders_is_erp_order RENAME TO ix_orders_is_erp_beta"))
        elif not _has_column(conn, "orders", "is_erp_order"):
            op.drop_index("ix_orders_is_erp_order", table_name="orders")

    if _has_column(conn, "orders", "is_erp_beta") and not _has_index(conn, "orders", "ix_orders_is_erp_beta"):
        op.create_index("ix_orders_is_erp_beta", "orders", ["is_erp_beta"])
