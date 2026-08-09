"""AUDIT-LOG T8: security_logs 구조화 실 PostgreSQL 계약 (PGTEST-00 lane).

SQLite 도메인 레인(``tests/domains/test_security_log_structured.py``)이 **구조적으로 증명할
수 없는 것**만 실 DB 로 고정한다.

1. **마이그레이션 왕복** — ``seclog_struct_00`` 의 ``downgrade`` → ``upgrade`` 를 실 PG
   카탈로그에 돌려 컬럼 4개·인덱스 1개가 정확히 사라지고 되돌아오는지 본다(2 사이클 = 멱등).
   DDL 은 트랜잭션 안에서만 돌고 rollback 되므로 레인 스키마는 그대로다.
2. **create_all 레인 정합** — ``models.SecurityLog.__table_args__`` 의 인덱스가 baseline
   (create_all) 에 **이미 존재**해야 한다. 마이그레이션과 모델이 어긋나면 alembic 레인과
   테스트 레인이 서로 다른 스키마가 된다(스펙 §4 T8 — 이름·구성 완전 동일 요구).
3. **JSONB 왕복 + 질의** — ``detail`` 이 실제로 JSONB 로 저장되어 ``->>`` 연산자로 질의된다
   (SQLite 는 JSON 을 TEXT 로 떨궈 이 계약을 증명할 수 없다).
4. **대상 인덱스가 실제로 쓰인다** — "이 대상에게 무슨 일이 있었나" 질의가 Seq Scan 이 아닌
   Index Scan 으로 풀린다.
5. **독립 writer 의 구조화 컬럼 왕복** — 전용 engine 경로로 쓴 행의 컬럼 값이 그대로 읽힌다.

``FOMS_TEST_DATABASE_URL`` 미설정이면 lane 자체가 skip 된다(conftest). 커밋 파일에는
비밀번호·DSN 을 넣지 않는다(env 주입).
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

import db as db_module
from foms.services import audit_writer

_MIGRATION_PATH = (
    pathlib.Path(__file__).resolve().parents[2]
    / "migrations" / "versions" / "seclog_struct_00_security_log_structured_columns.py"
)
_spec = importlib.util.spec_from_file_location("seclog_struct_00", _MIGRATION_PATH)
mig = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mig)  # top-level import only — no DB side effects

TABLE = mig.TABLE
TARGET_INDEX = mig.TARGET_INDEX
STRUCTURED_COLUMNS = {"action", "target_type", "target_id", "detail"}
# 기존 trgm 인덱스(phase_f) — 이 마이그레이션이 절대 건드리면 안 되는 대조군.
TRGM_INDEX = "ix_security_logs_message_trgm"


def _columns(conn: Connection) -> set[str]:
    rows = conn.execute(
        text("SELECT column_name FROM information_schema.columns WHERE table_name = :t"),
        {"t": TABLE},
    ).fetchall()
    return {r[0] for r in rows}


def _indexes(conn: Connection) -> set[str]:
    rows = conn.execute(
        text("SELECT indexname FROM pg_indexes WHERE tablename = :t"), {"t": TABLE}
    ).fetchall()
    return {r[0] for r in rows}


def _column_type(conn: Connection, column: str) -> str:
    return conn.execute(
        text("SELECT data_type FROM information_schema.columns "
             "WHERE table_name = :t AND column_name = :c"),
        {"t": TABLE, "c": column},
    ).scalar_one()


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


@pytest.fixture
def audit_engine_on_lane(pg_test_database, monkeypatch) -> Iterator[None]:
    """감사 헬퍼가 레인 DB 를 보도록 ``db.DB_URL`` 을 갈아끼운다(운영 코드 경로 그대로)."""
    audit_writer.reset_audit_engine()
    audit_writer.reset_dedupe_cache()
    # str(URL)은 비밀번호를 ***로 마스킹한다(SQLAlchemy hide_password 기본) —
    # CI 레인처럼 비번 있는 DSN에서 인증 실패하므로 원문 렌더가 필수다.
    monkeypatch.setattr(
        db_module, "DB_URL", pg_test_database.render_as_string(hide_password=False)
    )
    yield
    audit_writer.reset_audit_engine()
    audit_writer.reset_dedupe_cache()


# --------------------------------------------------------------------------- #
# 1. create_all 레인 정합 + 마이그레이션 왕복
# --------------------------------------------------------------------------- #
def test_create_all_lane_has_model_columns_and_index(ddl_conn):
    """모델(create_all) baseline 에 구조화 컬럼 4개 + 대상 인덱스가 이미 있다."""
    assert STRUCTURED_COLUMNS <= _columns(ddl_conn)
    assert TARGET_INDEX in _indexes(ddl_conn), _indexes(ddl_conn)


def test_migration_roundtrip_restores_columns_and_index(ddl_conn):
    """downgrade 가 컬럼·인덱스를 정확히 걷어내고 upgrade 가 원상복구한다(2 사이클)."""
    baseline_columns, baseline_indexes = _columns(ddl_conn), _indexes(ddl_conn)

    for cycle in range(2):
        _run(ddl_conn, "downgrade")
        assert baseline_columns - _columns(ddl_conn) == STRUCTURED_COLUMNS, cycle
        assert baseline_indexes - _indexes(ddl_conn) == {TARGET_INDEX}, cycle

        _run(ddl_conn, "upgrade")
        assert _columns(ddl_conn) == baseline_columns, cycle
        assert _indexes(ddl_conn) == baseline_indexes, cycle


def test_downgrade_preserves_message_rows_and_other_indexes(ddl_conn):
    """downgrade 는 구조화 컬럼만 건드린다 — 기존 감사 행(message)도 다른 인덱스도 보존."""
    ddl_conn.execute(text(
        "INSERT INTO security_logs (message, action, target_type, target_id, timestamp) "
        "VALUES ('보존 대상 감사행', 'USER_UPDATE', 'user', 42, now())"
    ))
    other_indexes = _indexes(ddl_conn) - {TARGET_INDEX}

    _run(ddl_conn, "downgrade")

    assert ddl_conn.execute(text(
        "SELECT count(*) FROM security_logs WHERE message = '보존 대상 감사행'"
    )).scalar_one() == 1
    assert other_indexes <= _indexes(ddl_conn)


def test_migration_does_not_touch_trgm_index(ddl_conn):
    """기존 trgm 인덱스(phase_f)는 upgrade/downgrade 어느 쪽에도 영향받지 않는다."""
    # trgm 인덱스는 마이그레이션 전용이라 create_all 레인에는 없다 — 여기서 만들어 대조한다.
    ddl_conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    ddl_conn.execute(text(
        f"CREATE INDEX {TRGM_INDEX} ON security_logs USING gin (message gin_trgm_ops)"))
    assert TRGM_INDEX in _indexes(ddl_conn)

    _run(ddl_conn, "downgrade")
    assert TRGM_INDEX in _indexes(ddl_conn), "downgrade 가 남의 인덱스를 지웠다"
    _run(ddl_conn, "upgrade")
    assert TRGM_INDEX in _indexes(ddl_conn)


# --------------------------------------------------------------------------- #
# 2. JSONB 타입 · 질의 (SQLite 로는 증명 불가)
# --------------------------------------------------------------------------- #
def test_detail_column_is_jsonb(ddl_conn):
    """``detail`` 은 PostgreSQL 에서 JSONB 로 떨어진다(연산자·GIN 인덱스 가능성 확보)."""
    assert _column_type(ddl_conn, "detail") == "jsonb"
    assert _column_type(ddl_conn, "target_id") == "integer"


def test_detail_is_queryable_with_json_operators(pg_engine, audit_engine_on_lane):
    """detail 이 JSONB 로 저장되어 ``->>`` 로 질의된다(자유 텍스트 파싱 불필요)."""
    assert audit_writer.write_security_log_detached(
        "PG구조화-JSONB",
        action="USER_UPDATE",
        target_type="user",
        target_id=4242,
        detail={"changes": {"role": {"from": "STAFF", "to": "ADMIN"}}},
    ) is True

    with pg_engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT action, target_type, target_id, "
            "       detail #>> '{changes,role,from}', detail #>> '{changes,role,to}' "
            "FROM security_logs WHERE target_type = 'user' AND target_id = 4242"
        )).fetchall()

    assert rows == [("USER_UPDATE", "user", 4242, "STAFF", "ADMIN")]


def test_structured_columns_default_to_null_for_legacy_writes(pg_engine, audit_engine_on_lane):
    """구조화 인자 없는 기존 호출은 실 DB 에서도 NULL 4개로 저장된다(하위호환)."""
    assert audit_writer.write_security_log_detached("PG레거시-무인자") is True

    with pg_engine.connect() as conn:
        row = conn.execute(text(
            "SELECT action, target_type, target_id, detail FROM security_logs "
            "WHERE message = 'PG레거시-무인자'"
        )).one()
    assert row == (None, None, None, None)


# --------------------------------------------------------------------------- #
# 3. 대상 인덱스가 실제로 쓰인다 (감사 원장이 커져도 조사 질의가 죽지 않는다)
# --------------------------------------------------------------------------- #
def test_target_lookup_uses_index(pg_session):
    """"이 대상에게 무슨 일이 있었나" 질의가 Seq Scan 으로 떨어지지 않는다."""
    pg_session.execute(text("SET enable_seqscan = off"))
    plan = "\n".join(
        row[0] for row in pg_session.execute(text(
            "EXPLAIN SELECT id FROM security_logs "
            "WHERE target_type = 'user' AND target_id = 1 "
            "ORDER BY timestamp DESC LIMIT 50"
        ))
    )
    pg_session.execute(text("SET enable_seqscan = on"))

    assert TARGET_INDEX in plan, plan
    assert "Seq Scan" not in plan, plan
