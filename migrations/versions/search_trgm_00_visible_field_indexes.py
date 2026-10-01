"""SEARCH-TRGM-00: 검색 술어 가지마다 trgm 인덱스 5개 (CONCURRENTLY)

Revision ID: search_trgm_00
Revises: nvmirror_00
Create Date: 2026-10-01

왜: 과거 이력·통합 검색 술어(``erp_order_dashboard_search_predicate``)는 OR 가지가 19~20개다.
가지 하나라도 인덱스가 없으면 PostgreSQL 이 BitmapOr 를 만들지 못하고, 후보 행 전부를 읽으며
가지마다 ``structured_data`` 를 다시 푼다(TOAST). 스테이징 실측 "박성수" 이력 목록은
184ms·38,142 buf 였고, 막는 가지를 빼면 0.41ms·96 buf 였다. 막는 가지는 다섯이다.

* ``CAST(id AS VARCHAR) ILIKE`` — 주문번호 일부 검색. 동작은 그대로 둔다(결정 1-가).
* ``erp_phone_digits LIKE '%x%'`` — 기존 ``ix_orders_erp_phone_digits`` 는 btree 라 앞뒤 ``%``
  를 못 탄다. 가운데 자리 검색을 그대로 둔다(결정 2-가). btree 는 정확 일치 조회용으로 남긴다.
* SD ``parties.buyer.name``·``parties.buyer.phone`` (``->>``) — 가지만 늘고 인덱스가 없었다.
  과거 이력의 끝 4자리 정규식(``~``)도 buyer.phone 인덱스를 함께 탄다(trgm 은 정규식도 받는다).
* SD ``parties.manager.name`` (``->>``) — 기존 ``ix_orders_sd_manager_name_trgm`` 은 ``-> 'name'``
  (따옴표 붙은 JSON 문자열) 식이라 쓸 수 없다. 그 인덱스는 "내 담당" 필터가 쓰므로 그대로 둔다.

식은 SQLAlchemy 가 내는 SQL 과 글자 단위로 같다(인덱스 DDL 에 못 쓰는 ``orders.`` 접두만 뺐다).
``models.Order`` 의 같은 이름 Index 와도 같아야 한다 — ``tests/performance/
test_search_trgm_index_contract.py`` 와 PG 레인 ``tests/postgres/test_search_trgm_indexes_pg.py``
가 강제한다. 검색 술어 동작은 바꾸지 않는다(인덱스만). 마이그레이션 상수 동결 원칙에 따라
``models`` 를 import 하지 않는다(리터럴만 쓴다).

INVALID 처리: ``CREATE INDEX CONCURRENTLY`` 가 중간에 실패하면 INVALID 인덱스가 남는다.
``IF NOT EXISTS`` 는 그것도 "있다"고 보고 건너뛰어 쓸모없는 인덱스가 영영 남는다. 그래서 만들기
전에 ``pg_index.indisvalid = false`` 면 ``DROP INDEX CONCURRENTLY`` 후 다시 만든다. 만든 뒤에도
valid 가 아니면 예외를 낸다 — predeploy(``set -e``)가 실패해 새 배포가 라이브되지 않고 옛 버전이
계속 돈다.

잠금·소요: CONCURRENTLY 는 읽기·쓰기를 막지 않는다. 대신 시작 시점에 열려 있던 트랜잭션이 끝날
때까지 기다린다(이 마이그레이션에는 lock_timeout 이 없다 — 배포 직전 ``pg_stat_activity`` 에
오래 열린 트랜잭션이 없는지 본다). 다중 replica 의 동시 실행은 ``migrations/env.py`` 의 세션
advisory lock 이 직렬화한다. 로컬 6,000행 기준 인덱스 하나 22~42ms, 다섯 개 합계 약 0.66MB.

되돌리기: ``downgrade()`` 는 역순 ``DROP INDEX CONCURRENTLY IF EXISTS``. 검색 결과는 인덱스와
무관하고 속도만 달라지므로 언제 지워도 안전하다. ``pg_trgm`` 확장은 다른 인덱스가 쓰므로
지우지 않는다.

스펙: docs/specs/2026-10-01-search-index-perf_SPEC.md
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


revision: str = 'search_trgm_00'
down_revision: Union[str, None] = 'nvmirror_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = 'orders'

# 인덱스 이름 -> 검색 가지의 왼쪽 식(앱이 내는 SQL 에서 ``orders.`` 만 뺀 것). 순서 = upgrade 순서.
SEARCH_TRGM_INDEXES: dict[str, str] = {
    'ix_orders_sd_buyer_name_trgm':
        "CAST(((structured_data -> 'parties') -> 'buyer') ->> 'name' AS VARCHAR)",
    'ix_orders_sd_buyer_phone_trgm':
        "CAST(((structured_data -> 'parties') -> 'buyer') ->> 'phone' AS VARCHAR)",
    'ix_orders_sd_manager_name_text_trgm':
        "CAST(((structured_data -> 'parties') -> 'manager') ->> 'name' AS VARCHAR)",
    'ix_orders_erp_phone_digits_trgm': "erp_phone_digits",
    'ix_orders_id_text_trgm': "CAST(id AS VARCHAR)",
}

_INDEX_VALIDITY_SQL = text("SELECT indisvalid FROM pg_index WHERE indexrelid = to_regclass(:name)")


def _index_element(expression: str) -> str:
    """인덱스 원소 — 컬럼 하나면 그대로, 식이면 괄호로 감싼다(PostgreSQL 문법)."""
    return expression if expression.isidentifier() else f"({expression})"


def create_index_sql(name: str) -> str:
    """``name`` 인덱스를 만드는 DDL(멱등). 테스트가 models 정의와 글자 단위로 대조한다."""
    element = _index_element(SEARCH_TRGM_INDEXES[name])
    return f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON {TABLE} USING gin ({element} gin_trgm_ops)"


def drop_index_sql(name: str) -> str:
    """``name`` 인덱스를 지우는 DDL(멱등)."""
    return f"DROP INDEX CONCURRENTLY IF EXISTS {name}"


def index_validity(conn, name: str) -> bool | None:
    """``None`` = 인덱스 없음, ``True`` = 정상, ``False`` = 빌드 실패로 남은 INVALID."""
    return conn.execute(_INDEX_VALIDITY_SQL, {'name': name}).scalar()


def _run_concurrently(conn, sql: str) -> None:
    """CONCURRENTLY DDL 은 트랜잭션 밖에서 실행한다."""
    # 문자열 COMMIT 뒤 DDL 은 psycopg2 가 트랜잭션 상태를 추적하지 않아서만 통했다 — psycopg(3)는
    # 서버 상태를 보고 새 BEGIN 을 열어 CONCURRENTLY 가 실패한다. alembic autocommit_block 이 정본.
    # PG 레인 테스트는 이미 AUTOCOMMIT 인 연결로 _apply_upgrade 를 부른다(alembic 컨텍스트 없음).
    if conn.get_execution_options().get('isolation_level') == 'AUTOCOMMIT':
        conn.execute(text(sql))
        return
    with op.get_context().autocommit_block():
        op.get_bind().execute(text(sql))


def _ensure_valid_index(conn, name: str) -> None:
    """INVALID 로 남은 같은 이름 인덱스를 지우고 만든 뒤, valid 인지 확인한다."""
    if index_validity(conn, name) is False:
        print(f'[SEARCH-TRGM-00] {name} 이 INVALID 로 남아 있어 지우고 다시 만든다.')
        _run_concurrently(conn, drop_index_sql(name))
    _run_concurrently(conn, create_index_sql(name))
    if index_validity(conn, name) is not True:
        raise RuntimeError(f'[SEARCH-TRGM-00] {name} 을 만든 뒤에도 valid 가 아니다 — 배포를 멈춘다.')


def _apply_upgrade(conn) -> None:
    """확장 확인 후 인덱스 5개를 순서대로 만든다(``upgrade`` 와 PG 레인 테스트가 같이 쓴다)."""
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    for name in SEARCH_TRGM_INDEXES:
        _ensure_valid_index(conn, name)


def _apply_downgrade(conn) -> None:
    """이 마이그레이션이 만든 인덱스만 역순으로 지운다(데이터 무손실)."""
    for name in reversed(list(SEARCH_TRGM_INDEXES)):
        _run_concurrently(conn, drop_index_sql(name))


def upgrade() -> None:
    """검색 가지 trgm 인덱스 5개를 멱등 additive 로 만든다(PostgreSQL 전용)."""
    conn = op.get_bind()
    if conn.dialect.name != 'postgresql':
        return
    _apply_upgrade(conn)


def downgrade() -> None:
    """검색 가지 trgm 인덱스 5개를 지운다(PostgreSQL 전용)."""
    conn = op.get_bind()
    if conn.dialect.name != 'postgresql':
        return
    _apply_downgrade(conn)
