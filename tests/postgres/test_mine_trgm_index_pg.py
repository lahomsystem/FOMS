"""MINE-TOPDRAW-00 실 PostgreSQL 계약 (PGTEST-00 lane).

mine 필터 최상위 ``drawing_assignees`` 가지가 새 trgm 인덱스를 탄다(설계서
``docs/specs/2026-10-22-mine-toplevel-drawing-assignees-index_SPEC.md``). 검색 인덱스 스위트의 전용 DB·
합성 데이터(``search_engine``: 운영 trgm 인덱스 전부 + 1,200행)를 같이 쓴다.

1. 마이그레이션 왕복 — upgrade→downgrade→upgrade 멱등, 다른 인덱스 무접촉.
2. 가지가 인덱스를 탄다(seqscan off, 가지 조건 없는 대용 btree 는 잴 때만 뺌). 음성 대조군: 새 인덱스를
   빼면 같은 질의가 그 인덱스를 못 쓴다.
3. 결과 동일 — 인덱스 경로와 순차 경로의 id 가 같다.
"""

from __future__ import annotations

from typing import Iterator

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.engine import Connection, Engine

from foms.services.erp_permissions import _json_string_token_condition
from models import Order
from tests.postgres.test_search_trgm_indexes_pg import STAND_IN_BTREES, search_db_url, search_engine  # noqa: F401
from tests.support.search_index_contract import load_migration

mig = load_migration("mine_toplevel_drawing_idx_00.py")
NAME = "ix_orders_sd_toplevel_drawing_assignees_trgm"
ASSIGNEE = "도면최상위"


@pytest.fixture
def ac(search_engine: Engine) -> Iterator[Connection]:  # noqa: F811
    """AUTOCOMMIT 연결. 끝나면 새 인덱스를 정상 상태로 되돌린다."""
    conn = search_engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    try:
        mig._apply_upgrade(conn)
        yield conn
    finally:
        mig._apply_upgrade(conn)
        conn.close()


@pytest.fixture
def seeded(ac: Connection) -> Iterator[set[int]]:
    """최상위 drawing_assignees 를 가진 주문 몇 건(끝나면 되돌린다)."""
    ids = [r[0] for r in ac.execute(text("SELECT id FROM orders ORDER BY id LIMIT 30 OFFSET 100")).all()]
    hit = set(ids[::3])
    for oid in ids:
        who = ASSIGNEE if oid in hit else "다른도면"
        ac.execute(
            text("UPDATE orders SET structured_data = jsonb_set(structured_data, '{drawing_assignees}', "
                 "CAST(:v AS jsonb)) WHERE id = :id"),
            {"v": f'["{who}"]', "id": oid},
        )
    ac.execute(text("ANALYZE orders"))
    try:
        yield hit
    finally:
        for oid in ids:
            ac.execute(text("UPDATE orders SET structured_data = structured_data - 'drawing_assignees' WHERE id = :id"),
                       {"id": oid})


def _branch():
    return _json_string_token_condition(Order.structured_data["drawing_assignees"], ASSIGNEE, dialect_name="postgresql")


def _plan(engine: Engine, *, without: tuple[str, ...] = ()) -> str:
    """앱과 같은 드라이버 경로로 그린 SQL 앞에 EXPLAIN 만 붙인다(seqscan off, 대용 btree 는 잴 때만 뺌)."""

    def _prefix(_c, _cur, statement, parameters, _ctx, _many):
        return "EXPLAIN " + statement, parameters

    with engine.connect() as conn:
        conn.execute(text("SET LOCAL lock_timeout = '10s'"))
        for name in (*STAND_IN_BTREES, *without):
            conn.execute(text(f"DROP INDEX IF EXISTS {name}"))
        conn.execute(text("SET LOCAL enable_seqscan = off"))
        event.listen(conn, "before_cursor_execute", _prefix, retval=True)
        try:
            plan = "\n".join(r[0] for r in conn.execute(select(Order.id).where(Order.is_erp_order.is_(True), _branch())).all())
        finally:
            event.remove(conn, "before_cursor_execute", _prefix)
        conn.rollback()
    return plan


def _definitions(conn: Connection) -> dict[str, str]:
    rows = conn.execute(text(
        "SELECT c.relname, pg_get_indexdef(i.indexrelid) FROM pg_index i "
        "JOIN pg_class c ON c.oid = i.indexrelid WHERE i.indrelid = 'orders'::regclass"
    )).all()
    return dict(rows)


def test_migration_roundtrip_only_touches_its_index(ac: Connection) -> None:
    baseline = _definitions(ac)
    assert NAME in baseline and mig.index_validity(ac, NAME) is True
    for cycle in range(2):
        mig._apply_downgrade(ac)
        assert set(baseline) - set(_definitions(ac)) == {NAME}, cycle
        mig._apply_upgrade(ac)
        mig._apply_upgrade(ac)
        assert _definitions(ac) == baseline, cycle


def test_toplevel_branch_uses_the_new_index(search_engine: Engine, seeded: set[int]) -> None:  # noqa: F811
    plan = _plan(search_engine)
    assert f"Bitmap Index Scan on {NAME}" in plan, plan
    assert "Seq Scan" not in plan, plan


def test_negative_control_without_the_index(search_engine: Engine, seeded: set[int]) -> None:  # noqa: F811
    plan = _plan(search_engine, without=(NAME,))
    assert NAME not in plan
    assert "Seq Scan" in plan, plan


def test_index_path_and_seq_path_return_same_ids(search_engine: Engine, seeded: set[int]) -> None:  # noqa: F811
    stmt = select(Order.id).where(_branch())
    with search_engine.connect() as conn:
        conn.execute(text("SET LOCAL enable_seqscan = off"))
        via_index = {r[0] for r in conn.execute(stmt).all()}
        conn.rollback()
    with search_engine.connect() as conn:
        conn.execute(text("SET LOCAL enable_indexscan = off"))
        conn.execute(text("SET LOCAL enable_bitmapscan = off"))
        via_seq = {r[0] for r in conn.execute(stmt).all()}
        conn.rollback()
    assert via_index == via_seq == seeded
