"""ACCESS-LOG-DETAIL-00: access_logs 구조화 payload 실 PostgreSQL 계약 (PGTEST-00 lane).

SQLite 도메인 레인(``tests/domains/test_file_access_log.py``)이 **구조적으로 증명할 수 없는
것**만 실 DB 로 고정한다.

1. **마이그레이션 왕복** — ``accesslog_detail_00`` 을 실제로 upgrade→downgrade→upgrade 돌려
   ``detail`` 컬럼과 표현식 인덱스 DDL 을 증명한다. 스키마는 ``create_all`` 로 부트스트랩
   되므로(conftest) 여기서 돌리지 않으면 마이그레이션이 사문 코드가 된다.
2. **백필 범위** — 파일 접근 3종만 채우고 구 형식 행은 ``detail`` NULL 로 남는다
   (구 형식 payload 의 PII 를 질의 가능한 JSONB 컬럼으로 옮기지 않는다).
3. **비-JSON 내성** — 자유 형식 원문이 섞여 있어도 마이그레이션이 파산하지 않는다.
   ``::jsonb`` 일괄 캐스트였다면 여기서 죽는다.
4. **인덱스가 실제로 쓰인다** — ORM 이 내는 바로 그 비교식이 표현식 인덱스를 탄다.
   인덱스 표현식과 ORM 표현식이 한 글자라도 어긋나면 인덱스가 있어도 Seq Scan 이다.

``FOMS_TEST_DATABASE_URL`` 미설정이면 lane 자체가 skip 된다(conftest).
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
from typing import Iterator

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

from models import AccessLog

# --------------------------------------------------------------------------- #
# load the migration module by path (migrations/versions is not a package)
# --------------------------------------------------------------------------- #
_MIGRATION_PATH = (
    pathlib.Path(__file__).resolve().parents[2]
    / "migrations" / "versions" / "accesslog_detail_00_access_log_detail_jsonb.py"
)
_spec = importlib.util.spec_from_file_location(
    "accesslog_detail_00_access_log_detail_jsonb", _MIGRATION_PATH)
mig = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mig)  # top-level import only — no DB side effects

TABLE = mig.TABLE
DETAIL_COLUMN = mig.DETAIL_COLUMN
ORDER_INDEX = mig.ORDER_INDEX


def _index_names(conn) -> set[str]:
    rows = conn.execute(
        text("SELECT indexname FROM pg_indexes WHERE tablename = :t"), {"t": TABLE}
    ).fetchall()
    return {r[0] for r in rows}


def _column_names(conn) -> set[str]:
    rows = conn.execute(text(
        "SELECT column_name FROM information_schema.columns WHERE table_name = :t"
    ), {"t": TABLE}).fetchall()
    return {r[0] for r in rows}


def _run_migration(conn, func) -> None:
    """``op`` 프록시를 이 커넥션에 묶고 마이그레이션 함수를 실행한다(운영 경로 그대로)."""
    context = MigrationContext.configure(conn)
    with Operations.context(context):
        func()


@pytest.fixture
def migration_conn(pg_engine) -> Iterator:
    """``detail`` 없는 baseline 에서 시작하는 DDL 전용 커넥션(항상 rollback — 스키마 무오염).

    conftest 가 ``create_all`` 로 만든 스키마에는 이미 ``detail`` 과 표현식 인덱스가 있다
    (models.py 정합). 마이그레이션을 진짜로 돌려보려면 그것을 먼저 걷어내야 하는데,
    PostgreSQL 은 DDL 도 트랜잭션이므로 **rollback 하나로 원상복구**된다 — 수동 복원 코드를
    두면 그 코드가 틀렸을 때 다른 모듈의 스키마를 조용히 망친다(테스트 순서 의존 사고).
    """
    connection = pg_engine.connect()
    trans = connection.begin()
    connection.execute(text("SET LOCAL lock_timeout = '10s'"))
    try:
        connection.execute(text(f"DROP INDEX IF EXISTS {ORDER_INDEX}"))
        connection.execute(
            text(f"ALTER TABLE {TABLE} DROP COLUMN IF EXISTS {DETAIL_COLUMN}"))
        connection.execute(text(f"DELETE FROM {TABLE}"))
        yield connection
    finally:
        if trans.is_active:
            trans.rollback()
        connection.close()


def _seed_raw(conn, action: str, additional_data: str | None) -> int:
    """``detail`` 없는 baseline 에 원문 행 1건을 넣고 id 를 돌려준다."""
    return conn.execute(text(
        f"INSERT INTO {TABLE} (action, additional_data, timestamp) "
        "VALUES (:a, :d, now()) RETURNING id"
    ), {"a": action, "d": additional_data}).scalar_one()


def _detail_of(conn, row_id: int):
    return conn.execute(text(
        f"SELECT {DETAIL_COLUMN} FROM {TABLE} WHERE id = :i"), {"i": row_id}).scalar_one()


def _raw_of(conn, row_id: int):
    return conn.execute(text(
        f"SELECT additional_data FROM {TABLE} WHERE id = :i"), {"i": row_id}).scalar_one()


# --------------------------------------------------------------------------- #
# 1. 마이그레이션 왕복
# --------------------------------------------------------------------------- #
def test_migration_adds_detail_column_and_order_index(migration_conn):
    """upgrade 가 detail 컬럼과 주문 축 표현식 인덱스를 만든다."""
    assert DETAIL_COLUMN not in _column_names(migration_conn)
    assert ORDER_INDEX not in _index_names(migration_conn)

    _run_migration(migration_conn, mig.upgrade)

    assert DETAIL_COLUMN in _column_names(migration_conn)
    assert ORDER_INDEX in _index_names(migration_conn)


def test_migration_round_trip_upgrade_downgrade_upgrade(migration_conn):
    """upgrade→downgrade→upgrade 왕복이 성립한다(downgrade 가 진짜 되돌린다)."""
    _run_migration(migration_conn, mig.upgrade)
    assert DETAIL_COLUMN in _column_names(migration_conn)

    _run_migration(migration_conn, mig.downgrade)
    assert DETAIL_COLUMN not in _column_names(migration_conn)
    assert ORDER_INDEX not in _index_names(migration_conn)

    _run_migration(migration_conn, mig.upgrade)
    assert DETAIL_COLUMN in _column_names(migration_conn)
    assert ORDER_INDEX in _index_names(migration_conn)


def test_downgrade_preserves_raw_payload(migration_conn):
    """downgrade 는 원문(additional_data)을 건드리지 않는다 — 데이터 손실 0 의 가역 변경."""
    raw = json.dumps({"storage_key": "orders/7/a.jpg", "order_id": 7}, ensure_ascii=False)
    row_id = _seed_raw(migration_conn, "FILE_VIEW", raw)

    _run_migration(migration_conn, mig.upgrade)
    assert _detail_of(migration_conn, row_id) == {"storage_key": "orders/7/a.jpg",
                                                  "order_id": 7}

    _run_migration(migration_conn, mig.downgrade)
    assert _raw_of(migration_conn, row_id) == raw


# --------------------------------------------------------------------------- #
# 2. 백필 범위 — 파일 접근 3종만 (구 형식 PII 를 옮기지 않는다)
# --------------------------------------------------------------------------- #
def test_backfill_fills_file_access_rows_only(migration_conn):
    """파일 접근 3종은 채우고, 구 형식 행은 detail NULL 로 남는다(PII 이관 금지)."""
    file_ids = [
        _seed_raw(migration_conn, action,
                  json.dumps({"storage_key": f"orders/3/{action}.jpg", "order_id": 3}))
        for action in mig.FILE_ACCESS_ACTIONS
    ]
    legacy_id = _seed_raw(
        migration_conn, "주문 정보 조회",
        json.dumps({"order_id": 24, "customer_name": "구형식고객",
                    "phone": "010-1234-5678"}, ensure_ascii=False),
    )

    _run_migration(migration_conn, mig.upgrade)

    for row_id in file_ids:
        assert _detail_of(migration_conn, row_id)["order_id"] == 3
    assert _detail_of(migration_conn, legacy_id) is None, "구 형식 PII 가 JSONB 로 새어나갔다"
    # 원문은 그대로 — 원장이 값을 잃지 않는다.
    assert "구형식고객" in _raw_of(migration_conn, legacy_id)


def test_backfill_survives_non_json_and_non_dict_payloads(migration_conn):
    """자유 형식 원문이 섞여 있어도 마이그레이션이 파산하지 않는다(::jsonb 일괄 캐스트 금지)."""
    broken = _seed_raw(migration_conn, "FILE_VIEW", "이건 JSON 이 아니다")
    listish = _seed_raw(migration_conn, "FILE_VIEW", "[1, 2, 3]")
    empty = _seed_raw(migration_conn, "FILE_VIEW", None)
    good = _seed_raw(migration_conn, "FILE_VIEW",
                     json.dumps({"storage_key": "orders/8/ok.jpg", "order_id": 8}))

    _run_migration(migration_conn, mig.upgrade)  # 여기서 죽으면 red

    assert _detail_of(migration_conn, broken) is None
    assert _detail_of(migration_conn, listish) is None
    assert _detail_of(migration_conn, empty) is None
    assert _detail_of(migration_conn, good)["order_id"] == 8
    assert _raw_of(migration_conn, broken) == "이건 JSON 이 아니다", "원문이 훼손됐다"


# --------------------------------------------------------------------------- #
# 3. 인덱스가 ORM 이 내는 바로 그 표현식에 쓰인다
# --------------------------------------------------------------------------- #
def test_order_filter_query_uses_expression_index(migration_conn):
    """화면 주문 필터(ORM 표현식)가 Seq Scan 이 아닌 표현식 인덱스로 풀린다.

    EXPLAIN 대상 SQL 을 손으로 쓰지 않고 **ORM 이 컴파일한 문장**을 그대로 쓴다 —
    인덱스 표현식과 ORM 표현식의 불일치가 이 테스트의 유일한 검출 목표이기 때문이다.
    """
    _run_migration(migration_conn, mig.upgrade)

    stmt = sa.select(AccessLog.id).where(
        AccessLog.detail["order_id"].as_integer() == 41
    )
    sql = str(stmt.compile(dialect=postgresql.dialect(),
                           compile_kwargs={"literal_binds": True}))
    assert "->> 'order_id'" in sql, sql  # ORM 이 정말 그 표현식을 내는지 먼저 고정

    migration_conn.execute(text("SET enable_seqscan = off"))
    try:
        plan = "\n".join(r[0] for r in migration_conn.execute(text(f"EXPLAIN {sql}")))
    finally:
        migration_conn.execute(text("SET enable_seqscan = on"))

    assert ORDER_INDEX in plan, plan
    assert "Seq Scan" not in plan, plan


def test_order_filter_cannot_prefix_collide(migration_conn):
    """정수 동등 비교라 주문 12 조회가 주문 123 을 끌고 오는 것이 구조적으로 불가능하다."""
    _run_migration(migration_conn, mig.upgrade)

    conn = migration_conn
    for order_id in (12, 123, 1234):
        conn.execute(text(
            f"INSERT INTO {TABLE} (action, additional_data, {DETAIL_COLUMN}, timestamp) "
            "VALUES ('FILE_VIEW', :d, CAST(:d AS JSONB), now())"
        ), {"d": json.dumps({"storage_key": f"orders/{order_id}/a.jpg",
                             "order_id": order_id})})

    hits = conn.execute(text(
        f"SELECT ({DETAIL_COLUMN} ->> 'order_id')::integer FROM {TABLE} "
        f"WHERE ({DETAIL_COLUMN} ->> 'order_id')::integer = 12"
    )).fetchall()
    assert [r[0] for r in hits] == [12]
