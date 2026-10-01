"""검색 술어 가지 ↔ trgm 인덱스 대조 도구 (SEARCH-TRGM-00 계약 테스트 공용).

OR 술어의 가지 하나라도 인덱스가 없으면 PostgreSQL 은 BitmapOr 를 만들지 못하고 후보 행
전부를 읽으며 가지마다 ``structured_data`` 를 다시 푼다(스펙
``docs/specs/2026-10-01-search-index-perf_SPEC.md`` §1.2). 그래서 계약은 "패턴 가지(ILIKE·
LIKE·contains·정규식)마다, 그 가지의 왼쪽 식과 **글자 단위로 같은** trgm 인덱스가 운영
마이그레이션에 있다" 이다. 식이 한 글자만 달라도(``->`` 와 ``->>``) 플래너는 인덱스를 못 쓴다.

등호 가지(주문번호 정확 일치 등)는 btree 몫이라 대조하지 않는다.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import operators, visitors
from sqlalchemy.sql.elements import BinaryExpression

ROOT = Path(__file__).resolve().parents[2]
VERSIONS = ROOT / "migrations" / "versions"

PATTERN_OPERATORS = frozenset(
    {operators.ilike_op, operators.like_op, operators.contains_op, operators.regexp_match_op}
)

# phase_d 는 DDL 을 리터럴로만 적어 상수로 읽을 수 없다 — 원문에 있는지 확인하고 쓴다.
_PHASE_D_INDEXES: dict[str, tuple[str, str]] = {
    "manager_name": ("ix_orders_manager_name_trgm", "USING gin (manager_name gin_trgm_ops)"),
    "CAST(structured_data AS VARCHAR)": (
        "ix_orders_structured_data_text_trgm",
        "USING gin (CAST(structured_data AS VARCHAR) gin_trgm_ops)",
    ),
}


def load_migration(filename: str) -> ModuleType:
    """``migrations/versions`` 의 리비전 파일을 경로로 읽는다(패키지가 아니다).

    Args:
        filename: 리비전 파일 이름.

    Returns:
        최상위 상수만 실행된 모듈(DB 부작용 없음).
    """
    spec = importlib.util.spec_from_file_location(filename.removesuffix(".py"), VERSIONS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SEARCH_TRGM = load_migration("search_trgm_00_visible_field_indexes.py")


def orders_trgm_index_registry() -> dict[str, str]:
    """운영 마이그레이션이 orders 에 만드는 trgm 인덱스 — ``{식: 인덱스 이름}``.

    Returns:
        phase_d·phase_e·phase_f·search_trgm_00 의 orders trgm 인덱스 식(``orders.`` 접두 없음).

    Raises:
        AssertionError: phase_d 원문에서 기대한 DDL 이 사라졌을 때(대조 기준이 낡았다).
    """
    phase_d_source = (VERSIONS / "phase_d_trgm_indexes.py").read_text(encoding="utf-8")
    registry: dict[str, str] = {}
    for expression, (name, ddl_fragment) in _PHASE_D_INDEXES.items():
        assert name in phase_d_source and ddl_fragment in phase_d_source, f"phase_d 원문에 {name} DDL 이 없다"
        registry[expression] = name
    phase_e = load_migration("phase_e_trgm_perm_indexes.py")
    registry.update({expression: name for name, expression in phase_e._PERM_TRGM_INDEXES.items()})
    phase_f = load_migration("phase_f_trgm_search_indexes.py")
    registry.update(
        {column: name for table, name, column in phase_f._SIMPLE_TRGM_INDEXES if table == "orders"}
    )
    registry.update({expression: name for name, expression in phase_f._ORDER_SD_TRGM_INDEXES.items()})
    registry.update({expression: name for name, expression in SEARCH_TRGM.SEARCH_TRGM_INDEXES.items()})
    return registry


def pattern_branches(clause: Any) -> list[BinaryExpression]:
    """술어 안의 패턴 가지(ILIKE·LIKE·contains·정규식)를 모두 고른다.

    Args:
        clause: SQLAlchemy 술어.

    Returns:
        패턴 연산자를 쓰는 이항식 목록.
    """
    return [
        element
        for element in visitors.iterate(clause)
        if isinstance(element, BinaryExpression) and element.operator in PATTERN_OPERATORS
    ]


def branch_expression(branch: BinaryExpression) -> str:
    """가지의 왼쪽 식을 PostgreSQL 방언으로 그린 SQL(인덱스 DDL 에 못 쓰는 ``orders.`` 만 뺌).

    Args:
        branch: :func:`pattern_branches` 가 고른 가지.

    Returns:
        인덱스 식과 글자 단위로 대조할 문자열.
    """
    sql = str(branch.left.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    return sql.replace("orders.", "")


def branch_index_names(clause: Any, registry: dict[str, str]) -> list[str | None]:
    """가지마다 탈 인덱스 이름 — 같은 식의 인덱스가 없으면 ``None``.

    Args:
        clause: SQLAlchemy 술어.
        registry: :func:`orders_trgm_index_registry` 결과.

    Returns:
        가지 순서대로 인덱스 이름(없으면 None).
    """
    return [registry.get(branch_expression(branch)) for branch in pattern_branches(clause)]
