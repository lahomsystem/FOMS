"""Phase D: pg_trgm GIN 인덱스 (manager_name + structured_data text) CONCURRENTLY

Revision ID: phase_d_trgm_indexes
Revises: add_erp_phone_digits
Create Date: 2026-06-16

근본 원인: 다중 사용자 ERP 대시보드/검색의 핵심 필터가
``manager_name ILIKE '%..%'`` 및 ``CAST(structured_data AS VARCHAR) ILIKE '%..%'``
형태인데, 기존 인덱스(B-tree, jsonb_ops GIN)는 ILIKE 부분일치를 못 탄다 →
주문 행수 N에 비례한 Seq Scan이 매 요청 발생(대시보드 카운트/검색/담당자 mine 필터).

해결: pg_trgm trigram GIN 인덱스로 ILIKE '%..%'를 인덱스 스캔 가능하게 한다.
- 쿼리/시맨틱 변경 0. 기존 ILIKE 표현식 형태를 그대로 인덱스가 백킹한다.
- 인덱스 표현식은 SQLAlchemy가 생성하는 SQL(``CAST(structured_data AS VARCHAR)``)과
  byte 단위로 일치시켰고, EXPLAIN(seqscan off)으로 Bitmap Index Scan 사용을 사전 검증했다.

CREATE INDEX CONCURRENTLY는 트랜잭션 블록 내 실행 불가 → COMMIT 후 autocommit 실행
(phase_c_indexes_concurrently 동일 패턴).
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


revision: str = 'phase_d_trgm_indexes'
down_revision: Union[str, None] = 'add_erp_phone_digits'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _run_concurrently(conn, sql: str) -> None:
    """CONCURRENTLY DDL은 트랜잭션 외부에서 실행."""
    conn.execute(text("COMMIT"))
    conn.execute(text(sql))


def upgrade() -> None:
    conn = op.get_bind()
    # D-0: trigram 확장 (ILIKE '%..%' 인덱스 전제)
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    # D-1: manager_name 부분일치 (mine/visibility 필터 conds[0], 대시보드 검색)
    _run_concurrently(
        conn,
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_orders_manager_name_trgm "
        "ON orders USING gin (manager_name gin_trgm_ops)"
    )
    # D-2: structured_data 전체 blob 부분일치
    # (nav badge mine 필터, 생산 dashboard mine 필터, 통합 검색, 지도 검색 등)
    _run_concurrently(
        conn,
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_orders_structured_data_text_trgm "
        "ON orders USING gin (CAST(structured_data AS VARCHAR) gin_trgm_ops)"
    )


def downgrade() -> None:
    conn = op.get_bind()
    _run_concurrently(conn, "DROP INDEX CONCURRENTLY IF EXISTS ix_orders_structured_data_text_trgm")
    _run_concurrently(conn, "DROP INDEX CONCURRENTLY IF EXISTS ix_orders_manager_name_trgm")
    # pg_trgm 확장은 다른 인덱스가 쓸 수 있어 downgrade에서 제거하지 않는다.
