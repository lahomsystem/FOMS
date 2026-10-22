"""MINE-TOPDRAW-00 계약: mine 필터의 패턴 가지마다 같은 식의 trgm 인덱스가 있다.

설계서 ``docs/specs/2026-10-22-mine-toplevel-drawing-assignees-index_SPEC.md``. 가지 하나라도 인덱스가
없으면 범위 안 행마다 ``structured_data`` 를 푼다(2026-10-22 운영 ADMIN mine 목록 질의 70~80ms).
"""

from __future__ import annotations

import pytest
from sqlalchemy.dialects import postgresql

import foms.services.erp_permissions as ep
from tests.support import search_index_contract as sic


class _U:
    def __init__(self, name, username, uid, team, role):
        self.name, self.username, self.id, self.team, self.role = name, username, uid, team, role


USERS = {
    "ADMIN all": _U("인덱스관리", "idx_admin", 7, "SALES", "ADMIN"),
    "DRAWING": _U("인덱스도면", "idx_drawing", 8, "DRAWING", "STAFF"),
    "SALES": _U("인덱스영업", "idx_sales", 9, "SALES", "STAFF"),
    "CONSTRUCTION": _U("인덱스시공", "idx_const", 10, "CONSTRUCTION", "STAFF"),
}


@pytest.fixture(autouse=True)
def _pg_dialect(monkeypatch):
    monkeypatch.setattr(ep, "_current_dialect_name", lambda: "postgresql")


@pytest.mark.parametrize("who", list(USERS))
def test_every_mine_pattern_branch_has_a_trgm_index(who: str) -> None:
    registry = sic.orders_trgm_index_registry()
    for cond in ep.build_mine_sql_filter(USERS[who]):
        for branch in sic.pattern_branches(cond):
            expr = sic.branch_expression(branch)
            assert registry.get(expr), f"{who}: 인덱스 없는 mine 가지 — {expr}"


def test_negative_control_toplevel_branch_unindexed_without_this_migration() -> None:
    """이 마이그레이션을 빼면 최상위 drawing_assignees 가지만 인덱스가 없다."""
    registry = sic.orders_trgm_index_registry()
    mine_top = sic.load_migration("mine_toplevel_drawing_idx_00.py")
    for expr in mine_top.MINE_TRGM_INDEXES.values():
        registry.pop(expr)
    missing = {
        sic.branch_expression(b)
        for cond in ep.build_mine_sql_filter(USERS["ADMIN all"])
        for b in sic.pattern_branches(cond)
        if not registry.get(sic.branch_expression(b))
    }
    assert missing == set(mine_top.MINE_TRGM_INDEXES.values())


def test_migration_expression_matches_app_sql_character_for_character() -> None:
    mine_top = sic.load_migration("mine_toplevel_drawing_idx_00.py")
    from models import Order

    cond = ep._json_string_token_condition(Order.structured_data["drawing_assignees"], "x", dialect_name="postgresql")
    rendered = str(cond.left.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert rendered.replace("orders.", "") in mine_top.MINE_TRGM_INDEXES.values()
    assert mine_top.down_revision == "session_rev_00"
    assert "CONCURRENTLY IF NOT EXISTS" in mine_top.create_index_sql("ix_orders_sd_toplevel_drawing_assignees_trgm")
