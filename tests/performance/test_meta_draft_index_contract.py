"""DRAFTIDX-00 계약: 초안 술어는 번호 목록 서브쿼리로 읽고, 그 조건은 부분 인덱스와 같다 (DB 불필요).

모든 운영 화면에 붙는 ``Order.active_filter()`` 의 초안 가지는 행마다 ``structured_data`` 를 풀어
``meta.draft`` 를 읽었다(스테이징 대시보드 조각 56ms, 스펙
``docs/specs/2026-10-05-perf-db-draft-flag-and-stats_SPEC.md`` §1.2). 지금은 "표식이 켜진 번호
목록에 있나"를 보고, 그 목록은 같은 조건의 부분 인덱스 ``ix_orders_meta_draft_true`` 만 읽는다.

이 파일이 고정하는 것(SQLite 메인 CI 에서 초 단위로 돈다):

1. models 인덱스 DDL ↔ 마이그레이션 ``draftidx_00`` 가 글자 단위로 같다(create_all ↔ alembic).
2. 번호 목록 서브쿼리 조건(별칭 접두만 뺀 것) ↔ 인덱스 조건이 글자 단위로 같다. 조건이 어긋나면
   플래너가 인덱스를 못 쓰고 서브쿼리가 표 전체를 푼다. 음성 대조군: ``->``/``->>`` 로 쓴 같은
   뜻의 식은 잡힌다.
3. 네 필터 모두 바깥 ``orders.structured_data`` 를 읽지 않는다. 음성 대조군: 옛 술어·별칭 없는
   서브쿼리는 잡힌다.
4. 뜻이 그대로다 — SQLite 에서 경우 18가지의 옛/새 결과가 같고, 숨은 실제 주문 모양은 계속
   숨는다. 음성 대조군: status 만 보는 술어는 숨은 주문에서 갈린다.

실제 플래너가 인덱스·hashed SubPlan 을 고르는지는 PG 레인 ``tests/postgres/
test_meta_draft_predicate_pg.py``.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Iterator

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Connection
from sqlalchemy.orm import aliased
from sqlalchemy.schema import CreateIndex

import models
from models import Order
from tests.support.meta_draft_contract import (
    CASE_KEYS,
    DRAFTIDX,
    FILTER_NAMES,
    HIDDEN_ORDER_KEYS,
    NEGATIVE_CONTROL_FILTERS,
    NEW_FILTERS,
    OLD_FILTERS,
    insert_cases,
)

ALIAS_PREFIX = f"{models.META_DRAFT_ALIAS}."


def _pg_sql(clause: Any) -> str:
    """앱과 같은 PostgreSQL 방언으로, 바인드 값을 넣은 채 그린다."""
    return str(clause.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def _model_index():
    return next(index for index in Order.__table__.indexes if index.name == models.META_DRAFT_INDEX_NAME)


# --------------------------------------------------------------------------- #
# 1. models ↔ 마이그레이션
# --------------------------------------------------------------------------- #
def test_models_index_ddl_matches_migration_character_for_character() -> None:
    """models(create_all 레인)와 마이그레이션(운영)이 같은 DDL 을 낸다."""
    model_sql = str(CreateIndex(_model_index()).compile(dialect=postgresql.dialect()))
    migration_sql = DRAFTIDX.create_index_sql().replace("CONCURRENTLY IF NOT EXISTS ", "")
    assert model_sql == migration_sql


def test_migration_ddl_shape() -> None:
    """CONCURRENTLY·멱등·부분 인덱스, downgrade 는 IF EXISTS, 부모는 직전 head."""
    assert DRAFTIDX.INDEX_NAME == models.META_DRAFT_INDEX_NAME
    assert DRAFTIDX.INDEX_WHERE == models.META_DRAFT_INDEX_WHERE
    assert DRAFTIDX.create_index_sql() == (
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_orders_meta_draft_true ON orders (id) "
        f"WHERE {models.META_DRAFT_INDEX_WHERE}"
    )
    assert DRAFTIDX.drop_index_sql() == "DROP INDEX CONCURRENTLY IF EXISTS ix_orders_meta_draft_true"
    assert DRAFTIDX.revision == "draftidx_00"
    assert DRAFTIDX.down_revision == "search_trgm_00"


def test_partial_index_is_not_created_on_sqlite() -> None:
    """SQLite 레인 create_all 은 이 인덱스를 만들지 않는다(ddl_if) — 실제 DDL 발행으로 확인."""
    engine = create_engine("sqlite://")
    try:
        Order.__table__.create(bind=engine)
        with engine.connect() as conn:
            names = {row[0] for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type = 'index'"))}
    finally:
        engine.dispose()
    assert names, "SQLite 에 인덱스가 하나도 없다 — 대조가 무의미하다"
    assert models.META_DRAFT_INDEX_NAME not in names


# --------------------------------------------------------------------------- #
# 2. 서브쿼리 조건 ↔ 인덱스 조건
# --------------------------------------------------------------------------- #
def _subquery_condition(subquery: Any) -> str:
    """번호 목록 서브쿼리의 WHERE 를 그리고 별칭 접두를 뺀다(인덱스 DDL 에는 표 이름을 못 쓴다)."""
    return _pg_sql(subquery.whereclause).replace(ALIAS_PREFIX, "")


def test_subquery_condition_matches_index_predicate_character_for_character() -> None:
    """앱이 그리는 서브쿼리 조건 = 인덱스 조건 — 플래너가 부분 인덱스를 고를 수 있는 전제."""
    subquery = Order._meta_draft_order_ids()
    assert _pg_sql(subquery).startswith(
        f"SELECT {ALIAS_PREFIX}id \nFROM orders AS {models.META_DRAFT_ALIAS} \nWHERE "
    )
    assert _subquery_condition(subquery) == models.META_DRAFT_INDEX_WHERE


def test_negative_control_same_meaning_different_operator_is_caught() -> None:
    """음성 대조군: 같은 뜻이라도 ``->``/``->>`` 로 쓴 식은 인덱스 조건과 다르다고 잡힌다."""
    flagged = aliased(Order, name=models.META_DRAFT_ALIAS)
    near_miss = select(flagged.id).where(flagged.structured_data["meta"]["draft"].as_boolean().is_(True))
    assert _subquery_condition(near_miss) != models.META_DRAFT_INDEX_WHERE


# --------------------------------------------------------------------------- #
# 3. 바깥 행은 JSON 을 읽지 않는다
# --------------------------------------------------------------------------- #
_OUTER_JSON_READ = re.compile(r"(?<![\w.])orders\.structured_data\b")


def _reads_outer_json(clause: Any) -> bool:
    return bool(_OUTER_JSON_READ.search(_pg_sql(select(Order.id).where(clause))))


@pytest.mark.parametrize("name", FILTER_NAMES)
def test_filters_read_the_id_list_not_the_outer_json(name: str) -> None:
    """네 필터 모두 번호 목록(별칭 서브쿼리)을 대조하고 바깥 ``orders.structured_data`` 는 안 읽는다."""
    sql = _pg_sql(select(Order.id).where(NEW_FILTERS[name]()))
    assert f"orders.id IN (SELECT {ALIAS_PREFIX}id \nFROM orders AS {models.META_DRAFT_ALIAS} " in sql
    assert not _reads_outer_json(NEW_FILTERS[name]()), sql


@pytest.mark.parametrize("name", FILTER_NAMES)
def test_negative_control_old_predicate_reads_outer_json(name: str) -> None:
    """음성 대조군: 옛 술어는 바깥 행마다 JSON 을 읽는다 — 검사기가 그것을 잡는다."""
    assert _reads_outer_json(OLD_FILTERS[name]())


def test_negative_control_unaliased_subquery_is_caught() -> None:
    """음성 대조군: 별칭 없이 ``orders`` 로 서브쿼리를 짜면 안팎 이름이 겹쳐 검사기가 잡는다."""
    same_name = select(Order.id).where(Order.structured_data[("meta", "draft")].as_boolean().is_(True))
    assert _reads_outer_json(Order.id.in_(same_name))


def test_draft_filter_and_predicate_share_one_subquery() -> None:
    """``erp_draft_filter`` 와 ``erp_draft_predicate`` 가 같은 도우미를 쓴다(두 벌로 갈라지지 않는다)."""
    subquery_sql = _pg_sql(Order._meta_draft_order_ids())
    for name in ("erp_draft_filter", "erp_draft_predicate"):
        assert subquery_sql in _pg_sql(NEW_FILTERS[name]())


# --------------------------------------------------------------------------- #
# 4. 뜻이 그대로다 (SQLite)
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def sqlite_cases() -> Iterator[tuple[Connection, dict[int, str]]]:
    """orders 만 있는 메모리 SQLite 에 경우 행을 넣는다."""
    engine = create_engine("sqlite://")
    Order.__table__.create(bind=engine)
    conn = engine.connect()
    try:
        ids = insert_cases(conn)
        conn.commit()
        yield conn, ids
    finally:
        conn.close()
        engine.dispose()


def _keys(conn: Connection, ids: dict[int, str], build: Callable[[], Any]) -> set[str]:
    return {ids[row_id] for row_id in conn.execute(select(Order.id).where(build())).scalars()}


@pytest.mark.parametrize("name", FILTER_NAMES)
def test_new_filter_selects_the_same_rows_as_the_frozen_old_predicate(sqlite_cases, name: str) -> None:
    """경우 18가지에서 옛/새 결과가 같다(스테이징 전 행·앱 쿼리 대조는 스펙 §3.3)."""
    conn, ids = sqlite_cases
    assert len(CASE_KEYS) == 18 and set(ids.values()) == set(CASE_KEYS)
    old = _keys(conn, ids, OLD_FILTERS[name])
    new = _keys(conn, ids, NEW_FILTERS[name])
    assert old, "결과 0건 — 비교가 무의미하다"
    assert new == old


def test_hidden_real_order_shape_stays_hidden(sqlite_cases) -> None:
    """표식이 남은 실제 주문 모양은 계속 모든 운영 화면에서 빠진다(보이게 하기는 별도 결정)."""
    conn, ids = sqlite_cases
    for name in ("active_filter", "active_including_trashed_filter"):
        assert not set(HIDDEN_ORDER_KEYS) & _keys(conn, ids, NEW_FILTERS[name]), name
    assert set(HIDDEN_ORDER_KEYS) <= _keys(conn, ids, NEW_FILTERS["erp_draft_filter"])


@pytest.mark.parametrize(
    ("name", "expected_extra"),
    [
        ("active_filter", set(HIDDEN_ORDER_KEYS)),
        ("active_including_trashed_filter",
         set(HIDDEN_ORDER_KEYS) | {"deleted_draft", "deleted_promoted_flag_on", "deleted_at_only_flag_on"}),
    ],
)
def test_negative_control_status_only_predicate_differs(sqlite_cases, name: str, expected_extra: set[str]) -> None:
    """음성 대조군: status 만 보면 숨은 주문(휴지통 포함 화면은 지운 초안까지)이 나타난다."""
    conn, ids = sqlite_cases
    old = _keys(conn, ids, OLD_FILTERS[name])
    status_only = _keys(conn, ids, NEGATIVE_CONTROL_FILTERS[name])
    assert status_only - old == expected_extra
    assert not old - status_only
