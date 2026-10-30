"""MULTI-MGR-01: mine 필터 담당자 명단(parties.manager.names) 갈래 trgm 인덱스 (CONCURRENTLY)

Revision ID: mine_manager_names_idx_00
Revises: csagent_01
Create Date: 2026-10-30

담당자 여러 명(2026-10-30): 대표는 ``parties.manager.name``, 전체 명단은 ``parties.manager.names``
에 둔다. ``erp_permissions.build_mine_sql_filter`` 가 명단 갈래를 더했으므로 MINE-TOPDRAW-00 계약
(mine 패턴 가지마다 같은 식의 trgm 인덱스)대로 같은 식의 인덱스를 더한다. 처음에는 값이 있는 행이
없어 인덱스가 거의 비어 있다.

``mine_toplevel_drawing_idx_00`` 과 같은 모양: 멱등 additive, INVALID 잔해는 지우고 다시 만든다,
PostgreSQL 전용. 테이블·데이터는 건드리지 않는다.
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


revision: str = 'mine_manager_names_idx_00'
down_revision: Union[str, None] = 'csagent_01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'orders'

# 인덱스 이름 -> mine 갈래의 왼쪽 식(앱이 내는 SQL 에서 ``orders.`` 만 뺀 것).
MINE_TRGM_INDEXES: dict[str, str] = {
    'ix_orders_sd_manager_names_trgm':
        "CAST(((structured_data -> 'parties') -> 'manager') -> 'names' AS VARCHAR)",
}

_INDEX_VALIDITY_SQL = text("SELECT indisvalid FROM pg_index WHERE indexrelid = to_regclass(:name)")


def create_index_sql(name: str) -> str:
    """``name`` 인덱스를 만드는 DDL(멱등)."""
    return (
        f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON {TABLE} "
        f"USING gin (({MINE_TRGM_INDEXES[name]}) gin_trgm_ops)"
    )


def drop_index_sql(name: str) -> str:
    """``name`` 인덱스를 지우는 DDL(멱등)."""
    return f"DROP INDEX CONCURRENTLY IF EXISTS {name}"


def index_validity(conn, name: str) -> bool | None:
    """``None`` = 인덱스 없음, ``True`` = 정상, ``False`` = 빌드 실패로 남은 INVALID."""
    return conn.execute(_INDEX_VALIDITY_SQL, {'name': name}).scalar()


def _run_concurrently(conn, sql: str) -> None:
    """CONCURRENTLY DDL 은 트랜잭션 밖에서 실행한다(PG 레인 테스트는 AUTOCOMMIT 연결로 부른다)."""
    if conn.get_execution_options().get('isolation_level') == 'AUTOCOMMIT':
        conn.execute(text(sql))
        return
    with op.get_context().autocommit_block():
        op.get_bind().execute(text(sql))


def _ensure_valid_index(conn, name: str) -> None:
    """INVALID 로 남은 같은 이름 인덱스를 지우고 만든 뒤, valid 인지 확인한다."""
    if index_validity(conn, name) is False:
        print(f'[MULTI-MGR-01] {name} 이 INVALID 로 남아 있어 지우고 다시 만든다.')
        _run_concurrently(conn, drop_index_sql(name))
    _run_concurrently(conn, create_index_sql(name))
    if index_validity(conn, name) is not True:
        raise RuntimeError(f'[MULTI-MGR-01] {name} 을 만든 뒤에도 valid 가 아니다 — 배포를 멈춘다.')


def _apply_upgrade(conn) -> None:
    """확장 확인 후 인덱스를 만든다(``upgrade`` 와 PG 레인 테스트가 같이 쓴다)."""
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    for name in MINE_TRGM_INDEXES:
        _ensure_valid_index(conn, name)


def _apply_downgrade(conn) -> None:
    """이 마이그레이션이 만든 인덱스만 지운다(데이터 무손실)."""
    for name in reversed(list(MINE_TRGM_INDEXES)):
        _run_concurrently(conn, drop_index_sql(name))


def upgrade() -> None:
    """mine 담당자 명단(parties.manager.names) trgm 인덱스를 멱등 additive 로 만든다(PostgreSQL 전용)."""
    conn = op.get_bind()
    if conn.dialect.name != 'postgresql':
        return
    _apply_upgrade(conn)


def downgrade() -> None:
    """mine 담당자 명단(parties.manager.names) trgm 인덱스를 지운다(PostgreSQL 전용)."""
    conn = op.get_bind()
    if conn.dialect.name != 'postgresql':
        return
    _apply_downgrade(conn)
