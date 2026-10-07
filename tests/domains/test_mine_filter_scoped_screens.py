"""범위 있는 화면 7곳 "내 주문" — HYBRID 계약.

설계서 docs/specs/2026-10-07-mine-filter-scoped-screens_SPEC.md.
가벼운 갈래는 바깥 범위를 넣은 UNION, 무거운 갈래(도면 문서 전체 ILIKE)만 바깥 OR.

1. 표시 계약: ``build_mine_sql_filter`` 가 무거운 조건을 이름당 정확히 1개 표시한다.
   표시를 빼면 이 계약이 깨지는 것을 음성 대조로 확인한다.
2. 모양: HYBRID 절은 ``IN (UNION)`` + 표시된 원본 무거운 조건의 OR 이다. 7곳 소스가 헬퍼를
   ``scope_conds=[...whereclause]`` 로 부르고 ``or_(*conds)`` 꼴이 없다.
3. 동일성: 범위 R 에 대해 ``R ∧ or_(*conds)`` 와 주문 번호 집합이 같다(범위 밖 내 주문 제외 포함).
"""
from __future__ import annotations

import inspect
import re

import pytest
from sqlalchemy import and_, or_
from sqlalchemy.sql import operators
from sqlalchemy.sql.elements import BooleanClauseList
from werkzeug.security import generate_password_hash

import foms.api.cs.dashboard as cs_dashboard
import foms.services.erp_permissions as ep
import foms.services.orders.dashboard_control_tower as tower
import foms.services.orders.dashboard_read_model as dash_read_model
import foms.services.production_read_model as production_read_model
import foms.web.construction.dashboard as construction_dashboard
import foms.web.cs.as_dashboard as as_dashboard
from db import db_session, get_db
from foms.services.erp_permissions import (
    build_mine_sql_filter,
    is_doc_scan_mine_cond,
    mine_membership_clause,
)
from models import Order, User


class _U:
    def __init__(self, name, username, uid, team="DRAWING", role="STAFF"):
        self.name, self.username, self.id, self.team, self.role = name, username, uid, team, role


def _heavy(conds):
    return [c for c in conds if is_doc_scan_mine_cond(c)]


@pytest.mark.parametrize("scope,expected", [("all", 2), ("drawing", 2), ("sales", 0), ("construction", 0)])
def test_doc_scan_marker_one_per_name(app, scope, expected):
    with app.app_context():
        conds = build_mine_sql_filter(_U("표시도면", "mark_drawing", 7), scope=scope)
        heavy = _heavy(conds)
        assert len(heavy) == expected
        for c in heavy:  # 표시된 것은 실제로 문서 전체 ILIKE 를 품은 and_ 복합이다
            assert isinstance(c, BooleanClauseList) and c.operator is operators.and_


def test_doc_scan_marker_negative_control(app, monkeypatch):
    """표시를 빼면 계약 테스트가 잡는다 — 구조가 같아도 표시 없는 and_ 는 가볍게 취급된다."""
    with app.app_context():
        monkeypatch.setattr(ep, "_mark_doc_scan_cond", lambda c: c)
        conds = build_mine_sql_filter(_U("표시도면", "mark_drawing", 7), scope="all")
        assert len(_heavy(conds)) == 0  # 위 계약(2개)과 어긋난다 = 누락이 드러난다
        assert not is_doc_scan_mine_cond(and_(Order.id == 1, Order.id == 2))


def test_hybrid_clause_shape(app):
    with app.app_context():
        conds = build_mine_sql_filter(_U("모양도면", "shape_drawing", 9), scope="all")
        scope = Order.is_erp_order.is_(True)
        clause = mine_membership_clause(conds, scope_conds=[scope])
        assert isinstance(clause, BooleanClauseList) and clause.operator is operators.or_
        parts = list(clause.clauses)
        heavy = _heavy(conds)
        assert parts[1:] == heavy and all(a is b for a, b in zip(parts[1:], heavy))
        sql = str(clause.compile())
        assert sql.count("FROM orders AS orders_mine") == len(conds) - len(heavy)
        # 기본값(None)은 예전 그대로: 모든 갈래 UNION, 범위 없음
        old = mine_membership_clause(conds)
        assert str(old.compile()).count("FROM orders AS orders_mine") == len(conds)
        assert mine_membership_clause([], scope_conds=[scope]) is None


_OR_MINE_RE = re.compile(r"or_\(\*\w*(mine|conds|conditions)\w*\)")
_SITES = [
    (cs_dashboard._apply_mine_filter, "query.whereclause"),
    (tower._tower_base_query, "q.whereclause"),
    (tower._mine_open_count, "scoped.whereclause"),
    (tower._apply_mine_only, "base.whereclause"),
    (dash_read_model, "_q.whereclause"),
    (production_read_model.build_production_orders_query, "_q.whereclause"),
    (construction_dashboard, "query.whereclause"),
    (as_dashboard, "base_query.whereclause"),
]


@pytest.mark.parametrize("obj,scope_expr", _SITES, ids=lambda x: getattr(x, "__name__", str(x)))
def test_scoped_sites_use_hybrid(obj, scope_expr):
    src = inspect.getsource(obj)
    assert not _OR_MINE_RE.search(src), "or_(*conds) 꼴이 남았다"
    assert f"scope_conds=[{scope_expr}]" in src


def test_mine_open_count_scope_includes_stage():
    src = inspect.getsource(tower._mine_open_count)
    assert src.index("notin_(_DONE_CODES)") < src.index("mine_membership_clause(")


def _user(name, team, role="STAFF"):
    u = User(username=f"scoped_{name}", password=generate_password_hash("x"), role=role, team=team, name=name, is_active=True)
    db_session.add(u)
    db_session.commit()
    return u


def _order(manager, status, **sd):
    return Order(received_date="2026-10-07", customer_name="C", phone="010-0000-0000", address="A",
                 product="P", status=status, is_erp_order=True, manager_name=manager, structured_data=sd)


def test_hybrid_ids_match_or_form(app):
    with app.app_context():
        users = [_user("범위영업", "SALES"), _user("범위시공", "CONSTRUCTION"), _user("범위도면", "DRAWING"),
                 _user("범위관리", "ADMIN", role="ADMIN"), _user("범위고객", "CS")]
        db_session.add_all([
            _order("범위영업", "MEASURE"),
            _order("범위영업", "COMPLETED"),  # 범위 밖 내 주문 — 빠져야 한다
            _order("다른사람", "MEASURE"),
            _order("다른사람", "CONSTRUCTION", shipment={"construction_workers": ["범위시공"]}),
            _order("다른사람", "DRAWING", assignments={"drawing_assignees": ["범위도면"]}),
            _order("다른사람", "DRAWING", drawing_assignees=["범위도면"]),  # 최상위 배정만(무거운 갈래)
            _order("다른사람", "COMPLETED", drawing_assignees=["범위도면"]),  # 범위 밖
            _order("범위관리", "MEASURE"),
        ])
        db_session.commit()
        checked = matched = 0
        for user in users:
            for scope in (None, "all", "sales", "construction", "drawing"):
                conds = build_mine_sql_filter(user, scope=scope)
                if not conds:
                    continue
                q = get_db().query(Order.id).filter(Order.status != "COMPLETED", Order.is_erp_order.is_(True))
                old = sorted(r[0] for r in q.filter(or_(*conds)).all())
                new = sorted(r[0] for r in q.filter(mine_membership_clause(conds, scope_conds=[q.whereclause])).all())
                assert new == old, f"{user.team}/{scope}: {new} != {old}"
                checked += 1
                matched += len(old)
        assert checked >= 8
        assert matched > 0, "음성만 비교했다"
