"""Phase C: active 주문 partial index + JSONB GIN 인덱스 (CONCURRENTLY)

Revision ID: phase_c_indexes
Revises: phase_c_geocode_cols
Create Date: 2026-03-15

CREATE INDEX CONCURRENTLY는 트랜잭션 블록 내에서 실행 불가.
별도 COMMIT 후 autocommit 모드에서 실행.
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


revision: str = 'phase_c_indexes'
down_revision: Union[str, None] = 'phase_c_geocode_cols'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _run_concurrently(conn, sql: str) -> None:
    """CONCURRENTLY DDL은 트랜잭션 외부에서 실행."""
    # 문자열 COMMIT 뒤 DDL 은 psycopg2 가 트랜잭션 상태를 추적하지 않아서만 통했다 — psycopg(3)는
    # 서버 상태를 보고 새 BEGIN 을 열어 CONCURRENTLY 가 실패한다. alembic autocommit_block 이 정본.
    with op.get_context().autocommit_block():
        op.get_bind().execute(text(sql))


def upgrade() -> None:
    conn = op.get_bind()
    # C-1: active 주문용 partial index
    _run_concurrently(
        conn,
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_orders_active_id "
        "ON orders (id DESC) WHERE status <> 'DELETED' AND deleted_at IS NULL"
    )
    # C-2: JSONB containment 전용 GIN 인덱스
    _run_concurrently(
        conn,
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_orders_structured_data_gin "
        "ON orders USING gin (structured_data)"
    )


def downgrade() -> None:
    conn = op.get_bind()
    _run_concurrently(conn, "DROP INDEX CONCURRENTLY IF EXISTS ix_orders_structured_data_gin")
    _run_concurrently(conn, "DROP INDEX CONCURRENTLY IF EXISTS ix_orders_active_id")
