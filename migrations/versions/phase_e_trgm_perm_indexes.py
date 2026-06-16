"""Phase E: ERP 가시성(mine) 필터 per-field trigram GIN 인덱스 CONCURRENTLY

Revision ID: phase_e_trgm_perm_indexes
Revises: phase_d_trgm_indexes
Create Date: 2026-06-16

근본 원인(Phase 2): ``erp_permissions.build_mine_sql_filter``의 가시성 OR 필터는
비-ADMIN 모든 ERP 리스트(대시보드/control tower/실측/시공)에 적용되는 hot path인데,
nested-path cast ILIKE 브랜치(parties.manager.name, owner_person, construction_workers,
drawing_assignees, sales/drawing_assignee_user_ids)가 인덱스를 못 타 OR 전체가 Seq Scan.
Phase D의 manager_name/blob trigram 인덱스는 nested-path cast 표현식과 형태가 달라
이 브랜치들을 백킹하지 못한다.

설계 판단(시맨틱 보존):
- assignee_user_ids는 request raw 값으로 저장되어 int/str 혼재 가능(읽기 시 _normalize_ids가
  int() 방어). 따라서 @> containment로 바꾸면 타입 불일치로 본인 주문 누락(under-grant) 위험 →
  기존 cast ILIKE(타입 무관 부분일치)를 그대로 유지한다. 쿼리/Auth 로직 변경 0.
- 대신 각 브랜치의 정확한 표현식에 trigram GIN 인덱스를 추가해 OR을 BitmapOr로 만든다.

검증: 인덱스 표현식을 SQLAlchemy 생성 SQL(`->` literal-key + CAST(.. AS VARCHAR))과
일치시키고, 로컬 PostgreSQL EXPLAIN(seqscan off)으로 각 브랜치 인덱스 사용 +
결합 OR이 Seq Scan 없이 BitmapOr로 처리됨을 사전 검증함.

CONCURRENTLY는 트랜잭션 외부 실행(phase_c/phase_d 동일 패턴).
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


revision: str = 'phase_e_trgm_perm_indexes'
down_revision: Union[str, None] = 'phase_d_trgm_indexes'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# index_name -> 인덱싱할 표현식 (SQLAlchemy 생성 SQL과 byte 일치)
_PERM_TRGM_INDEXES: dict[str, str] = {
    "ix_orders_sd_manager_name_trgm":
        "CAST(((structured_data -> 'parties') -> 'manager') -> 'name' AS VARCHAR)",
    "ix_orders_sd_owner_person_trgm":
        "CAST(((structured_data -> 'workflow') -> 'current_quest') -> 'owner_person' AS VARCHAR)",
    "ix_orders_sd_construction_workers_trgm":
        "CAST((structured_data -> 'shipment') -> 'construction_workers' AS VARCHAR)",
    "ix_orders_sd_drawing_assignees_trgm":
        "CAST((structured_data -> 'assignments') -> 'drawing_assignees' AS VARCHAR)",
    "ix_orders_sd_sales_ids_trgm":
        "CAST((structured_data -> 'assignments') -> 'sales_assignee_user_ids' AS VARCHAR)",
    "ix_orders_sd_drawing_ids_trgm":
        "CAST((structured_data -> 'assignments') -> 'drawing_assignee_user_ids' AS VARCHAR)",
}


def _run_concurrently(conn, sql: str) -> None:
    """CONCURRENTLY DDL은 트랜잭션 외부에서 실행."""
    conn.execute(text("COMMIT"))
    conn.execute(text(sql))


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    for name, expr in _PERM_TRGM_INDEXES.items():
        _run_concurrently(
            conn,
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} "
            f"ON orders USING gin (({expr}) gin_trgm_ops)"
        )


def downgrade() -> None:
    conn = op.get_bind()
    for name in reversed(list(_PERM_TRGM_INDEXES)):
        _run_concurrently(conn, f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
