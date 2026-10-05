"""DRAFTIDX-00: 초안 표식이 켜진 주문 번호만 담는 부분 인덱스 (CONCURRENTLY)

Revision ID: draftidx_00
Revises: search_trgm_00
Create Date: 2026-10-05

왜: 모든 운영 화면에 붙는 ``Order.active_filter()`` 의 초안 술어는 ERP 이고 status 가 DRAFT 가
아닌 행마다 ``structured_data`` 를 풀어(TOAST) ``meta.draft`` 를 읽었다. 스테이징 실측
``/erp/dashboard`` 조각 하나(쿼리 3개) 56.4ms·3,334 buf, 완료 API 14.6ms 였고, 표식을 안 읽으면
9.5ms·0.6ms 다(스펙 §1.2). 식 인덱스만으로는 안 된다 — 걸러 내는 조건(NOT … OR 식)이라
플래너가 행마다 식을 다시 계산한다(스펙 §2 ③-가).

그래서 술어의 초안 가지를 "표식이 켜진 번호 목록에 있나"로 바꾸고(``models.Order.
_meta_draft_order_ids``), 그 목록 서브쿼리의 조건과 **같은 조건**의 부분 인덱스를 만든다.
플래너는 이 작은 인덱스(스테이징 39행)만 읽어 해시 목록을 한 번 만들고(hashed SubPlan), 바깥
행은 번호만 대조한다. 결과는 예전 술어와 한 행도 다르지 않다 — 같은 식을 같은 행에서 계산하고,
``id`` 는 기본 키라 NULL 이 없다(스펙 §3.3: 스테이징 3,524행·앱 쿼리 53개 차이 0건).

조건 글자는 앱이 그리는 서브쿼리 조건에서 별칭 접두(``orders_meta_draft.``)만 뺀 것이고,
``models.META_DRAFT_INDEX_WHERE`` 와 글자 단위로 같아야 한다 — ``tests/performance/
test_meta_draft_index_contract.py`` 와 PG 레인 ``tests/postgres/test_meta_draft_predicate_pg.py``
가 강제한다. 마이그레이션 상수 동결 원칙에 따라 ``models`` 를 import 하지 않는다(리터럴만 쓴다).

INVALID 처리: ``CREATE INDEX CONCURRENTLY`` 가 중간에 실패하면 INVALID 인덱스가 남고,
``IF NOT EXISTS`` 는 그것도 "있다"고 보고 건너뛴다. 그래서 만들기 전에 ``pg_index.indisvalid =
false`` 면 ``DROP INDEX CONCURRENTLY`` 후 다시 만든다. 만든 뒤에도 valid 가 아니면 예외를 낸다 —
predeploy(``set -e``)가 실패해 새 배포가 라이브되지 않고 옛 버전이 계속 돈다. 인덱스가 없거나
INVALID 인 채로 새 술어가 돌면 서브쿼리가 표 전체를 한 번 풀어 작은 쿼리가 느려진다(스펙 §2
약점 1) — 그래서 valid 확인이 배포 관문이다.

잠금·소요: CONCURRENTLY 는 읽기·쓰기를 막지 않는다. 대신 시작 시점에 열려 있던 트랜잭션이 끝날
때까지 기다린다(lock_timeout 없음 — 배포 직전 ``pg_stat_activity`` 에 오래 열린 트랜잭션이 없는지
본다). 다중 replica 의 동시 실행은 ``migrations/env.py`` 의 세션 advisory lock 이 직렬화한다.
로컬 4,600행 기준 37~70ms, 크기 16kB 안팎.

되돌리기: ``downgrade()`` 는 ``DROP INDEX CONCURRENTLY IF EXISTS``. 결과는 인덱스와 무관하므로
언제 지워도 안전하다. 다만 새 술어 코드가 돌고 있으면 위처럼 느려지므로 코드를 먼저 되돌린다.

스펙: docs/specs/2026-10-05-perf-db-draft-flag-and-stats_SPEC.md (P2-1, 결정 1-가)
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


revision: str = 'draftidx_00'
down_revision: Union[str, None] = 'search_trgm_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = 'orders'
INDEX_NAME = 'ix_orders_meta_draft_true'
# 앱이 그리는 번호 목록 서브쿼리 조건에서 ``orders_meta_draft.`` 만 뺀 것(글자 단위로 같아야 한다).
INDEX_WHERE = "CAST((structured_data #>> '{meta, draft}') AS BOOLEAN) IS true"

_INDEX_VALIDITY_SQL = text("SELECT indisvalid FROM pg_index WHERE indexrelid = to_regclass(:name)")


def create_index_sql() -> str:
    """부분 인덱스를 만드는 DDL(멱등). 테스트가 models 정의와 글자 단위로 대조한다."""
    return f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {INDEX_NAME} ON {TABLE} (id) WHERE {INDEX_WHERE}"


def drop_index_sql() -> str:
    """부분 인덱스를 지우는 DDL(멱등)."""
    return f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX_NAME}"


def index_validity(conn) -> bool | None:
    """``None`` = 인덱스 없음, ``True`` = 정상, ``False`` = 빌드 실패로 남은 INVALID."""
    return conn.execute(_INDEX_VALIDITY_SQL, {'name': INDEX_NAME}).scalar()


def _run_concurrently(conn, sql: str) -> None:
    """CONCURRENTLY DDL 은 트랜잭션 밖에서 실행한다(alembic ``autocommit_block`` 이 정본)."""
    # PG 레인 테스트는 이미 AUTOCOMMIT 인 연결로 _apply_upgrade 를 부른다(alembic 컨텍스트 없음).
    if conn.get_execution_options().get('isolation_level') == 'AUTOCOMMIT':
        conn.execute(text(sql))
        return
    with op.get_context().autocommit_block():
        op.get_bind().execute(text(sql))


def _apply_upgrade(conn) -> None:
    """INVALID 잔해를 지우고 인덱스를 만든 뒤 valid 인지 확인한다(``upgrade`` 와 PG 레인 테스트 공용)."""
    if index_validity(conn) is False:
        print(f'[DRAFTIDX-00] {INDEX_NAME} 이 INVALID 로 남아 있어 지우고 다시 만든다.')
        _run_concurrently(conn, drop_index_sql())
    _run_concurrently(conn, create_index_sql())
    if index_validity(conn) is not True:
        raise RuntimeError(f'[DRAFTIDX-00] {INDEX_NAME} 을 만든 뒤에도 valid 가 아니다 — 배포를 멈춘다.')


def _apply_downgrade(conn) -> None:
    """이 마이그레이션이 만든 인덱스만 지운다(데이터 무손실)."""
    _run_concurrently(conn, drop_index_sql())


def upgrade() -> None:
    """초안 표식 부분 인덱스를 멱등 additive 로 만든다(PostgreSQL 전용)."""
    conn = op.get_bind()
    if conn.dialect.name != 'postgresql':
        return
    _apply_upgrade(conn)


def downgrade() -> None:
    """초안 표식 부분 인덱스를 지운다(PostgreSQL 전용)."""
    conn = op.get_bind()
    if conn.dialect.name != 'postgresql':
        return
    _apply_downgrade(conn)
