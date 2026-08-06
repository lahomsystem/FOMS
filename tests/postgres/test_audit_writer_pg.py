"""AUDIT-LOG T5: 독립 감사 engine 실 PostgreSQL 계약 (PGTEST-00 lane).

SQLite 도메인 레인(``tests/domains/test_admin_audit_trail.py``)이 **구조적으로 증명할 수
없는 것**만 실 DB 로 고정한다. SQLite 는 ``audit_writer`` 가 메인 engine 을 재사용하고
pysqlite 가 커넥션 단위 트랜잭션이라 "별도 커넥션·별도 트랜잭션"이 성립하지 않는다.

1. **전용 engine 이 실제로 분리된다** — 메인 engine 과 다른 객체이며 풀 파라미터가
   스펙 §3-3 대로 pool 2 · overflow 0 · timeout 0.5s 로 고정된다.
2. **진짜 독립 커밋** — 본 세션이 rollback 돼도 감사 행은 남고, 본 세션의 업무 변경은
   사라진다(같은 커넥션이었다면 둘 다 남거나 둘 다 사라진다).
3. **풀 고갈 fail-open** — 전용 풀(2)을 모두 점유한 상태에서 감사 쓰기는 0.5초 안에
   포기하고 False 를 반환한다(요청 tail 을 만들지 않는다).
4. **naive UTC 왕복** — 기록 시각이 tz-naive UTC 규약을 지킨다.

``FOMS_TEST_DATABASE_URL`` 미설정이면 lane 자체가 skip 된다(conftest). 커밋 파일에는
비밀번호·DSN 을 넣지 않는다(env 주입).
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

import db as db_module
from foms.services import audit_writer
from models import SecurityLog, User


@pytest.fixture
def audit_engine_on_lane(pg_test_database, monkeypatch) -> Iterator[None]:
    """감사 헬퍼가 레인 DB 를 보도록 ``db.DB_URL`` 을 갈아끼운다(운영 코드 경로 그대로).

    ``_build_audit_engine`` 은 호출 시점에 ``db.DB_URL`` 을 읽으므로, 여기서 레인 DSN 을
    주입하면 **프로덕션과 동일한 생성 경로**(psycopg2 creator + 소형 풀)로 전용 engine 이
    만들어진다. 테스트 종료 시 싱글톤을 폐기해 다른 레인으로 새지 않게 한다.
    """
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


def _rows(pg_engine, marker: str) -> list[tuple]:
    """레인 DB 에서 marker 를 포함한 security_logs 행을 새 커넥션으로 직접 읽는다."""
    with pg_engine.connect() as conn:
        return list(conn.execute(
            text("SELECT id, user_id, message, timestamp FROM security_logs "
                 "WHERE message LIKE :pat ORDER BY id"),
            {"pat": f"%{marker}%"},
        ))


# --------------------------------------------------------------------------
# 1. 전용 engine 분리 + 풀 파라미터
# --------------------------------------------------------------------------
def test_audit_engine_is_separate_with_pinned_small_pool(audit_engine_on_lane):
    """감사 engine 은 메인 engine 과 다른 객체이고 풀은 2·0·0.5s 로 고정된다."""
    engine = audit_writer.get_audit_engine()

    assert engine is not db_module.engine, "감사 쓰기가 메인 풀을 잠식하면 안 된다(스펙 §3-3)"
    pool = engine.pool
    # 풀 상한/타임아웃은 공개 접근자가 없어 내부 속성을 계약으로 고정한다.
    assert pool.size() == 2
    assert pool._max_overflow == 0
    assert pool._timeout == 0.5

    # 싱글톤: 재호출은 같은 engine 을 돌려준다(요청마다 engine 생성 금지).
    assert audit_writer.get_audit_engine() is engine


# --------------------------------------------------------------------------
# 2. 진짜 독립 커밋 (SQLite 로는 증명 불가)
# --------------------------------------------------------------------------
def test_detached_write_survives_business_transaction_rollback(
        pg_engine, audit_engine_on_lane):
    """본 세션 rollback 후: 감사 행 잔존 + 업무 변경 소멸(= 서로 다른 트랜잭션)."""
    marker = "PG독립커밋-A"
    session = Session(bind=pg_engine)
    try:
        session.add(User(
            username="audit-pg-rollback",
            password="x",
            role="STAFF",
            name="롤백 대상",
            is_active=True,
        ))
        session.flush()  # 아직 커밋 안 됨 — 403/abort 경로의 "본 트랜잭션" 재현

        assert audit_writer.write_security_log_detached(marker) is True

        session.rollback()
    finally:
        session.close()

    assert len(_rows(pg_engine, marker)) == 1, "독립 커밋이 본 세션 rollback 에 딸려 사라졌다"

    with pg_engine.connect() as conn:
        remaining = conn.execute(
            text("SELECT count(*) FROM users WHERE username = :u"),
            {"u": "audit-pg-rollback"},
        ).scalar_one()
    assert remaining == 0, "업무 변경까지 커밋됐다면 같은 커넥션을 공유한 것이다"


def test_detached_write_is_visible_before_business_commit(pg_engine, audit_engine_on_lane):
    """열려 있는 본 세션 트랜잭션과 무관하게 감사 행이 즉시 다른 커넥션에 보인다."""
    marker = "PG독립커밋-B"
    session = Session(bind=pg_engine)
    try:
        session.execute(text("SELECT 1"))  # 트랜잭션 개시(커넥션 점유)
        assert audit_writer.write_security_log_detached(marker) is True
        # 본 세션이 아직 열려 있는 상태에서 제3의 커넥션이 이미 행을 본다.
        assert len(_rows(pg_engine, marker)) == 1
    finally:
        session.rollback()
        session.close()


def test_detached_write_records_actor_and_naive_utc_timestamp(pg_engine, audit_engine_on_lane):
    """user_id FK 왕복 + 기록 시각이 tz-naive UTC(프로젝트 규약)인지."""
    marker = "PG독립커밋-C"
    session = Session(bind=pg_engine)
    try:
        actor = User(
            username="audit-pg-actor", password="x", role="ADMIN",
            name="감사 주체", is_active=True,
        )
        session.add(actor)
        session.commit()
        actor_id = actor.id
    finally:
        session.close()

    before = datetime.now(timezone.utc).replace(tzinfo=None)
    assert audit_writer.write_security_log_detached(marker, user_id=actor_id) is True
    after = datetime.now(timezone.utc).replace(tzinfo=None)

    rows = _rows(pg_engine, marker)
    assert len(rows) == 1
    _id, user_id, message, timestamp = rows[0]
    assert user_id == actor_id
    assert message == marker
    assert timestamp.tzinfo is None, "naive UTC 규약 위반"
    assert before - timedelta(seconds=1) <= timestamp <= after + timedelta(seconds=1)


# --------------------------------------------------------------------------
# 3. 풀 고갈 fail-open (전용 풀이 실제로 작다는 증거)
# --------------------------------------------------------------------------
def test_pool_exhaustion_fails_open_fast(audit_engine_on_lane, caplog):
    """전용 풀(2)을 모두 점유하면 0.5초 안에 포기하고 False + 경고 로그를 남긴다."""
    engine = audit_writer.get_audit_engine()
    held = [engine.connect(), engine.connect()]  # pool 2 · overflow 0 → 이제 고갈
    try:
        with caplog.at_level(logging.WARNING, logger="foms.services.audit_writer"):
            started = time.monotonic()
            ok = audit_writer.write_security_log_detached("PG풀고갈-D")
            elapsed = time.monotonic() - started
    finally:
        for conn in held:
            conn.close()

    assert ok is False, "고갈 시 예외 전파/무한 대기 대신 조용한 실패여야 한다"
    assert elapsed < 5.0, f"pool_timeout 0.5s 가 먹지 않았다: {elapsed:.2f}s"
    assert any("독립 기록 실패" in r.getMessage() for r in caplog.records), [
        r.getMessage() for r in caplog.records]


def test_pool_recovers_after_connections_released(pg_engine, audit_engine_on_lane):
    """고갈이 풀린 뒤에는 정상 기록으로 복귀한다(영구 degrade 아님)."""
    engine = audit_writer.get_audit_engine()
    held = [engine.connect(), engine.connect()]
    assert audit_writer.write_security_log_detached("PG풀고갈-E") is False
    for conn in held:
        conn.close()

    marker = "PG복구-F"
    assert audit_writer.write_security_log_detached(marker) is True
    assert len(_rows(pg_engine, marker)) == 1
    assert _rows(pg_engine, "PG풀고갈-E") == []


# --------------------------------------------------------------------------
# 4. dedupe 가 실 DB 에서도 행 수를 줄인다
# --------------------------------------------------------------------------
def test_record_access_denied_dedupes_against_real_db(pg_engine, audit_engine_on_lane):
    """같은 키 연타는 실 DB 에서도 1행 + 창 만료 후 억제 카운트 1행."""
    marker = "PG거부-G"
    clock = {"now": 500.0}

    original = audit_writer._monotonic
    audit_writer._monotonic = lambda: clock["now"]
    try:
        for _ in range(4):
            audit_writer.record_access_denied(
                marker, user_id=None, ip="10.9.9.9",
                endpoint="pg.audit.endpoint", action="policy:PG")
        assert len(_rows(pg_engine, marker)) == 1

        clock["now"] += 61
        audit_writer.record_access_denied(
            marker, user_id=None, ip="10.9.9.9",
            endpoint="pg.audit.endpoint", action="policy:PG")
    finally:
        audit_writer._monotonic = original

    rows = _rows(pg_engine, marker)
    assert len(rows) == 2
    assert rows[1][2].endswith("(억제 3회)"), rows[1][2]
