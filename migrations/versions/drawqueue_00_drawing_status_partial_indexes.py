"""DRAWQUEUE-01: 도면 작업실 모집단 술어용 drawing_status 부분 인덱스

Revision ID: drawqueue_00
Revises: assort_00
Create Date: 2026-08-23

도면 작업실 seed 가 "최신 N건" 대신 **도면 모집단**(단계 ∪ RETURNED ∪ 옵션 CONFIRMED)을
SQL 로 선스코프하도록 바뀌었다(2026-08-23 운영 사고: 프로세스 맵 28건 vs 작업실 1건 —
접수순 창 밖 27건 실종). 단계 축은 기존 ``ix_orders_erp_stage_code`` 가 받지만,
RETURNED/CONFIRMED 축은 ``structured_data`` JSON 경로라 인덱스가 없으면 OR 전체가
Seq Scan 으로 추락한다(운영 실측: 0.75ms → 43.5ms).

**순수 additive**: 부분 인덱스 3개만 더한다. RETURNED/CONFIRMED 행은 상시 소수라
인덱스 크기가 무시할 수준이다. 두 키를 각각 잡는 이유는 라우트 행 판정이
``sd['drawing']['status'] or sd['drawing_status']`` 순으로 읽기 때문이며, 술어는 두 키를
단순 동등 비교 OR 로 나란히 본다(coalesce 로 합치면 predicate 매칭이 깨진다).

로컬 PostgreSQL 검증: 세 인덱스가 BitmapOr 로 함께 선택됨(Seq Scan 없음).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'drawqueue_00'
down_revision: Union[str, None] = 'assort_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 인덱스 식은 build_drawing_queue_filter() 가 만드는 SQL 과 문자 그대로 대응해야 한다
# (foms/services/drawing_workbench_read_model.py). 어긋나면 조용히 Seq Scan 으로 떨어진다.
_INDEX_DDL: tuple[str, ...] = (
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_orders_workflow_stage_drawing "
    "ON orders ((CAST(structured_data #>> '{workflow,stage}' AS VARCHAR))) "
    "WHERE CAST(structured_data #>> '{workflow,stage}' AS VARCHAR) IN ('DRAWING', '도면')",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_orders_drawing_status_flat_active "
    "ON orders ((CAST(structured_data ->> 'drawing_status' AS VARCHAR))) "
    "WHERE CAST(structured_data ->> 'drawing_status' AS VARCHAR) IN ('RETURNED', 'CONFIRMED')",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_orders_drawing_status_nested_active "
    "ON orders ((CAST(structured_data #>> '{drawing,status}' AS VARCHAR))) "
    "WHERE CAST(structured_data #>> '{drawing,status}' AS VARCHAR) IN ('RETURNED', 'CONFIRMED')",
)

_DROP_DDL: tuple[str, ...] = (
    "DROP INDEX CONCURRENTLY IF EXISTS ix_orders_workflow_stage_drawing",
    "DROP INDEX CONCURRENTLY IF EXISTS ix_orders_drawing_status_nested_active",
    "DROP INDEX CONCURRENTLY IF EXISTS ix_orders_drawing_status_flat_active",
)


def _run_concurrently(conn, sql: str) -> None:
    """CONCURRENTLY DDL 은 트랜잭션 밖에서 실행 — 열린 트랜잭션을 COMMIT 후 실행.

    startup_schema_00 과 동일 패턴. env.py 의 세션 advisory lock 이 내부 COMMIT 을 넘어
    유지되므로 다중 replica 동시 인덱스 빌드가 직렬화된다.
    """
    conn.execute(sa.text("COMMIT"))
    conn.execute(sa.text(sql))


def upgrade() -> None:
    """도면 모집단 부분 인덱스 3개를 멱등 additive 로 생성(존재하면 no-op)."""
    conn = op.get_bind()
    if conn.dialect.name != 'postgresql':
        return
    for statement in _INDEX_DDL:
        _run_concurrently(conn, statement)


def downgrade() -> None:
    """이 마이그레이션이 만든 인덱스만 되돌린다(데이터 무손실)."""
    conn = op.get_bind()
    if conn.dialect.name != 'postgresql':
        return
    for statement in _DROP_DDL:
        _run_concurrently(conn, statement)
