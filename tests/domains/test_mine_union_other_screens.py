"""다른 화면 "내 주문" 조건 — 배지·실측과 같은 UNION 멤버십 계약.

설계서 docs/specs/2026-10-06-nav-badge-count-query_SPEC.md §9.
이력·통합 검색·도면 작업대는 ``build_mine_sql_filter`` 조건을 ``or_(*conds)`` 대신
``mine_membership_clause`` 로 묶는다. 범위 있는 대시보드 계열(타워·대시보드·생산·시공·AS·완료 큐)은
HYBRID(``scope_conds``)로 바꿨다 — 계약은 tests/domains/test_mine_filter_scoped_screens.py.

1. 모양: 각 경로 소스에 ``or_(*..mine/conds..)`` 꼴이 남지 않고 헬퍼를 부른다.
2. 동일성: 팀·도면 scope 별로 옛 OR 꼴과 주문 번호 집합이 같다(음성 대조군 포함).
3. 빈 조건: 호출부 기존 의미(0건 술어 또는 필터 없음)를 유지한다.
"""
from __future__ import annotations

import inspect
import re

import pytest
from sqlalchemy import or_
from sqlalchemy.dialects import postgresql
from werkzeug.security import generate_password_hash

import foms.services.foms_unified_search as unified_search
import foms.web.drawing.workbench as drawing_workbench
import foms.web.orders.history as history
from db import db_session, get_db
from foms.services.erp_permissions import build_mine_sql_filter, mine_membership_clause
from models import Order, User

_OR_MINE_RE = re.compile(r"or_\(\*\w*(mine|conds|conditions)\w*\)")

_MODULES = (unified_search, drawing_workbench, history)


@pytest.mark.parametrize("mod", _MODULES, ids=lambda m: m.__name__)
def test_screen_uses_membership_clause(mod):
    src = inspect.getsource(mod)
    assert not _OR_MINE_RE.search(src), f"{mod.__name__}: or_(*mine) 꼴이 남았다"
    assert "mine_membership_clause(build_mine_sql_filter(" in src, mod.__name__


def test_drawing_workbench_keeps_scope_argument():
    src = inspect.getsource(drawing_workbench)
    assert "mine_membership_clause(build_mine_sql_filter(current_user, scope=mine_scope))" in src


def _user(name: str, team: str, role: str = "STAFF") -> User:
    user = User(
        username=f"other_union_{name}",
        password=generate_password_hash("x"),
        role=role,
        team=team,
        name=name,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _order(manager: str, status: str, **sd) -> Order:
    return Order(
        received_date="2026-10-06",
        customer_name="C",
        phone="010-0000-0000",
        address="A",
        product="P",
        status=status,
        is_erp_order=True,
        manager_name=manager,
        structured_data=sd,
    )


def test_unified_search_owner_scope_shape_and_empty(app):
    with app.app_context():
        sales = _user("검색영업", "SALES")
        clause = unified_search._owner_scope(sales)
        sql = str(get_db().query(Order.id).filter(clause).statement.compile(dialect=postgresql.dialect()))
        assert sql.count("FROM orders AS orders_mine") == len(build_mine_sql_filter(sales))
        assert unified_search._owner_scope(None) is None


def test_other_screen_ids_match_or_form(app):
    with app.app_context():
        users = [
            _user("확대영업", "SALES"),
            _user("확대시공", "CONSTRUCTION"),
            _user("확대도면", "DRAWING"),
            _user("확대관리", "ADMIN", role="ADMIN"),
            _user("확대고객", "CS"),
        ]
        db_session.add_all(
            [
                _order("확대영업", "MEASURE"),
                _order("다른사람", "MEASURE"),
                _order("다른사람", "CONSTRUCTION", shipment={"construction_workers": ["확대시공"]}),
                _order("확대시공", "CS"),
                _order("다른사람", "DRAWING", assignments={"drawing_assignees": ["확대도면"]}),
                _order("확대관리", "COMPLETED"),
                _order("확대고객", "AS_RECEIVED"),
            ]
        )
        db_session.commit()
        checked = 0
        matched = 0
        for user in users:
            for scope in (None, "all", "sales", "construction", "drawing"):
                conds = build_mine_sql_filter(user, scope=scope)
                if not conds:
                    assert mine_membership_clause(conds) is None
                    continue
                base = get_db().query(Order.id)
                old = sorted(r[0] for r in base.filter(or_(*conds)).all())
                new = sorted(r[0] for r in base.filter(mine_membership_clause(conds)).all())
                assert new == old, f"{user.team}/{scope}: {new} != {old}"
                checked += 1
                matched += len(old)
        assert checked >= 8
        assert matched > 0, "음성만 비교했다 — 매칭 주문이 하나도 없다"
