"""SEARCH-TRGM-00 계약: 검색 술어의 패턴 가지마다 같은 식의 trgm 인덱스가 있다 (DB 불필요).

과거 이력·통합 검색 술어는 OR 가지가 19~20개다. 가지 하나라도 인덱스가 없으면 BitmapOr 가
깨져 후보 행 전부를 읽는다(2026-09-29 #439 이후 운영 p50 +120~200ms). 08-20 에 buyer 가지가
인덱스 없이 들어왔고, ``perf-ok`` 주석이 다른 가지의 인덱스 이름을 달고 있어 가드가 못 잡았다.

이 파일이 고정하는 것(SQLite 메인 CI 에서 초 단위로 돈다):

1. 화면이 쓰는 술어를 실제로 만들어, 패턴 가지마다 왼쪽 식이 운영 마이그레이션의 trgm 인덱스
   식과 글자 단위로 같다. 음성 대조군: 인덱스 없는 경로, 한 글자만 다른 ``->`` 식은 잡힌다.
2. ``models.Order`` 의 새 인덱스 DDL 이 마이그레이션 ``search_trgm_00`` 과 글자 단위로 같다
   (create_all 레인 ↔ alembic 레인 정합). SQLite 레인에서는 만들지 않는다.
3. ``erp_dashboard_search.py`` 의 인덱스 이름 주석은 실제 trgm 인덱스만 가리킨다.

실제 플래너가 BitmapOr 를 고르는지는 PG 레인 ``tests/postgres/test_search_trgm_indexes_pg.py``.
"""

from __future__ import annotations

import re
from typing import Any, Callable

import pytest
from sqlalchemy import String, cast, create_engine, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex

from foms.services.erp_dashboard_search import (
    _order_id_match_clause,
    erp_order_dashboard_search_predicate,
    visible_order_search_clause,
)
from models import Order
from tests.support.search_index_contract import (
    ROOT,
    SEARCH_TRGM,
    branch_expression,
    branch_index_names,
    orders_trgm_index_registry,
    pattern_branches,
)

REGISTRY = orders_trgm_index_registry()
NEW_INDEXES = list(SEARCH_TRGM.SEARCH_TRGM_INDEXES)

# 화면별 실제 술어. 숫자 4자리 이상이면 전화 숫자 가지(erp_phone_digits)가 붙는다.
SEARCH_CASES: dict[str, Callable[[], Any]] = {
    "이력·통합 일반어": lambda: visible_order_search_clause("cust123"),
    "통합 숫자 4자리(가운데 자리 포함)": lambda: erp_order_dashboard_search_predicate("%5678%", raw_query="5678"),
    "긴 숫자": lambda: visible_order_search_clause("01012345678"),
    "이력 숫자 4자리(끝자리 정규식)": lambda: visible_order_search_clause("5678"),
    "대시보드 고객 연락처": lambda: erp_order_dashboard_search_predicate(
        "%5678%", customer_contact_only=True, raw_query="5678"
    ),
    "레거시 대시보드 주문번호 가지": lambda: _order_id_match_clause("abc", "%abc%"),
}

# 스펙 §2.1 의 가지 수(일반어 19 · 숫자 20). 바뀌면 인덱스도 같이 봐야 한다는 신호다.
EXPECTED_BRANCH_COUNTS = {"이력·통합 일반어": 19, "통합 숫자 4자리(가운데 자리 포함)": 20}


@pytest.mark.parametrize("case", list(SEARCH_CASES))
def test_every_pattern_branch_has_a_trgm_index_with_the_same_expression(case: str) -> None:
    """패턴 가지마다 같은 식의 trgm 인덱스가 있다 — 하나라도 없으면 BitmapOr 가 깨진다."""
    clause = SEARCH_CASES[case]()
    branches = pattern_branches(clause)
    assert branches, "패턴 가지가 0개 — 대조할 모집단이 비었다"
    if case in EXPECTED_BRANCH_COUNTS:
        assert len(branches) == EXPECTED_BRANCH_COUNTS[case]

    missing = [branch_expression(b) for b in branches if branch_expression(b) not in REGISTRY]
    assert not missing, (
        "인덱스 없는 검색 가지가 생겼다 — 같은 식의 trgm 인덱스를 마이그레이션·models 에 더하라:\n  "
        + "\n  ".join(missing)
    )


def test_each_new_index_is_used_by_some_search_branch() -> None:
    """새 인덱스 5개가 모두 어떤 화면의 가지와 식이 맞는다(쓰이지 않는 인덱스가 없다)."""
    used = {name for build in SEARCH_CASES.values() for name in branch_index_names(build(), REGISTRY)}
    assert set(NEW_INDEXES) <= used, sorted(set(NEW_INDEXES) - used)


@pytest.mark.parametrize(
    "branch",
    [
        # 인덱스 없는 경로
        Order.structured_data["parties"]["buyer"]["email"].as_string().ilike("%x%"),
        # 한 글자 차이: ``->`` (따옴표 붙은 JSON 문자열) — 스펙 §2.1 manager 가지와 같은 함정
        cast(Order.structured_data["parties"]["buyer"]["name"], String).ilike("%x%"),
    ],
    ids=["no-index-path", "arrow-instead-of-text-arrow"],
)
def test_negative_control_branches_without_matching_index_are_caught(branch: Any) -> None:
    """음성 대조군: 대조기가 인덱스 없는 가지·한 글자 다른 식을 실제로 잡는다."""
    assert branch_index_names(branch, REGISTRY) == [None]


def test_without_this_migration_the_five_branches_would_be_unindexed() -> None:
    """음성 대조군: 새 인덱스를 빼면 정확히 그 가지들이 빠진다(스펙 §1.2 의 막는 가지 다섯)."""
    without_new = {expr: name for expr, name in REGISTRY.items() if name not in NEW_INDEXES}
    unindexed = {
        branch_expression(branch)
        for build in SEARCH_CASES.values()
        for branch in pattern_branches(build())
        if branch_expression(branch) not in without_new
    }
    assert unindexed == set(SEARCH_TRGM.SEARCH_TRGM_INDEXES.values())


def _model_index(name: str):
    return next(index for index in Order.__table__.indexes if index.name == name)


@pytest.mark.parametrize("name", NEW_INDEXES)
def test_models_index_ddl_matches_migration_character_for_character(name: str) -> None:
    """models(create_all 레인)와 마이그레이션(운영)이 같은 DDL 을 낸다."""
    model_sql = str(CreateIndex(_model_index(name)).compile(dialect=postgresql.dialect()))
    migration_sql = SEARCH_TRGM.create_index_sql(name).replace("CONCURRENTLY IF NOT EXISTS ", "")
    assert model_sql == migration_sql


def test_migration_ddl_shape() -> None:
    """CONCURRENTLY·멱등·gin_trgm_ops, downgrade 는 IF EXISTS (create_all 레인에는 처음부터 있다)."""
    for name in NEW_INDEXES:
        create_sql = SEARCH_TRGM.create_index_sql(name)
        assert create_sql.startswith(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON orders USING gin (")
        assert create_sql.endswith(" gin_trgm_ops)")
        assert SEARCH_TRGM.drop_index_sql(name) == f"DROP INDEX CONCURRENTLY IF EXISTS {name}"
    assert SEARCH_TRGM.down_revision == "nvmirror_00"


def test_models_trgm_indexes_are_not_created_on_sqlite() -> None:
    """SQLite 레인 create_all 은 trgm 인덱스를 만들지 않는다(ddl_if) — 실제 DDL 발행으로 확인."""
    engine = create_engine("sqlite://")
    try:
        Order.__table__.create(bind=engine)
        with engine.connect() as conn:
            names = {row[0] for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type = 'index'"))}
    finally:
        engine.dispose()
    assert names, "SQLite 에 인덱스가 하나도 없다 — 대조가 무의미하다"
    assert not (set(NEW_INDEXES) & names)


def _cited_index_names(line: str) -> list[str]:
    """줄의 주석 부분에서 인덱스 이름(``ix_...``)을 모두 읽는다."""
    comment = line.split("#", 1)[1] if "#" in line else ""
    return re.findall(r"\bix_[a-z0-9_]+", comment)


def test_negative_control_comment_parser_reads_the_old_btree_citation() -> None:
    """음성 대조군: 고치기 전 주석(btree 이름)은 trgm 목록에 없어 잡힌다."""
    old_line = "Order.erp_phone_digits.contains(digits),  # perf-ok: ix_orders_erp_phone_digits"
    assert _cited_index_names(old_line) == ["ix_orders_erp_phone_digits"]
    assert "ix_orders_erp_phone_digits" not in set(REGISTRY.values())


def test_search_module_index_comments_cite_real_trgm_indexes() -> None:
    """``erp_dashboard_search.py`` 의 인덱스 이름 주석은 운영에 있는 trgm 인덱스만 가리킨다."""
    source = (ROOT / "foms" / "services" / "erp_dashboard_search.py").read_text(encoding="utf-8")
    cited = [name for line in source.splitlines() for name in _cited_index_names(line)]
    assert len(cited) >= 20, "주석 인용이 너무 적다 — 파서가 아무것도 못 읽고 있다"
    known = set(REGISTRY.values())
    stale = sorted({name for name in cited if name not in known})
    assert not stale, f"없는 인덱스(또는 btree)를 가리키는 주석: {stale}"
    assert set(NEW_INDEXES) <= set(cited)
