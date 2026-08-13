"""ORDER-REASON-00: 주문 변경 사유 실 PostgreSQL 계약 (PGTEST-00 lane).

SQLite 도메인 레인이 **구조적으로 증명할 수 없는 것**만 실 DB 로 고정한다.

1. **마이그레이션 왕복** — ``orderreason_00`` 을 upgrade→downgrade→upgrade 로 실제 실행한다.
   스키마는 ``create_all`` 로 부트스트랩되므로(conftest) 여기서 돌리지 않으면 마이그레이션이
   사문 코드가 되고 운영 배포에서 처음 실행된다.
2. **레인 간 스키마 정합** — alembic 이 만든 인덱스 이름·컬럼 순서가 ``models`` 와 같아야 한다.
3. **중복 사유 차단이 DB 에서도 강제된다** — API 409 는 레이스에서 두 요청이 동시에 통과할 수
   있다. 감사 원장이 덮어써지지 않는 최종 보루는 unique 인덱스다.

``FOMS_TEST_DATABASE_URL`` 미설정이면 lane 자체가 skip 된다(conftest).
"""

from __future__ import annotations

import importlib.util
import pathlib
from typing import Iterator

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from models import OrderChangeReason

_MIGRATION_PATH = (
    pathlib.Path(__file__).resolve().parents[2]
    / "migrations" / "versions" / "orderreason_00_order_change_reasons.py"
)
_spec = importlib.util.spec_from_file_location("orderreason_00_order_change_reasons", _MIGRATION_PATH)
mig = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mig)  # top-level import only — no DB side effects

TABLE = mig.TABLE
INDEXES = {mig.CHANGE_SET_INDEX, mig.CODE_INDEX, mig.ORDER_INDEX}


def _index_names(conn) -> set[str]:
    rows = conn.execute(
        text("SELECT indexname FROM pg_indexes WHERE tablename = :t"), {"t": TABLE}
    ).fetchall()
    return {row[0] for row in rows}


def _index_columns(conn, index_name: str) -> list[str]:
    """인덱스가 실제로 덮는 컬럼을 **순서대로** 돌려준다(순서가 다르면 다른 인덱스다)."""
    rows = conn.execute(text("""
        SELECT a.attname
        FROM pg_index i
        JOIN pg_class c ON c.oid = i.indexrelid
        JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
        WHERE c.relname = :n
        ORDER BY array_position(i.indkey, a.attnum)
    """), {"n": index_name}).fetchall()
    return [row[0] for row in rows]


def _table_exists(conn) -> bool:
    return bool(conn.execute(text(
        "SELECT to_regclass(:t)"), {"t": f"public.{TABLE}"}).scalar())


def _run_migration(conn, func) -> None:
    """``op`` 프록시를 이 커넥션에 묶고 마이그레이션 함수를 실행한다(운영 경로 그대로)."""
    context = MigrationContext.configure(conn)
    with Operations.context(context):
        func()


@pytest.fixture
def migration_conn(pg_engine) -> Iterator:
    """사유 테이블이 없는 baseline 에서 시작하는 DDL 전용 커넥션(항상 rollback — 스키마 무오염)."""
    connection = pg_engine.connect()
    trans = connection.begin()
    connection.execute(text("SET LOCAL lock_timeout = '10s'"))
    try:
        connection.execute(text(f"DROP TABLE IF EXISTS {TABLE}"))
        yield connection
    finally:
        if trans.is_active:
            trans.rollback()
        connection.close()


def test_migration_round_trip(migration_conn):
    """upgrade → downgrade → upgrade 가 같은 스키마로 돌아온다."""
    assert not _table_exists(migration_conn)

    _run_migration(migration_conn, mig.upgrade)
    assert _table_exists(migration_conn)
    assert INDEXES <= _index_names(migration_conn)

    _run_migration(migration_conn, mig.downgrade)
    assert not _table_exists(migration_conn)

    _run_migration(migration_conn, mig.upgrade)
    assert INDEXES <= _index_names(migration_conn)


def test_migration_schema_matches_models(migration_conn):
    """alembic 스키마와 ``models`` 정의가 컬럼·인덱스 구성까지 같다."""
    _run_migration(migration_conn, mig.upgrade)

    columns = {row[0] for row in migration_conn.execute(text(
        "SELECT column_name FROM information_schema.columns WHERE table_name = :t"
    ), {"t": TABLE}).fetchall()}
    assert columns == {column.name for column in OrderChangeReason.__table__.columns}

    for index in OrderChangeReason.__table__.indexes:
        assert _index_columns(migration_conn, index.name) == [c.name for c in index.columns]


def test_change_set_uniqueness_is_enforced_by_db(migration_conn):
    """같은 change set 에 사유 2개가 들어갈 수 없다 — 감사 원장은 덮어쓰지 않는다."""
    _run_migration(migration_conn, mig.upgrade)
    insert = text(f"""
        INSERT INTO {TABLE} (change_set_id, order_id, reason_code, created_at)
        VALUES (:cs, 1, :code, now())
    """)
    migration_conn.execute(insert, {"cs": "cs-dup", "code": "customer_request"})

    with pytest.raises(IntegrityError):
        migration_conn.execute(insert, {"cs": "cs-dup", "code": "input_correction"})


def test_code_aggregation_uses_index(migration_conn):
    """"입력 오류 정정 월 몇 건" 집계가 Seq Scan 으로 떨어지지 않는다.

    시드는 **현실 분포**여야 한다 — 전 행이 같은 코드면 Seq Scan 이 실제로 더 싸고,
    플래너가 옳은 그 선택을 red 로 읽게 된다(인덱스가 아니라 테스트가 틀린 상태).
    운영에서 물을 코드는 소수 코드다.
    """
    _run_migration(migration_conn, mig.upgrade)
    migration_conn.execute(text(f"""
        INSERT INTO {TABLE} (change_set_id, order_id, reason_code, created_at)
        SELECT gen_random_uuid()::text, g,
               -- ``%`` 는 드라이버 파라미터 문법과 충돌한다 — mod() 로 쓴다.
               CASE WHEN mod(g, 50) = 0 THEN 'input_correction' ELSE 'customer_request' END,
               now()
        FROM generate_series(1, 3000) g
    """))
    migration_conn.execute(text(f"ANALYZE {TABLE}"))

    plan = "\n".join(str(row[0]) for row in migration_conn.execute(text(
        f"EXPLAIN SELECT count(*) FROM {TABLE} WHERE reason_code = 'input_correction'"
    )).fetchall())
    assert "Seq Scan" not in plan, plan
