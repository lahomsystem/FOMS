"""ATTACH-LIFE-01(T4) 첨부 수명주기 PostgreSQL 계약 (PGTEST-00 lane).

SQLite lane(``tests/domains/test_attachment_lifecycle.py``)이 증명할 수 없는 것만 실 DB 로
고정한다.

1. **마이그레이션 왕복.** ``attach_life_00`` 의 ``downgrade`` → ``upgrade`` 를 실 PG 카탈로그
   에 돌려 컬럼 2개·인덱스 2개가 정확히 사라지고 되돌아오는지 본다(2 사이클 = 멱등).
   DDL 은 트랜잭션 안에서만 돌고 rollback 되므로 lane 스키마는 그대로다.
2. **인덱스가 실제로 쓰인다.** canonical 파일 라우트의 tombstone lookup
   (``storage_key = $1 OR thumbnail_key = $1``)이 Seq Scan 으로 떨어지지 않는지 —
   매 파일 요청이 타는 hot path 라 인덱스 부재는 곧 TTFB 회귀다.
3. **raw SQL 카운트 2곳의 실 동작.** ``... WHERE order_id = ANY(:ids)`` 는 PostgreSQL
   전용 문법이라 SQLite lane 에서 실행 자체가 불가능하다. 삭제 첨부가 대시보드 카운트에서
   빠지는지를 실 쿼리로 확인한다(유령 카운트 0).
4. **전역 필터 vs Core 우회.** ORM SELECT 는 삭제 행을 못 보고, Session 밖 Core SQL 은
   그대로 본다(purge/worker 계약).

``FOMS_TEST_DATABASE_URL`` 미설정이면 lane 자체가 skip 된다(conftest). 커밋 파일에는
비밀번호·DSN 을 넣지 않는다(env 주입).
"""
from __future__ import annotations

import importlib.util
import pathlib
import time
from typing import Iterator

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.engine import Connection

from foms.services.attachment_visibility import include_deleted
from foms.services.construction_read_model import fetch_construction_attachment_counts
from foms.services.production_read_model import fetch_production_attachment_counts
from models import Order, OrderAttachment

_MIGRATION_PATH = (
    pathlib.Path(__file__).resolve().parents[2]
    / "migrations" / "versions" / "attach_life_00_order_attachment_tombstone.py"
)
_spec = importlib.util.spec_from_file_location("attach_life_00", _MIGRATION_PATH)
mig = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mig)  # top-level import only — no DB side effects

TABLE = "order_attachments"
TOMBSTONE_COLUMNS = {"deleted_at", "deleted_by_user_id"}
KEY_INDEXES = {"ix_order_attachments_storage_key", "ix_order_attachments_thumbnail_key"}

_SEQ = [0]


def _sfx() -> str:
    """테스트 간 충돌을 막는 짧은 고유 접미사."""
    _SEQ[0] += 1
    return f"{_SEQ[0]}_{int(time.time() * 1000) % 1000000}"


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
# 1. 마이그레이션 왕복 (downgrade → upgrade → 재왕복)
# --------------------------------------------------------------------------- #
def test_migration_roundtrip_restores_columns_and_indexes(ddl_conn):
    """downgrade 가 컬럼·인덱스를 정확히 걷어내고 upgrade 가 원상복구한다(2 사이클)."""
    baseline_columns, baseline_indexes = _columns(ddl_conn), _indexes(ddl_conn)
    assert TOMBSTONE_COLUMNS <= baseline_columns
    assert KEY_INDEXES <= baseline_indexes

    for cycle in range(2):
        _run(ddl_conn, "downgrade")
        after_down_columns, after_down_indexes = _columns(ddl_conn), _indexes(ddl_conn)
        assert baseline_columns - after_down_columns == TOMBSTONE_COLUMNS, cycle
        assert baseline_indexes - after_down_indexes == KEY_INDEXES, cycle

        _run(ddl_conn, "upgrade")
        assert _columns(ddl_conn) == baseline_columns, cycle
        assert _indexes(ddl_conn) == baseline_indexes, cycle


def test_downgrade_preserves_surviving_rows_and_other_indexes(ddl_conn):
    """downgrade 는 tombstone 컬럼만 건드린다 — 행도 다른 인덱스도 잃지 않는다."""
    ddl_conn.execute(text(
        "INSERT INTO orders (received_date, customer_name, phone, address, product, status, "
        "structured_schema_version) "
        "VALUES ('2026-08-06', 'ddl-order', '010-0000-0000', 'addr', 'p', 'RECEIVED', 1)"
    ))
    order_id = ddl_conn.execute(text("SELECT max(id) FROM orders")).scalar_one()
    ddl_conn.execute(text(
        "INSERT INTO order_attachments "
        "(order_id, filename, file_type, category, file_size, storage_key, created_at) "
        "VALUES (:o, 'p.jpg', 'image', 'measurement', 1, :k, now())"
    ), {"o": order_id, "k": f"orders/{order_id}/attachments/p.jpg"})

    other_indexes = _indexes(ddl_conn) - KEY_INDEXES
    _run(ddl_conn, "downgrade")

    assert ddl_conn.execute(text(
        "SELECT COUNT(*) FROM order_attachments WHERE order_id = :o"), {"o": order_id}
    ).scalar_one() == 1
    assert other_indexes <= _indexes(ddl_conn)


# --------------------------------------------------------------------------- #
# 2. tombstone lookup 이 인덱스를 탄다 (hot path 회귀 가드)
# --------------------------------------------------------------------------- #
def test_tombstone_lookup_uses_key_indexes(pg_session):
    """canonical 라우트의 OR lookup 이 Seq Scan 으로 떨어지지 않는다."""
    pg_session.execute(text("SET enable_seqscan = off"))
    plan = "\n".join(
        row[0]
        for row in pg_session.execute(text(
            "EXPLAIN SELECT id FROM order_attachments "
            "WHERE deleted_at IS NOT NULL "
            "AND (storage_key = 'k' OR thumbnail_key = 'k')"
        )).fetchall()
    )
    assert "Seq Scan" not in plan, plan
    assert "ix_order_attachments_storage_key" in plan, plan
    assert "ix_order_attachments_thumbnail_key" in plan, plan


# --------------------------------------------------------------------------- #
# 3. 전역 필터 vs Core 우회 (실 DB)
# --------------------------------------------------------------------------- #
def _make_order(session) -> Order:
    order = Order(
        received_date="2026-08-06", customer_name=f"첨부고객_{_sfx()}",
        phone="010-1234-5678", address="서울 테헤란로 123", product="붙박이장",
        status="RECEIVED", is_erp_order=True,
    )
    session.add(order)
    session.flush()
    return order


def _make_attachment(session, order_id: int) -> OrderAttachment:
    n = _sfx()
    att = OrderAttachment(
        order_id=order_id, filename=f"p-{n}.jpg", file_type="image",
        category="measurement", file_size=1,
        storage_key=f"orders/{order_id}/attachments/p-{n}.jpg",
    )
    session.add(att)
    session.flush()
    return att


def _tombstone(session, attachment_id: int) -> None:
    session.execute(
        text("UPDATE order_attachments SET deleted_at = now() WHERE id = :i"),
        {"i": attachment_id},
    )
    session.expire_all()


def test_global_filter_hides_tombstone_but_core_sql_still_sees_it(pg_session):
    """ORM SELECT 는 제외, Session 밖 Core SQL 은 전량(purge/worker 계약)."""
    order = _make_order(pg_session)
    att = _make_attachment(pg_session, order.id)
    _tombstone(pg_session, att.id)

    assert pg_session.query(OrderAttachment).filter_by(id=att.id).first() is None
    assert include_deleted(
        pg_session.query(OrderAttachment).filter_by(id=att.id)).first() is not None
    assert pg_session.execute(
        text("SELECT COUNT(*) FROM order_attachments WHERE id = :i"), {"i": att.id}
    ).scalar_one() == 1


# --------------------------------------------------------------------------- #
# 4. raw SQL 카운트 2곳 (PostgreSQL 전용 ANY(:ids) 문법 — 실행 자체가 PG 전용)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "fetch_counts",
    [fetch_construction_attachment_counts, fetch_production_attachment_counts],
)
def test_attachment_count_raw_sql_excludes_tombstones(pg_session, fetch_counts):
    """대시보드 첨부 카운트에서 삭제 첨부가 빠진다(유령 카운트 0)."""
    order = _make_order(pg_session)
    live = _make_attachment(pg_session, order.id)
    doomed = _make_attachment(pg_session, order.id)
    pg_session.flush()

    assert fetch_counts(pg_session, [order]) == {order.id: 2}

    _tombstone(pg_session, doomed.id)
    assert fetch_counts(pg_session, [order]) == {order.id: 1}

    _tombstone(pg_session, live.id)
    assert fetch_counts(pg_session, [order]) == {}  # 전부 삭제 → 행 자체가 안 나온다
