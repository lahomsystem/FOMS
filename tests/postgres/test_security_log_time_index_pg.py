"""SEC-LOG-TIME-00: security_logs 정렬 인덱스 실 PostgreSQL 계약 (PGTEST-00 lane).

감사 화면의 **기본 조회**(``ORDER BY timestamp DESC, id DESC`` + ``count(*)``)는 T8 까지
Seq Scan + Sort 였다 — ``ix_security_logs_target`` 은 선행 컬럼이 ``target_type`` 이고
trgm 은 ``message`` 전용이라 정렬에 쓸 수 없다. 이 스위트가 고정하는 것:

1. **create_all 레인 정합** — ``models.SecurityLog.__table_args__`` 의 새 인덱스가 baseline
   에 이미 존재한다(모델과 마이그레이션이 어긋나면 두 레인의 스키마가 갈린다).
2. **마이그레이션 왕복** — downgrade→upgrade 2 사이클이 인덱스만 정확히 걷어내고 되돌린다.
3. **범위 봉인** — 기존 인덱스(대상 조회·trgm)를 건드리지 않는다.
4. **인덱스가 실제로 쓰인다** — 화면이 내는 바로 그 정렬 질의가 Sort 없이 풀린다.
   여기가 이 작업의 유일한 목적이므로 EXPLAIN 으로 고정한다.

DDL 은 트랜잭션 안에서만 돌고 rollback 되므로 레인 스키마는 그대로다.
``FOMS_TEST_DATABASE_URL`` 미설정이면 lane 자체가 skip 된다(conftest).
"""

from __future__ import annotations

import importlib.util
import pathlib
from typing import Iterator

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Connection

from models import SecurityLog

_MIGRATION_PATH = (
    pathlib.Path(__file__).resolve().parents[2]
    / "migrations" / "versions" / "seclog_time_00_security_log_timestamp_index.py"
)
_spec = importlib.util.spec_from_file_location("seclog_time_00", _MIGRATION_PATH)
mig = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mig)  # top-level import only — no DB side effects

TABLE = mig.TABLE
TIME_INDEX = mig.TIME_INDEX
TARGET_INDEX = "ix_security_logs_target"
TRGM_INDEX = "ix_security_logs_message_trgm"


def _indexes(conn: Connection) -> set[str]:
    rows = conn.execute(
        text("SELECT indexname FROM pg_indexes WHERE tablename = :t"), {"t": TABLE}
    ).fetchall()
    return {r[0] for r in rows}


@pytest.fixture
def ddl_conn(pg_engine) -> Iterator[Connection]:
    """DDL 전용 커넥션 — 트랜잭션 안에서만 돌고 항상 rollback(스키마 무오염)."""
    connection = pg_engine.connect()
    trans = connection.begin()
    connection.execute(text("SET LOCAL lock_timeout = '10s'"))
    try:
        yield connection
    finally:
        if trans.is_active:
            trans.rollback()
        connection.close()


def _run(conn: Connection, direction: str) -> None:
    """마이그레이션 ``upgrade``/``downgrade`` 를 이 커넥션에 실행한다(alembic op 프록시)."""
    context = MigrationContext.configure(conn)
    with Operations.context(context):
        getattr(mig, direction)()


# --------------------------------------------------------------------------- #
# 1. 모델 ↔ 마이그레이션 정합 + 왕복
# --------------------------------------------------------------------------- #
def test_create_all_lane_has_time_index(ddl_conn):
    """모델(create_all) baseline 에 정렬 인덱스가 이미 있다(레인 간 스키마 정합)."""
    assert TIME_INDEX in _indexes(ddl_conn), _indexes(ddl_conn)


def test_index_columns_match_model_definition(ddl_conn):
    """인덱스 컬럼 구성이 ``(timestamp, id)`` 순서 그대로다 — 순서가 뒤집히면 정렬에 못 쓴다."""
    definition = ddl_conn.execute(text(
        "SELECT indexdef FROM pg_indexes WHERE tablename = :t AND indexname = :i"
    ), {"t": TABLE, "i": TIME_INDEX}).scalar_one()
    assert "(timestamp, id)" in definition.replace('"', ""), definition

    model_index = next(ix for ix in SecurityLog.__table__.indexes if ix.name == TIME_INDEX)
    assert [c.name for c in model_index.columns] == ["timestamp", "id"]


def test_migration_roundtrip_restores_index(ddl_conn):
    """downgrade 가 인덱스를 걷어내고 upgrade 가 원상복구한다(2 사이클 = 멱등)."""
    baseline = _indexes(ddl_conn)
    assert TIME_INDEX in baseline

    for cycle in range(2):
        _run(ddl_conn, "downgrade")
        assert baseline - _indexes(ddl_conn) == {TIME_INDEX}, cycle

        _run(ddl_conn, "upgrade")
        assert _indexes(ddl_conn) == baseline, cycle


def test_migration_touches_only_the_time_index(ddl_conn):
    """기존 인덱스(대상 조회·trgm)는 무접촉이다(범위 봉인)."""
    before = _indexes(ddl_conn)
    _run(ddl_conn, "downgrade")
    after = _indexes(ddl_conn)

    assert TARGET_INDEX in after, "대상 조회 인덱스를 같이 지웠다"
    if TRGM_INDEX in before:
        assert TRGM_INDEX in after, "trgm 인덱스를 같이 지웠다"


# --------------------------------------------------------------------------- #
# 2. 화면이 내는 그 질의가 인덱스를 탄다
# --------------------------------------------------------------------------- #
def test_screen_default_ordering_uses_index_without_sort(ddl_conn):
    """감사 화면 기본 조회가 Sort 없이 인덱스 순서로 풀린다(Seq Scan + Sort 제거).

    EXPLAIN 대상 SQL 을 손으로 쓰지 않고 화면과 **같은 ORM 표현식**을 컴파일해서 쓴다 —
    정렬 키가 바뀌면(예: id 탈락) 이 테스트가 red 로 알려주는 게 목적이다.
    """
    stmt = (
        sa.select(SecurityLog.id)
        .order_by(SecurityLog.timestamp.desc(), SecurityLog.id.desc())
        .limit(50)
    )
    sql = str(stmt.compile(dialect=postgresql.dialect(),
                           compile_kwargs={"literal_binds": True}))

    ddl_conn.execute(text("SET LOCAL enable_seqscan = off"))
    plan = "\n".join(r[0] for r in ddl_conn.execute(text(f"EXPLAIN {sql}")))

    assert TIME_INDEX in plan, plan
    assert "Sort" not in plan, plan


def test_downgrade_makes_the_same_query_sort_again(ddl_conn):
    """인덱스를 걷어내면 같은 질의가 Sort 로 되돌아간다 — 인덱스가 진짜 원인임을 대조로 고정."""
    stmt = (
        sa.select(SecurityLog.id)
        .order_by(SecurityLog.timestamp.desc(), SecurityLog.id.desc())
        .limit(50)
    )
    sql = str(stmt.compile(dialect=postgresql.dialect(),
                           compile_kwargs={"literal_binds": True}))

    _run(ddl_conn, "downgrade")
    plan = "\n".join(r[0] for r in ddl_conn.execute(text(f"EXPLAIN {sql}")))

    assert TIME_INDEX not in plan
    assert "Sort" in plan, plan
