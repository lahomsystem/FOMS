"""NAVER-INGEST-BACKFILL: 매칭 축 사본 컬럼 마이그레이션 왕복 계약 (PostgreSQL 레인).

SQLite 레인은 부분 인덱스(``WHERE order_id IS NULL``)를 조용히 무시하므로 여기서만 잰다.
고정하는 것:

* ``upgrade`` 가 사본 컬럼 3개와 **미연결 전용 부분 인덱스** 3개를 만든다.
* ``downgrade`` 가 정확히 그것만 걷어낸다(왕복 2회로 멱등 확인).
* 인덱스 술어가 실제로 ``order_id IS NULL`` 이다 — 술어가 빠지면 인덱스가 수집 이력
  전체 크기로 자란다.
"""

from __future__ import annotations

import importlib.util
import pathlib
from typing import Iterator

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.engine import Connection

_MIGRATION_PATH = (
    pathlib.Path(__file__).resolve().parents[2]
    / "migrations" / "versions" / "naverbf_00_link_match_keys.py"
)
_spec = importlib.util.spec_from_file_location("naverbf_00", _MIGRATION_PATH)
mig = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mig)  # top-level import only — no DB side effects

TABLE = "external_order_links"
COPY_COLUMNS = {"recipient_name", "recipient_phone_digits", "orderer_phone_digits"}
MATCH_INDEXES = {
    "ix_external_order_link_match_recipient_phone",
    "ix_external_order_link_match_orderer_phone",
    "ix_external_order_link_match_name",
}


def _columns(conn: Connection) -> set[str]:
    rows = conn.execute(
        text("SELECT column_name FROM information_schema.columns WHERE table_name = :t"),
        {"t": TABLE},
    ).fetchall()
    return {row[0] for row in rows}


def _indexes(conn: Connection) -> dict[str, str]:
    rows = conn.execute(
        text("SELECT indexname, indexdef FROM pg_indexes WHERE tablename = :t"),
        {"t": TABLE},
    ).fetchall()
    return {row[0]: row[1] for row in rows}


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
    """마이그레이션 ``upgrade``/``downgrade`` 를 이 커넥션에 실행한다."""
    context = MigrationContext.configure(conn)
    with Operations.context(context):
        getattr(mig, direction)()


def test_migration_roundtrip_restores_columns_and_indexes(ddl_conn):
    """downgrade 가 사본 컬럼·인덱스만 걷어내고 upgrade 가 원상복구한다(2 사이클)."""
    baseline_columns = _columns(ddl_conn)
    baseline_indexes = set(_indexes(ddl_conn))
    assert COPY_COLUMNS <= baseline_columns
    assert MATCH_INDEXES <= baseline_indexes

    for cycle in range(2):
        _run(ddl_conn, "downgrade")
        assert baseline_columns - _columns(ddl_conn) == COPY_COLUMNS, cycle
        assert baseline_indexes - set(_indexes(ddl_conn)) == MATCH_INDEXES, cycle

        _run(ddl_conn, "upgrade")
        assert _columns(ddl_conn) == baseline_columns, cycle
        assert set(_indexes(ddl_conn)) == baseline_indexes, cycle


def test_match_indexes_are_partial_on_unlinked_rows(ddl_conn):
    """인덱스는 **미연결 행만** 담는다 — 술어가 빠지면 이력 전체 크기로 자란다."""
    definitions = _indexes(ddl_conn)
    for name in MATCH_INDEXES:
        assert "WHERE (order_id IS NULL)" in definitions[name], name
