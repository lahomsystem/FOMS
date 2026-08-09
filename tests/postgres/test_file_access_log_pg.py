"""AUDIT-LOG T6: 파일 접근 기록 실 PostgreSQL 계약 (PGTEST-00 lane).

SQLite 도메인 레인(``tests/domains/test_file_access_log.py``)이 **구조적으로 증명할 수 없는
것**만 실 DB 로 고정한다.

1. **인덱스 마이그레이션 왕복** — ``access_log_00`` 을 실제로 upgrade→downgrade→upgrade
   돌려 ``ix_access_logs_user_id_timestamp``·``ix_access_logs_timestamp`` DDL 을 증명한다.
   스키마는 ``create_all`` 로 부트스트랩되므로(conftest) 이 인덱스는 마이그레이션에만 있고,
   여기서 돌리지 않으면 어디서도 실행되지 않는 사문 코드가 된다.
2. **인덱스가 실제로 쓰인다** — "이 사용자가 최근 무슨 파일을 봤나" 질의가 Seq Scan 이 아닌
   Index Scan 으로 풀린다(감사 원장이 커져도 조사 질의가 죽지 않는다).
3. **진짜 독립 커밋** — 본 세션 rollback 후에도 access_logs 행이 남는다(SQLite 는 메인
   engine 을 재사용해 증명 불가).
4. **naive UTC · JSONB 아닌 Text payload 왕복** — 기록 시각 규약과 additional_data 원문.

``FOMS_TEST_DATABASE_URL`` 미설정이면 lane 자체가 skip 된다(conftest).
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
from datetime import datetime, timedelta, timezone
from typing import Iterator

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.orm import Session

import db as db_module
from foms.services import audit_writer
from models import User

# --------------------------------------------------------------------------- #
# load the migration module by path (migrations/versions is not a package)
# --------------------------------------------------------------------------- #
_MIGRATION_PATH = (
    pathlib.Path(__file__).resolve().parents[2]
    / "migrations" / "versions" / "access_log_00_access_log_indexes.py"
)
_spec = importlib.util.spec_from_file_location("access_log_00_access_log_indexes",
                                               _MIGRATION_PATH)
mig = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mig)  # top-level import only — no DB side effects

TABLE = mig.TABLE
USER_TIME_INDEX = mig.USER_TIME_INDEX
TIME_INDEX = mig.TIME_INDEX


def _index_names(conn) -> set[str]:
    rows = conn.execute(
        text("SELECT indexname FROM pg_indexes WHERE tablename = :t"), {"t": TABLE}
    ).fetchall()
    return {r[0] for r in rows}


def _run_migration(conn, func) -> None:
    """``op`` 프록시를 이 커넥션에 묶고 마이그레이션 함수를 실행한다(운영 경로 그대로)."""
    context = MigrationContext.configure(conn)
    with Operations.context(context):
        func()


@pytest.fixture
def migration_conn(pg_engine) -> Iterator:
    """인덱스 없는 baseline(create_all) 에서 시작해 teardown 으로 baseline 을 복원한다."""
    conn = pg_engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    try:
        for name in (USER_TIME_INDEX, TIME_INDEX):
            conn.execute(text(f"DROP INDEX IF EXISTS {name}"))
        yield conn
    finally:
        for name in (USER_TIME_INDEX, TIME_INDEX):
            conn.execute(text(f"DROP INDEX IF EXISTS {name}"))
        conn.close()


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


def _make_lane_user(pg_engine, username: str) -> int:
    """레인 DB 에 실제 User 를 만들고 id 를 돌려준다.

    ``access_logs.user_id`` 는 ``users.id`` FK 다 — 가짜 id 로 쓰면 FK 위반이 fail-open 에
    먹혀 "행 0" 으로만 보인다(테스트가 조용히 무의미해진다).
    """
    session = Session(bind=pg_engine)
    try:
        user = User(username=username, password="x", role="STAFF",
                    name=username, is_active=True)
        session.add(user)
        session.commit()
        return user.id
    finally:
        session.close()


def _rows(pg_engine, action: str) -> list[tuple]:
    """레인 DB 에서 action 으로 access_logs 행을 새 커넥션으로 직접 읽는다."""
    with pg_engine.connect() as conn:
        return list(conn.execute(
            text("SELECT id, user_id, action, ip_address, user_agent, "
                 "additional_data, timestamp FROM access_logs "
                 "WHERE action = :a ORDER BY id"),
            {"a": action},
        ))


# --------------------------------------------------------------------------- #
# 1. 마이그레이션 왕복
# --------------------------------------------------------------------------- #
def test_migration_creates_both_indexes(migration_conn):
    """upgrade 가 감사 조회 인덱스 2개를 만든다."""
    assert not ({USER_TIME_INDEX, TIME_INDEX} & _index_names(migration_conn))

    _run_migration(migration_conn, mig.upgrade)

    assert {USER_TIME_INDEX, TIME_INDEX} <= _index_names(migration_conn)


def test_migration_round_trip_upgrade_downgrade_upgrade(migration_conn):
    """upgrade→downgrade→upgrade 왕복이 성립한다(downgrade 가 진짜 되돌린다)."""
    _run_migration(migration_conn, mig.upgrade)
    assert {USER_TIME_INDEX, TIME_INDEX} <= _index_names(migration_conn)

    _run_migration(migration_conn, mig.downgrade)
    assert not ({USER_TIME_INDEX, TIME_INDEX} & _index_names(migration_conn))

    _run_migration(migration_conn, mig.upgrade)
    assert {USER_TIME_INDEX, TIME_INDEX} <= _index_names(migration_conn)


def _security_log_indexes(conn) -> set[str]:
    """대조군: 같은 감사 계열의 다른 테이블 인덱스 목록(마이그레이션이 안 건드려야 한다)."""
    return {row[0] for row in conn.execute(text(
        "SELECT indexname FROM pg_indexes WHERE tablename = 'security_logs'"))}


def test_migration_touches_only_access_logs_indexes(migration_conn):
    """다른 테이블 인덱스는 건드리지 않는다(범위 봉인)."""
    before = _index_names(migration_conn)
    other_before = _security_log_indexes(migration_conn)

    _run_migration(migration_conn, mig.upgrade)

    after = _index_names(migration_conn)
    assert after - before == {USER_TIME_INDEX, TIME_INDEX}
    assert _security_log_indexes(migration_conn) == other_before


def test_user_timeline_query_uses_index(migration_conn):
    """사용자별 최근 접근 조회(user_id = ? ORDER BY timestamp DESC)가 Index Scan 으로 풀린다."""
    _run_migration(migration_conn, mig.upgrade)

    migration_conn.execute(text("SET enable_seqscan = off"))
    try:
        plan = "\n".join(
            row[0] for row in migration_conn.execute(text(
                "EXPLAIN SELECT id FROM access_logs WHERE user_id = 1 "
                "ORDER BY timestamp DESC LIMIT 50"
            ))
        )
    finally:
        migration_conn.execute(text("SET enable_seqscan = on"))

    assert USER_TIME_INDEX in plan, plan
    assert "Seq Scan" not in plan, plan


# --------------------------------------------------------------------------- #
# 2. 진짜 독립 커밋 (SQLite 로는 증명 불가)
# --------------------------------------------------------------------------- #
def test_access_log_write_survives_business_transaction_rollback(
        pg_engine, audit_engine_on_lane):
    """본 세션 rollback 후: 감사 행 잔존 + 업무 변경 소멸(= 서로 다른 트랜잭션)."""
    action = "FILE_VIEW_PG_ROLLBACK"
    session = Session(bind=pg_engine)
    try:
        session.add(User(
            username="access-pg-rollback", password="x", role="STAFF",
            name="롤백 대상", is_active=True,
        ))
        session.flush()  # 아직 커밋 안 됨 — GET 경로의 "본 트랜잭션" 재현

        assert audit_writer.write_access_log_detached(
            action, ip="10.1.2.3", user_agent="ua",
            additional_data={"storage_key": "orders/1/a.jpg"}) is True

        session.rollback()
    finally:
        session.close()

    assert len(_rows(pg_engine, action)) == 1, "독립 커밋이 본 세션 rollback 에 딸려 사라졌다"

    with pg_engine.connect() as conn:
        remaining = conn.execute(
            text("SELECT count(*) FROM users WHERE username = :u"),
            {"u": "access-pg-rollback"},
        ).scalar_one()
    assert remaining == 0, "업무 변경까지 커밋됐다면 같은 커넥션을 공유한 것이다"


def test_access_log_columns_round_trip_with_naive_utc(pg_engine, audit_engine_on_lane):
    """user_id FK · IP · UA · JSON payload · tz-naive UTC 시각이 그대로 왕복한다."""
    action = "FILE_DOWNLOAD_PG_ROUNDTRIP"
    session = Session(bind=pg_engine)
    try:
        actor = User(username="access-pg-actor", password="x", role="ADMIN",
                     name="감사 주체", is_active=True)
        session.add(actor)
        session.commit()
        actor_id = actor.id
    finally:
        session.close()

    before = datetime.now(timezone.utc).replace(tzinfo=None)
    assert audit_writer.record_file_access(
        action, storage_key="orders/77/attachments/도면.pdf", user_id=actor_id,
        ip="203.0.113.9", user_agent="Mozilla/5.0 (PG)", order_id=77) is True
    after = datetime.now(timezone.utc).replace(tzinfo=None)

    rows = _rows(pg_engine, action)
    assert len(rows) == 1
    _id, user_id, _action, ip, user_agent, additional_data, timestamp = rows[0]
    assert user_id == actor_id
    assert ip == "203.0.113.9"
    assert user_agent == "Mozilla/5.0 (PG)"
    assert json.loads(additional_data) == {
        "order_id": 77, "storage_key": "orders/77/attachments/도면.pdf"}
    assert timestamp.tzinfo is None, "naive UTC 규약 위반"
    assert before - timedelta(seconds=1) <= timestamp <= after + timedelta(seconds=1)


# --------------------------------------------------------------------------- #
# 3. dedupe 가 실 DB 에서도 행 수를 줄인다 (view 만)
# --------------------------------------------------------------------------- #
def test_view_dedupe_reduces_rows_against_real_db(pg_engine, audit_engine_on_lane):
    """같은 (주체, file key) 연타는 실 DB 에서도 1행, 10분 창 만료 후 억제 카운트 1행."""
    action = "FILE_VIEW_PG_DEDUPE"
    key = "orders/5/attachments/photo.jpg"
    actor_id = _make_lane_user(pg_engine, "access-pg-dedupe")
    clock = {"now": 500.0}

    def _hit():
        return audit_writer.record_file_access(
            action, storage_key=key, user_id=actor_id, ip="10.0.0.1",
            dedupe_window_seconds=audit_writer.ACCESS_VIEW_DEDUPE_WINDOW_SECONDS)

    original = audit_writer._monotonic
    audit_writer._monotonic = lambda: clock["now"]
    try:
        for _ in range(4):
            _hit()
        assert len(_rows(pg_engine, action)) == 1

        # 9분 59초: 아직 창 안이다.
        clock["now"] += 599
        _hit()
        assert len(_rows(pg_engine, action)) == 1

        # 10분 초과: 새 창 + 억제 카운트 보고.
        clock["now"] += 2
        assert _hit() is True
    finally:
        audit_writer._monotonic = original

    rows = _rows(pg_engine, action)
    assert len(rows) == 2
    assert json.loads(rows[1][5])["suppressed"] == 4


def test_download_is_not_deduped_against_real_db(pg_engine, audit_engine_on_lane):
    """다운로드는 창 인자가 없어 실 DB 에서도 매 건 기록된다."""
    action = "FILE_DOWNLOAD_PG_NODEDUPE"
    actor_id = _make_lane_user(pg_engine, "access-pg-nodedupe")
    for _ in range(3):
        assert audit_writer.record_file_access(
            action, storage_key="orders/5/attachments/photo.jpg",
            user_id=actor_id) is True
    assert len(_rows(pg_engine, action)) == 3
