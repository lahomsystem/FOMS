"""Add ERP stage transition timestamp flat column.

Revision ID: add_orders_erp_stage_updated_at
Revises: rename_orders_erp_order_flag
Create Date: 2026-05-12
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "add_orders_erp_stage_updated_at"
down_revision: Union[str, None] = "rename_orders_erp_order_flag"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(conn, table_name: str, column_name: str) -> bool:
    inspector = inspect(conn)
    return any(column.get("name") == column_name for column in inspector.get_columns(table_name))


def _has_index(conn, table_name: str, index_name: str) -> bool:
    inspector = inspect(conn)
    return any(index.get("name") == index_name for index in inspector.get_indexes(table_name))


def _is_postgresql(conn) -> bool:
    return getattr(getattr(conn, "dialect", None), "name", None) == "postgresql"


def upgrade() -> None:
    conn = op.get_bind()
    if not _has_column(conn, "orders", "erp_stage_updated_at"):
        op.add_column("orders", sa.Column("erp_stage_updated_at", sa.DateTime(), nullable=True))

    if _has_index(conn, "orders", "ix_orders_erp_stage_updated_at"):
        return

    if _is_postgresql(conn):
        with op.get_context().autocommit_block():
            op.execute(
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
                "ix_orders_erp_stage_updated_at ON orders (erp_stage_updated_at)"
            )
    else:
        op.create_index(
            "ix_orders_erp_stage_updated_at",
            "orders",
            ["erp_stage_updated_at"],
        )


def downgrade() -> None:
    conn = op.get_bind()
    if _has_index(conn, "orders", "ix_orders_erp_stage_updated_at"):
        if _is_postgresql(conn):
            with op.get_context().autocommit_block():
                op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_orders_erp_stage_updated_at")
        else:
            op.drop_index("ix_orders_erp_stage_updated_at", table_name="orders")

    if _has_column(conn, "orders", "erp_stage_updated_at"):
        op.drop_column("orders", "erp_stage_updated_at")
