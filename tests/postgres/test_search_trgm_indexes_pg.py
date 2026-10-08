"""SEARCH-TRGM-00 실 PostgreSQL 계약 (PGTEST-00 lane).

검색 술어(``erp_dashboard_search``)의 OR 가지가 모두 인덱스를 가져야 BitmapOr 가 된다. 가지
하나라도 없으면 후보 행 전부를 읽으며 가지마다 ``structured_data`` 를 다시 푼다(스펙
``docs/specs/2026-10-01-search-index-perf_SPEC.md``). 이 스위트가 고정하는 것:

1. **create_all 레인 정합** — ``models.Order`` 가 새 인덱스 5개를 만들고(pg_trgm 확장 포함),
   마이그레이션 ``search_trgm_00`` 이 만든 정의(``pg_get_indexdef``)와 같다.
2. **마이그레이션 왕복** — upgrade→downgrade→upgrade 2 사이클, 멱등, 다른 인덱스 무접촉.
3. **INVALID 잔해** — CONCURRENTLY 빌드 실패로 남은 INVALID 인덱스를 ``IF NOT EXISTS`` 는
   건너뛰지만(음성 대조군), upgrade 는 지우고 다시 만든다.
4. **가지 수 = 인덱스를 탄 수** — 화면이 쓰는 술어를 앱과 같은 드라이버 경로(ClientCursor)로
   그려 EXPLAIN(seqscan off) 하면 Seq Scan 없이 BitmapOr 이고, trgm Bitmap Index Scan 이
   패턴 가지마다 하나씩이다. 가지 조건 없이 행 묶음 전체를 읽는 대용 인덱스(``STAND_IN_BTREES``)
   는 잴 때만 뺀다. 음성 대조군: 새 인덱스 하나를 빼면 같은 질의가 Seq Scan 으로 떨어진다.
5. **결과 동일** — 인덱스 경로와 순차 경로의 결과 id 가 같다.

자기 전용 throwaway DB(orders 테이블만)를 쓴다 — 운영에만 있는 기존 trgm 인덱스
(phase_d·e·f, create_all 에 없다)를 깔고 데이터를 넣으므로 공유 레인 DB 를 오염시키지 않는다.
``FOMS_TEST_DATABASE_URL`` 미설정이면 lane 자체가 skip 된다(conftest).
"""

from __future__ import annotations

import re
import uuid
from collections import Counter
from typing import Any, Callable, Iterator

import pytest
from sqlalchemy import create_engine, event, insert, select, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.engine.url import URL
from sqlalchemy.exc import DBAPIError
from sqlalchemy.pool import NullPool

from foms.services.db_url_resolver import PG_SQLALCHEMY_DRIVER, pg_error_code
from foms.services.erp_dashboard_search import (
    erp_order_dashboard_search_predicate,
    visible_order_search_clause,
)
from models import Order, PartnerOrg, User
from tests.postgres.conftest import _raw_connect, assert_test_db_name
from tests.support.search_index_contract import (
    SEARCH_TRGM,
    branch_index_names,
    orders_trgm_index_registry,
)

mig = SEARCH_TRGM
NEW_INDEXES = list(mig.SEARCH_TRGM_INDEXES)
REGISTRY = orders_trgm_index_registry()
TRGM_NAMES = set(REGISTRY.values())
SEED_ROWS = 1200

# 화면이 쓰는 술어 그대로 — (모집단 조건 포함 술어, 이 질의를 쓰는 화면).
SCREEN_QUERIES: dict[str, Callable[[], Any]] = {
    # 과거 이력: active 전체(레거시 포함) + 가시 필드 술어
    "이력 일반어": lambda: (Order.active_filter(), visible_order_search_clause("cust123")),
    # 통합 검색 _term_prefilter: ERP 만, 숫자 4자리는 가운데 자리까지(전화 숫자 가지 포함)
    "통합 숫자 4자리": lambda: (
        Order.active_filter(),
        Order.is_erp_order.is_(True),
        erp_order_dashboard_search_predicate("%5678%", raw_query="5678"),
    ),
    # 과거 이력 숫자 4자리: 주문번호 정확 일치 + 전화 끝 4자리 정규식
    "이력 숫자 4자리": lambda: (Order.active_filter(), visible_order_search_clause("5678")),
    "이력 긴 숫자": lambda: (Order.active_filter(), visible_order_search_clause("01012345678")),
    # 주문 대시보드 고객 검색(customer_contact_only)
    "대시보드 고객 연락처": lambda: (
        Order.active_filter(),
        erp_order_dashboard_search_predicate("%5678%", customer_contact_only=True, raw_query="5678"),
    ),
}

# 새 인덱스마다 그 인덱스를 타는 화면 질의(음성 대조군용).
QUERY_USING_INDEX = {
    "ix_orders_sd_buyer_name_trgm": "이력 일반어",
    "ix_orders_sd_buyer_phone_trgm": "이력 숫자 4자리",
    "ix_orders_sd_manager_name_text_trgm": "이력 일반어",
    "ix_orders_erp_phone_digits_trgm": "통합 숫자 4자리",
    "ix_orders_id_text_trgm": "이력 일반어",
}


# --------------------------------------------------------------------------- #
# 전용 DB · 데이터
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def search_db_url(pg_admin_url: URL) -> Iterator[URL]:
    """이 스위트 전용 throwaway DB 를 만들고 끝나면 지운다."""
    db_name = assert_test_db_name(f"foms_test_searchtrgm_{uuid.uuid4().hex[:12]}")
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


def _seed_rows() -> list[dict[str, Any]]:
    """결정적 합성 주문. 10건마다 buyer, 25건마다 끝 4자리 5678, 6건마다 레거시."""
    rows = []
    for i in range(1, SEED_ROWS + 1):
        phone = f"010-{1000 + i % 9000:04d}-{5678 if i % 25 == 0 else 2000 + i % 3000:04d}"
        parties: dict[str, Any] = {
            "customer": {"name": f"cust{i:04d}", "phone": phone},
            "manager": {"name": f"mgr{i % 9}"},
            "orderer": {"name": f"ord{i:04d}"},
        }
        if i % 10 == 0:
            parties["buyer"] = {"name": f"buyer{i:04d}", "phone": f"010-77{i % 100:02d}-5678"}
        rows.append({
            "received_date": "2026-09-01",
            "customer_name": f"cust{i:04d}",
            "phone": phone,
            "address": f"road {i}",
            "product": f"prod{i:04d}",
            "manager_name": f"mgr{i % 9}",
            "status": "RECEIVED",
            "is_erp_order": i % 6 != 0,
            "erp_phone_digits": phone.replace("-", ""),
            "structured_data": {
                "parties": parties,
                "site": {"address_full": f"road {i} full", "address_main": f"road {i}"},
                "items": [{"product_name": f"prod{i:04d}", "name": f"item{i:04d}"}],
                "schedule": {
                    "measurement": {"date": "2026-09-01", "time": "10:00"},
                    "construction": {"date": "2026-10-01"},
                },
            },
        })
    return rows


@pytest.fixture(scope="module")
def search_engine(search_db_url: URL) -> Iterator[Engine]:
    """orders 만 create_all(models 레인) + 운영에 있는 기존 trgm 인덱스 + 합성 데이터."""
    import app  # noqa: F401  (모델 모듈 등록)
    from db import Base

    engine = create_engine(search_db_url, connect_args={"client_encoding": "utf8"}, poolclass=NullPool)
    # orders.partner_org_id → partner_orgs → users(owner) FK 대상도 함께 만든다(PARTNER-01·02).
    Base.metadata.create_all(bind=engine, tables=[User.__table__, PartnerOrg.__table__, Order.__table__])
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as ac:
        for expression, name in REGISTRY.items():
            if name not in NEW_INDEXES:  # 새 5개는 models(create_all)가 이미 만들었다
                ac.execute(text(
                    f"CREATE INDEX IF NOT EXISTS {name} ON orders "
                    f"USING gin ({mig._index_element(expression)} gin_trgm_ops)"
                ))
        ac.execute(insert(Order.__table__), _seed_rows())
        ac.execute(text("ANALYZE orders"))
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def ac(search_engine: Engine) -> Iterator[Connection]:
    """AUTOCOMMIT 연결(CONCURRENTLY DDL 용). 끝나면 새 인덱스 5개를 정상 상태로 되돌린다."""
    conn = search_engine.connect().execution_options(isolation_level="AUTOCOMMIT")
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
def test_create_all_lane_builds_the_five_valid_indexes(ac: Connection) -> None:
    """models(create_all)가 pg_trgm 확장과 새 인덱스 5개를 valid 로 만든다."""
    assert ac.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'")).scalar() == 1
    for name in NEW_INDEXES:
        assert mig.index_validity(ac, name) is True, name


def test_migration_roundtrip_matches_models_definitions(ac: Connection) -> None:
    """downgrade 는 5개만 걷어내고, upgrade 는 models 와 같은 정의로 되돌린다(2 사이클·멱등)."""
    baseline = _definitions(ac)
    assert set(NEW_INDEXES) <= set(baseline)
    for cycle in range(2):
        mig._apply_downgrade(ac)
        after_down = _definitions(ac)
        assert set(baseline) - set(after_down) == set(NEW_INDEXES), cycle
        mig._apply_upgrade(ac)
        mig._apply_upgrade(ac)  # 멱등: 이미 있으면 그대로
        assert _definitions(ac) == baseline, cycle


def test_upgrade_rebuilds_an_invalid_leftover(ac: Connection) -> None:
    """빌드 실패로 남은 INVALID 인덱스: IF NOT EXISTS 는 건너뛰고, upgrade 는 다시 만든다."""
    name = "ix_orders_id_text_trgm"
    expected = _definitions(ac)[name]
    some_id = ac.execute(text("SELECT min(id) FROM orders")).scalar_one()
    ac.execute(text(mig.drop_index_sql(name)))
    # 0 으로 나누기로 CONCURRENTLY 빌드를 중간에 실패시킨다 → 같은 이름의 INVALID 인덱스가 남는다.
    with pytest.raises(DBAPIError) as failed_build:
        ac.execute(text(
            f"CREATE INDEX CONCURRENTLY {name} ON orders "
            f"USING gin ((CAST((1 / (id - {int(some_id)})) AS VARCHAR)) gin_trgm_ops)"
        ))
    assert pg_error_code(failed_build.value) == "22012"  # division_by_zero
    assert mig.index_validity(ac, name) is False

    ac.execute(text(mig.create_index_sql(name)))  # 음성 대조군: IF NOT EXISTS 만으로는
    assert mig.index_validity(ac, name) is False  # 깨진 인덱스가 그대로 남는다

    mig._apply_upgrade(ac)
    assert mig.index_validity(ac, name) is True
    assert _definitions(ac)[name] == expected


# --------------------------------------------------------------------------- #
# 4. 가지 수 = 인덱스를 탄 수 (앱과 같은 드라이버 경로로 그린 SQL)
# --------------------------------------------------------------------------- #
def _statement(case: str):
    return select(Order.id).where(*SCREEN_QUERIES[case]())


def _explain(conn: Connection, case: str) -> str:
    """앱과 같은 실행 경로(바인드 처리 → ClientCursor 렌더링) 그대로, 문장 앞에 EXPLAIN 만 붙인다."""

    def _prefix_explain(_conn, _cursor, statement, parameters, _context, _executemany):
        return "EXPLAIN " + statement, parameters

    event.listen(conn, "before_cursor_execute", _prefix_explain, retval=True)
    try:
        rows = conn.execute(_statement(case)).all()
    finally:
        event.remove(conn, "before_cursor_execute", _prefix_explain)
    return "\n".join(row[0] for row in rows)


# 가지의 보조 조건(``is_erp_order = true``·``erp_phone_digits IS NOT NULL``)만 받는 btree 들.
# 이것으로도 OR 가지를 "ERP 활성 행 전부 읽기" 비트맵으로 채울 수 있어서, trgm 인덱스가 없는
# 가지가 있어도 BitmapOr 가 그대로 보인다(처음 쓴 음성 대조군이 이것 때문에 거짓 통과했다 —
# 합성 1,200행에서 플래너는 trgm 대신 ix_orders_erp_order_active 전체를 가지 대용으로 골랐다).
# 그래서 계획을 잴 때만 트랜잭션 안에서 빼고 "trgm 인덱스로만 OR 전체를 덮을 수 있는가"를 본다.
# 실데이터에서 플래너가 무엇을 고르는지는 스테이징 EXPLAIN(스펙 §9-3)의 몫이다.
STAND_IN_BTREES = ("ix_orders_is_erp_order", "ix_orders_erp_phone_digits", "ix_orders_erp_order_active")
# 등호 가지(주문번호 정확 일치)가 타는 인덱스 — trgm 이 아니어도 정당하다.
EQUALITY_INDEXES = frozenset({"orders_pkey"})


def _trgm_scans(plan: str) -> Counter:
    return Counter(n for n in re.findall(r"Bitmap Index Scan on (\w+)", plan) if n in TRGM_NAMES)


def _expected_scans(case: str) -> Counter:
    names = [n for clause in SCREEN_QUERIES[case]() for n in branch_index_names(clause, REGISTRY)]
    assert None not in names and names, names
    return Counter(names)


def _plan(engine: Engine, case: str, *, without: tuple[str, ...] = ()) -> str:
    """seqscan off 로 화면 질의를 EXPLAIN 한다. ``without`` 인덱스는 트랜잭션 안에서만 뺀다."""
    with engine.connect() as conn:
        conn.execute(text("SET LOCAL lock_timeout = '10s'"))
        for name in (*STAND_IN_BTREES, *without):
            conn.execute(text(f"DROP INDEX {name}"))  # rollback 으로 되살아난다
        conn.execute(text("SET LOCAL enable_seqscan = off"))
        plan = _explain(conn, case)
        conn.rollback()
    return plan


def test_stand_in_btrees_exist_in_the_models_lane(ac: Connection) -> None:
    """빼고 재는 btree 두 개가 실제로 있다(이름이 바뀌면 위 DROP 이 엉뚱하게 실패한다)."""
    assert set(STAND_IN_BTREES) <= set(_definitions(ac))


@pytest.mark.parametrize("case", list(SCREEN_QUERIES))
def test_screen_query_is_bitmapor_over_every_branch(search_engine: Engine, case: str) -> None:
    """Seq Scan 없이 BitmapOr, trgm Bitmap Index Scan 이 패턴 가지마다 하나씩(가지 수 = 인덱스 수)."""
    plan = _plan(search_engine, case)
    assert "Seq Scan" not in plan, plan
    assert "BitmapOr" in plan, plan
    assert _trgm_scans(plan) == _expected_scans(case), plan
    # 새 대용 인덱스(가지 조건 없이 행 묶음 전체를 읽는 것)가 생기면 여기서 드러난다.
    scanned = set(re.findall(r"Bitmap Index Scan on (\w+)", plan))
    assert scanned <= TRGM_NAMES | EQUALITY_INDEXES, sorted(scanned - TRGM_NAMES - EQUALITY_INDEXES)


@pytest.mark.parametrize("name", NEW_INDEXES)
def test_negative_control_without_the_new_index_bitmapor_is_lost(search_engine: Engine, name: str) -> None:
    """새 인덱스 하나만 빼도 같은 질의가 BitmapOr 를 잃는다 — 그 인덱스가 원인임을 대조로 고정."""
    plan = _plan(search_engine, QUERY_USING_INDEX[name], without=(name,))
    assert name not in plan
    assert "BitmapOr" not in plan, plan
    assert "Seq Scan" in plan, plan


# --------------------------------------------------------------------------- #
# 5. 결과 동일 — 인덱스 경로 = 순차 경로
# --------------------------------------------------------------------------- #
RESULT_CASES: dict[str, tuple[Callable[[], Any], set[int] | None]] = {
    "buyer 이름만 맞는 주문": (lambda: visible_order_search_clause("buyer0010"), {10}),
    "buyer 전화 가운데 자리": (
        lambda: erp_order_dashboard_search_predicate("%7720%", raw_query="7720"),
        None,
    ),
    "끝 4자리 정규식": (lambda: visible_order_search_clause("5678"), None),
    "주문번호 일부": (lambda: erp_order_dashboard_search_predicate("%1111%", raw_query="1111"), None),
}


def _ids(conn: Connection, clause: Any) -> set[int]:
    return set(conn.execute(select(Order.id).where(Order.active_filter(), clause)).scalars())


@pytest.mark.parametrize("case", list(RESULT_CASES))
def test_index_path_returns_the_same_rows_as_sequential_scan(search_engine: Engine, case: str) -> None:
    """trgm 인덱스는 속도만 바꾼다 — 같은 술어의 결과 id 가 순차 경로와 같다."""
    build, exact = RESULT_CASES[case]
    with search_engine.connect() as conn:
        conn.execute(text("SET LOCAL enable_seqscan = off"))
        via_index = _ids(conn, build())
        conn.rollback()
        for setting in ("enable_bitmapscan", "enable_indexscan", "enable_indexonlyscan"):
            conn.execute(text(f"SET LOCAL {setting} = off"))
        via_seq = _ids(conn, build())
        conn.rollback()
    assert via_index, "결과 0건 — 비교가 무의미하다"
    assert via_index == via_seq
    if exact is not None:
        assert via_index == exact
