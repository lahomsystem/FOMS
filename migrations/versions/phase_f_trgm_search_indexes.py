"""Phase F: general-ilike hot path trigram GIN indexes CONCURRENTLY

Revision ID: phase_f_trgm_search_indexes
Revises: phase_e_trgm_perm_indexes
Create Date: 2026-07-01

baseline_debt.json general-ilike hot path: orders 컬럼·SD 가시 경로, chat, 첨부, users, security_logs.
표현식은 SQLAlchemy ``.as_string()`` / ``CAST(.. AS VARCHAR)`` 생성 SQL과 byte 일치.
CONCURRENTLY는 트랜잭션 외부 실행(phase_c/phase_d/phase_e 동일 패턴).
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


revision: str = 'phase_f_trgm_search_indexes'
down_revision: Union[str, None] = 'phase_e_trgm_perm_indexes'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# table, index_name, column (simple ILIKE)
_SIMPLE_TRGM_INDEXES: list[tuple[str, str, str]] = [
    ("orders", "ix_orders_customer_name_trgm", "customer_name"),
    ("orders", "ix_orders_address_trgm", "address"),
    ("orders", "ix_orders_phone_trgm", "phone"),
    ("orders", "ix_orders_product_trgm", "product"),
    ("orders", "ix_orders_notes_trgm", "notes"),
    ("orders", "ix_orders_regional_memo_trgm", "regional_memo"),
    ("chat_rooms", "ix_chat_rooms_name_trgm", "name"),
    ("chat_messages", "ix_chat_messages_content_trgm", "content"),
    ("order_attachments", "ix_order_attachments_filename_trgm", "filename"),
    ("users", "ix_users_name_trgm", "name"),
    ("security_logs", "ix_security_logs_message_trgm", "message"),
]

# index_name -> 표현식 (erp_dashboard_search structured_visible_fields)
_ORDER_SD_TRGM_INDEXES: dict[str, str] = {
    "ix_orders_sd_customer_name_trgm":
        "CAST(((structured_data -> 'parties') -> 'customer') ->> 'name' AS VARCHAR)",
    "ix_orders_sd_customer_phone_trgm":
        "CAST(((structured_data -> 'parties') -> 'customer') ->> 'phone' AS VARCHAR)",
    "ix_orders_sd_orderer_name_trgm":
        "CAST(((structured_data -> 'parties') -> 'orderer') ->> 'name' AS VARCHAR)",
    "ix_orders_sd_site_address_full_trgm":
        "CAST((structured_data -> 'site') ->> 'address_full' AS VARCHAR)",
    "ix_orders_sd_site_address_main_trgm":
        "CAST((structured_data -> 'site') ->> 'address_main' AS VARCHAR)",
    "ix_orders_sd_items0_product_name_trgm":
        "CAST(((structured_data -> 'items') -> 0) ->> 'product_name' AS VARCHAR)",
    "ix_orders_sd_items0_name_trgm":
        "CAST(((structured_data -> 'items') -> 0) ->> 'name' AS VARCHAR)",
    "ix_orders_sd_meas_date_trgm":
        "CAST(((structured_data -> 'schedule') -> 'measurement') ->> 'date' AS VARCHAR)",
    "ix_orders_sd_meas_time_trgm":
        "CAST(((structured_data -> 'schedule') -> 'measurement') ->> 'time' AS VARCHAR)",
    "ix_orders_sd_construction_date_trgm":
        "CAST(((structured_data -> 'schedule') -> 'construction') ->> 'date' AS VARCHAR)",
}

# downgrade reverse order (upgrade append 순서)
_ALL_INDEX_NAMES: list[str] = (
    [name for _, name, _ in _SIMPLE_TRGM_INDEXES]
    + list(_ORDER_SD_TRGM_INDEXES)
)


def _run_concurrently(conn, sql: str) -> None:
    """CONCURRENTLY DDL은 트랜잭션 외부에서 실행."""
    conn.execute(text("COMMIT"))
    conn.execute(text(sql))


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    for table, name, column in _SIMPLE_TRGM_INDEXES:
        _run_concurrently(
            conn,
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} "
            f"ON {table} USING gin ({column} gin_trgm_ops)"
        )
    for name, expr in _ORDER_SD_TRGM_INDEXES.items():
        _run_concurrently(
            conn,
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} "
            f"ON orders USING gin (({expr}) gin_trgm_ops)"
        )


def downgrade() -> None:
    conn = op.get_bind()
    for name in reversed(_ALL_INDEX_NAMES):
        _run_concurrently(conn, f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
