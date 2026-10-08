"""DRAFTIDX-00 실 PostgreSQL 계약 (PGTEST-00 lane).

초안 술어(``Order.erp_draft_predicate``·``active_filter`` 등)는 "표식이 켜진 번호 목록에 있나"를
보고, 그 목록은 같은 조건의 부분 인덱스 ``ix_orders_meta_draft_true`` 만 읽는다(스펙
``docs/specs/2026-10-05-perf-db-draft-flag-and-stats_SPEC.md`` §3). 이 스위트가 고정하는 것:

1. **create_all 레인 정합** — ``models.Order`` 가 인덱스를 valid 로 만들고, 마이그레이션
   ``draftidx_00`` 이 만든 정의(``pg_get_indexdef``)와 같다.
2. **마이그레이션 왕복** — upgrade→downgrade→upgrade 2 사이클, 멱등, 다른 인덱스 무접촉.
3. **INVALID 잔해** — CONCURRENTLY 빌드 실패로 남은 INVALID 인덱스를 ``IF NOT EXISTS`` 는
   건너뛰지만(음성 대조군), upgrade 는 지우고 다시 만든다.
4. **뜻이 그대로** — 경우 행(숨은 실제 주문 모양 포함)과 채움 행에서 네 필터의 id 집합이 옛 식
   (``tests/support/meta_draft_contract.py`` 에 고정)과 같다. 음성 대조군: status 만 보는 술어는
   숨은 주문·지운 초안·글자 "true" 에서 갈린다.
5. **계획** — 앱과 같은 드라이버 경로(ClientCursor)로 그린 SQL 의 EXPLAIN 에 부분 인덱스와
   ``hashed SubPlan`` 이 있고, 바깥 ``orders`` 의 Filter 에 ``structured_data`` 가 없다. 음성
   대조군: 인덱스를 빼면 서브쿼리가 표를 훑고, 옛 술어는 바깥 Filter 에서 JSON 을 읽는다.

자기 전용 throwaway DB(orders 테이블만)를 쓴다. ``FOMS_TEST_DATABASE_URL`` 미설정이면 lane 자체가
skip 된다(conftest).
"""

from __future__ import annotations

import re
import uuid
from typing import Any, Callable, Iterator

import pytest
from sqlalchemy import create_engine, event, insert, select, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.engine.url import URL
from sqlalchemy.exc import DBAPIError
from sqlalchemy.pool import NullPool

from foms.services.db_url_resolver import PG_SQLALCHEMY_DRIVER, pg_error_code
from models import META_DRAFT_ALIAS, META_DRAFT_INDEX_NAME, Order, PartnerOrg
from tests.postgres.conftest import _raw_connect, assert_test_db_name
from tests.support.meta_draft_contract import (
    DRAFTIDX,
    FILTER_NAMES,
    FIRST_CASE_ID,
    HIDDEN_ORDER_KEYS,
    NEGATIVE_CONTROL_FILTERS,
    NEW_FILTERS,
    OLD_FILTERS,
    insert_cases,
)

mig = DRAFTIDX
FILLER_ROWS = 3000
# 채움 행 중 표식이 켜진 것(지운 초안·숨은 주문 모양)의 간격 — 스테이징 비율(39/3,524)과 비슷하게.
FLAG_EVERY = 97


# --------------------------------------------------------------------------- #
# 전용 DB · 데이터
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def draft_db_url(pg_admin_url: URL) -> Iterator[URL]:
    """이 스위트 전용 throwaway DB 를 만들고 끝나면 지운다."""
    db_name = assert_test_db_name(f"foms_test_draftidx_{uuid.uuid4().hex[:12]}")
    admin_dbname = pg_admin_url.database or "postgres"
    conn = _raw_connect(pg_admin_url, admin_dbname)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        conn.close()
    try:
        yield pg_admin_url.set(drivername=f"postgresql+{PG_SQLALCHEMY_DRIVER}", database=db_name)
    finally:
        assert_test_db_name(db_name)
        conn = _raw_connect(pg_admin_url, admin_dbname)
        conn.autocommit = True
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = %s AND pid <> pg_backend_pid()",
                    (db_name,),
                )
                cur.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
        finally:
            conn.close()


def _filler_rows() -> list[dict[str, Any]]:
    """결정적 합성 주문. 대부분 승격된 ERP(표식 false), 6건마다 레거시, ``FLAG_EVERY`` 마다 표식 참."""
    rows = []
    for i in range(1, FILLER_ROWS + 1):
        flagged = i % FLAG_EVERY == 0
        deleted = flagged and i % 2 == 0  # 표식 행의 절반은 지운 초안, 나머지는 숨은 주문 모양
        rows.append({
            "id": i,
            "received_date": "2026-09-01",
            "customer_name": f"cust{i:04d}",
            "phone": f"010-{1000 + i % 9000:04d}-{2000 + i % 3000:04d}",
            "address": f"road {i}",
            "product": f"prod{i:04d}",
            "status": "DELETED" if deleted else ("MEASURE" if i % 3 == 0 else "RECEIVED"),
            "deleted_at": "2026-09-02 10:00:00" if deleted else None,
            "is_erp_order": i % 6 != 0,
            "structured_data": {
                "meta": {"draft": flagged, "created_via": "ADD_ORDER"},
                "parties": {"customer": {"name": f"cust{i:04d}"}},
                # 행 하나를 스테이징 중앙값(약 2.2KB)만큼 키워 TOAST 경계 근처로 둔다.
                "notes": "x" * 2200,
            },
        })
    return rows


@pytest.fixture(scope="module")
def draft_engine(draft_db_url: URL) -> Iterator[tuple[Engine, dict[int, str]]]:
    """orders 만 create_all(models 레인 — 부분 인덱스 포함) + 채움 행 + 경우 행 + VACUUM ANALYZE."""
    import app  # noqa: F401  (모델 모듈 등록)
    from db import Base

    engine = create_engine(draft_db_url, connect_args={"client_encoding": "utf8"}, poolclass=NullPool)
    # orders.partner_org_id FK 대상(PARTNER-01)도 함께 만든다.
    Base.metadata.create_all(bind=engine, tables=[PartnerOrg.__table__, Order.__table__])
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as ac:
        ac.execute(insert(Order.__table__), _filler_rows())
        case_ids = insert_cases(ac, first_id=FIRST_CASE_ID)
        ac.execute(text("VACUUM ANALYZE orders"))
    try:
        yield engine, case_ids
    finally:
        engine.dispose()


@pytest.fixture
def ac(draft_engine: tuple[Engine, dict[int, str]]) -> Iterator[Connection]:
    """AUTOCOMMIT 연결(CONCURRENTLY DDL 용). 끝나면 인덱스를 정상 상태로 되돌린다."""
    engine, _ = draft_engine
    conn = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    try:
        yield conn
    finally:
        mig._apply_upgrade(conn)
        conn.close()


def _definitions(conn: Connection) -> dict[str, str]:
    rows = conn.execute(text(
        "SELECT c.relname, pg_get_indexdef(i.indexrelid) FROM pg_index i "
        "JOIN pg_class c ON c.oid = i.indexrelid WHERE i.indrelid = 'orders'::regclass"
    )).all()
    return {name: definition for name, definition in rows}


# --------------------------------------------------------------------------- #
# 1~3. 모델 정합 · 왕복 · INVALID 잔해
# --------------------------------------------------------------------------- #
def test_create_all_lane_builds_the_valid_partial_index(ac: Connection) -> None:
    """models(create_all)가 부분 인덱스를 valid 로 만들고, 표식이 켜진 행만 담는다."""
    assert mig.index_validity(ac) is True
    definition = _definitions(ac)[META_DRAFT_INDEX_NAME]
    assert definition.startswith(f"CREATE INDEX {META_DRAFT_INDEX_NAME} ON public.orders USING btree (id) WHERE ")
    flagged = ac.execute(text(
        "SELECT count(*) FROM orders WHERE CAST((structured_data #>> '{meta,draft}') AS BOOLEAN) IS TRUE"
    )).scalar_one()
    stats = ac.execute(text(
        "SELECT reltuples FROM pg_class WHERE relname = :name"
    ), {"name": META_DRAFT_INDEX_NAME}).scalar_one()
    assert flagged > 0 and int(stats) == flagged


def test_migration_roundtrip_matches_models_definition(ac: Connection) -> None:
    """downgrade 는 이 인덱스만 걷어내고, upgrade 는 models 와 같은 정의로 되돌린다(2 사이클·멱등)."""
    baseline = _definitions(ac)
    assert META_DRAFT_INDEX_NAME in baseline
    for cycle in range(2):
        mig._apply_downgrade(ac)
        assert set(baseline) - set(_definitions(ac)) == {META_DRAFT_INDEX_NAME}, cycle
        assert mig.index_validity(ac) is None
        mig._apply_upgrade(ac)
        mig._apply_upgrade(ac)  # 멱등: 이미 있으면 그대로
        assert _definitions(ac) == baseline, cycle


def test_upgrade_rebuilds_an_invalid_leftover(ac: Connection) -> None:
    """빌드 실패로 남은 INVALID 인덱스: IF NOT EXISTS 는 건너뛰고, upgrade 는 다시 만든다."""
    expected = _definitions(ac)[META_DRAFT_INDEX_NAME]
    some_id = ac.execute(text("SELECT min(id) FROM orders")).scalar_one()
    ac.execute(text(mig.drop_index_sql()))
    # 0 으로 나누기로 CONCURRENTLY 빌드를 중간에 실패시킨다 → 같은 이름의 INVALID 인덱스가 남는다.
    with pytest.raises(DBAPIError) as failed_build:
        ac.execute(text(
            f"CREATE INDEX CONCURRENTLY {META_DRAFT_INDEX_NAME} ON orders ((1 / (id - {int(some_id)})))"
        ))
    assert pg_error_code(failed_build.value) == "22012"  # division_by_zero
    assert mig.index_validity(ac) is False

    ac.execute(text(mig.create_index_sql()))  # 음성 대조군: IF NOT EXISTS 만으로는
    assert mig.index_validity(ac) is False  # 깨진 인덱스가 그대로 남는다

    mig._apply_upgrade(ac)
    assert mig.index_validity(ac) is True
    assert _definitions(ac)[META_DRAFT_INDEX_NAME] == expected


# --------------------------------------------------------------------------- #
# 4. 뜻이 그대로 — 옛 식(고정) = 새 술어
# --------------------------------------------------------------------------- #
def _ids(engine: Engine, build: Callable[[], Any]) -> set[int]:
    with engine.connect() as conn:
        return set(conn.execute(select(Order.id).where(build())).scalars())


@pytest.mark.parametrize("name", FILTER_NAMES)
def test_new_filter_matches_frozen_old_predicate_on_every_row(draft_engine, name: str) -> None:
    """채움 3,000행 + 경우 18행 전부에서 옛/새 id 집합이 같다."""
    engine, _ = draft_engine
    old = _ids(engine, OLD_FILTERS[name])
    new = _ids(engine, NEW_FILTERS[name])
    assert old, "결과 0건 — 비교가 무의미하다"
    assert new == old, (sorted(new - old)[:10], sorted(old - new)[:10])


def test_hidden_real_order_shape_stays_hidden(draft_engine) -> None:
    """표식이 남은 실제 주문 모양은 계속 모든 운영 화면에서 빠진다(보이게 하기는 별도 결정)."""
    engine, case_ids = draft_engine
    hidden = {order_id for order_id, key in case_ids.items() if key in HIDDEN_ORDER_KEYS}
    assert len(hidden) == len(HIDDEN_ORDER_KEYS)
    assert not hidden & _ids(engine, NEW_FILTERS["active_filter"])
    assert not hidden & _ids(engine, NEW_FILTERS["active_including_trashed_filter"])
    assert hidden <= _ids(engine, NEW_FILTERS["erp_draft_filter"])


@pytest.mark.parametrize("name", ["active_filter", "active_including_trashed_filter"])
def test_negative_control_status_only_predicate_differs(draft_engine, name: str) -> None:
    """음성 대조군: status 만 보면 숨은 주문 모양(휴지통 포함 화면은 지운 초안까지)이 나타난다."""
    engine, case_ids = draft_engine
    old = _ids(engine, OLD_FILTERS[name])
    status_only = _ids(engine, NEGATIVE_CONTROL_FILTERS[name])
    extra = status_only - old
    extra_keys = {case_ids[i] for i in extra if i in case_ids}
    assert set(HIDDEN_ORDER_KEYS) <= extra_keys
    assert "flag_string_true" in extra_keys  # PostgreSQL 은 글자 "true" 도 참으로 읽는다
    assert any(i < FIRST_CASE_ID for i in extra), "채움 행의 표식 참 행도 갈려야 한다"
    if name == "active_including_trashed_filter":
        assert {"deleted_draft", "deleted_promoted_flag_on"} <= extra_keys
    assert not old - status_only


# --------------------------------------------------------------------------- #
# 5. 계획 — 부분 인덱스 + hashed SubPlan, 바깥 행은 JSON 을 안 푼다
# --------------------------------------------------------------------------- #
def _explain(conn: Connection, build: Callable[[], Any]) -> str:
    """앱과 같은 실행 경로(바인드 처리 → ClientCursor 렌더링) 그대로, 문장 앞에 EXPLAIN 만 붙인다."""

    def _prefix_explain(_conn, _cursor, statement, parameters, _context, _executemany):
        return "EXPLAIN " + statement, parameters

    event.listen(conn, "before_cursor_execute", _prefix_explain, retval=True)
    try:
        rows = conn.execute(select(Order.id).where(build())).all()
    finally:
        event.remove(conn, "before_cursor_execute", _prefix_explain)
    return "\n".join(row[0] for row in rows)


def _plan(engine: Engine, build: Callable[[], Any], *, without_index: bool = False) -> str:
    """화면 술어를 EXPLAIN 한다. ``without_index`` 면 트랜잭션 안에서만 인덱스를 뺀다."""
    with engine.connect() as conn:
        if without_index:
            conn.execute(text("SET LOCAL lock_timeout = '10s'"))
            conn.execute(text(f"DROP INDEX {META_DRAFT_INDEX_NAME}"))  # rollback 으로 되살아난다
        plan = _explain(conn, build)
        conn.rollback()
    return plan


def _outer_filter(plan: str) -> str:
    """바깥 ``orders``(별칭 아닌 것) 노드의 Filter 줄."""
    lines = plan.splitlines()
    for index, line in enumerate(lines):
        if re.search(r"Scan on orders(?! {})".format(META_DRAFT_ALIAS), line) and not line.rstrip().endswith(
            f"orders {META_DRAFT_ALIAS}"
        ):
            for follow in lines[index + 1:]:
                if "Filter:" in follow:
                    return follow
                if "->" in follow or "SubPlan" in follow:
                    break
    raise AssertionError(f"바깥 orders 의 Filter 를 못 찾았다:\n{plan}")


@pytest.mark.parametrize("name", FILTER_NAMES)
def test_app_path_plan_uses_partial_index_via_hashed_subplan(draft_engine, name: str) -> None:
    """부분 인덱스로 번호 목록을 한 번 만들고(hashed SubPlan), 바깥 Filter 는 JSON 을 안 읽는다."""
    engine, _ = draft_engine
    plan = _plan(engine, NEW_FILTERS[name])
    assert f"using {META_DRAFT_INDEX_NAME} on orders {META_DRAFT_ALIAS}" in plan, plan
    assert "hashed SubPlan" in plan, plan
    assert "structured_data" not in _outer_filter(plan), plan


def test_negative_control_without_index_subquery_scans_the_table(draft_engine) -> None:
    """음성 대조군: 인덱스를 빼면 같은 질의의 서브쿼리가 표 전체를 훑는다 — 인덱스가 원인임을 고정."""
    engine, _ = draft_engine
    plan = _plan(engine, NEW_FILTERS["active_filter"], without_index=True)
    assert META_DRAFT_INDEX_NAME not in plan
    assert f"Seq Scan on orders {META_DRAFT_ALIAS}" in plan, plan


def test_negative_control_old_predicate_reads_json_in_outer_filter(draft_engine) -> None:
    """음성 대조군: 옛 술어는 바깥 Filter 에서 행마다 ``structured_data`` 를 푼다 — 검사기가 잡는다."""
    engine, _ = draft_engine
    plan = _plan(engine, OLD_FILTERS["active_filter"])
    assert "structured_data" in _outer_filter(plan), plan
    assert "hashed SubPlan" not in plan
