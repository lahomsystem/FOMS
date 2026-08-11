"""ORDER-DIFF-01: 주문 변경 원장 실 PostgreSQL 계약 (PGTEST-00 lane).

SQLite 도메인 레인(``tests/domains/test_order_field_changes_ledger.py``)이 **구조적으로 증명할
수 없는 것**만 실 DB 로 고정한다.

1. **마이그레이션 왕복** — ``orderdiff_01`` 을 upgrade→downgrade→upgrade 로 실제 실행한다.
   스키마는 ``create_all`` 로 부트스트랩되므로(conftest) 여기서 돌리지 않으면 마이그레이션이
   사문 코드가 되고, 운영 배포에서 처음 실행된다.
2. **레인 간 스키마 정합** — alembic 이 만든 인덱스 이름·컬럼 순서가 ``models`` 정의와 같아야
   한다. 어긋나면 create_all 레인에서 통과한 질의가 운영에서 인덱스를 못 탄다.
3. **인덱스가 실제로 쓰인다** — 감사의 1순위 질문(``path_template`` 동등 비교)이
   Seq Scan 으로 떨어지지 않는지 실행계획으로 확인한다.

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

from models import OrderFieldChange

_MIGRATION_PATH = (
    pathlib.Path(__file__).resolve().parents[2]
    / "migrations" / "versions" / "orderdiff_01_order_field_changes.py"
)
_spec = importlib.util.spec_from_file_location("orderdiff_01_order_field_changes", _MIGRATION_PATH)
mig = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mig)  # top-level import only — no DB side effects

TABLE = mig.TABLE
INDEXES = {mig.TEMPLATE_INDEX, mig.ORDER_INDEX, mig.CHANGE_SET_INDEX}


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
    """원장 테이블이 없는 baseline 에서 시작하는 DDL 전용 커넥션(항상 rollback — 스키마 무오염).

    PostgreSQL 은 DDL 도 트랜잭션이라 rollback 하나로 원상복구된다. 수동 복원 코드를 두면
    그 코드가 틀렸을 때 다른 모듈의 스키마를 조용히 망친다(테스트 순서 의존 사고).
    """
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
    """alembic 스키마와 ``models`` 정의가 컬럼·인덱스 구성까지 같다.

    두 레인(create_all·alembic)이 갈라지면 테스트에서 통과한 질의가 운영에서 다르게 돈다.
    """
    _run_migration(migration_conn, mig.upgrade)

    columns = {row[0] for row in migration_conn.execute(text(
        "SELECT column_name FROM information_schema.columns WHERE table_name = :t"
    ), {"t": TABLE}).fetchall()}
    assert columns == {column.name for column in OrderFieldChange.__table__.columns}

    for index in OrderFieldChange.__table__.indexes:
        assert _index_columns(migration_conn, index.name) == [c.name for c in index.columns]


def test_template_filter_uses_index(migration_conn):
    """감사 1순위 질의(``path_template`` 동등 비교)가 인덱스를 탄다.

    Seq Scan 으로 떨어지면 원장이 커질수록 감사 화면이 느려진다 — 인덱스가 "있다"가 아니라
    "쓰인다"를 확인해야 한다.
    """
    _run_migration(migration_conn, mig.upgrade)
    migration_conn.execute(text(f"""
        INSERT INTO {TABLE}
            (change_set_id, order_id, path, path_template, op, created_at)
        SELECT gen_random_uuid()::text, g, 'items.' || g || '.price', 'items.*.price', 'set', now()
        FROM generate_series(1, 3000) g
    """))
    migration_conn.execute(text(f"ANALYZE {TABLE}"))

    plan = "\n".join(row[0] for row in migration_conn.execute(text(
        f"EXPLAIN SELECT change_set_id FROM {TABLE} "
        "WHERE path_template = 'items.*.price' ORDER BY created_at DESC LIMIT 50"
    )).fetchall())

    assert "Seq Scan" not in plan, plan
