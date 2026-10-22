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


@pytest.mark.parametrize("scope", ["all", "drawing", "sales", "construction"])
def test_no_full_document_scan_conds(app, scope):
    """mine 조건에 문서 전체 ILIKE 가 없다 — 영업 이름이 거의 모든 문서에 있어 행마다 문서를 풀었다
    (2026-10-22 운영 ADMIN 질의 220ms). 최상위 drawing_assignees 는 칸 조건 하나로 본다."""
    with app.app_context():
        conds = build_mine_sql_filter(_U("표시도면", "mark_drawing", 7), scope=scope)
        assert _heavy(conds) == []
        for c in conds:
            sql = str(c.compile(compile_kwargs={"literal_binds": True}))
            assert "CAST(orders.structured_data AS" not in sql, sql


def test_toplevel_drawing_assignees_still_matched(app):
    """음성 대조군: 최상위 배정만 있는 주문도 도면 범위로 잡힌다(문서 스캔을 뺀 뒤에도)."""
    with app.app_context():
        conds = build_mine_sql_filter(_U("최상위도면", "top_drawing", 8), scope="drawing")
        sql = " ".join(str(c.compile(compile_kwargs={"literal_binds": True})) for c in conds)
        assert "drawing_assignees" in sql and "최상위도면" in sql


def test_hybrid_clause_shape(app):
    """HYBRID 기반은 남아 있다 — 표시된 무거운 조건은 바깥 OR, 나머지는 범위 넣은 UNION."""
    with app.app_context():
        conds = build_mine_sql_filter(_U("모양도면", "shape_drawing", 9), scope="all")
        marked = ep._mark_doc_scan_cond(and_(Order.id > 0, Order.notes.ilike("%모양%")))
        all_conds = conds + [marked]
        scope = Order.is_erp_order.is_(True)
        clause = mine_membership_clause(all_conds, scope_conds=[scope])
        assert isinstance(clause, BooleanClauseList) and clause.operator is operators.or_
        parts = list(clause.clauses)
        assert len(parts) == 2 and parts[1] is marked
        sql = str(clause.compile())
        assert sql.count("FROM orders AS orders_mine") == len(conds)
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


def test_tower_mine_on_does_not_reapply_mine_clause(app):
    """mine 켠 타워의 '내 담당 진행중' 은 이미 걸러진 base 를 그대로 센다.

    같은 mine 절을 두 번 걸면 첫 절이 범위로 갈래마다 복제돼(ADMIN all 범위) 질의 하나가 4.4초가 됐다
    (2026-10-20 스테이징). 개수는 mine 끈 타워와 같아야 하고, 어떤 SQL 도 mine 갈래를 한 벌 넘게 품지 않는다.
    """
    from sqlalchemy import event

    from foms.services.datetime_kst import get_today_kst

    with app.app_context():
        admin = _user("타워관리", "ADMIN", role="ADMIN")
        today = get_today_kst().isoformat()
        rows = [_order("타워관리", "MEASURE"), _order("타워관리", "DRAWING"), _order("타워관리", "COMPLETED"),
                _order("다른사람", "MEASURE")]
        rows[2].erp_stage_code = "COMPLETED"
        for o in rows:
            o.received_date = today
        db_session.add_all(rows)
        db_session.commit()

        light = [c for c in build_mine_sql_filter(admin) if not is_doc_scan_mine_cond(c)]
        statements: list[str] = []
        engine = db_session.get_bind()

        def _capture(conn, cursor, statement, params, context, executemany):
            statements.append(statement)

        off = tower.build_mobile_control_tower(db_session, admin, mine_only=False)
        event.listen(engine, "before_cursor_execute", _capture)
        try:
            on = tower.build_mobile_control_tower(db_session, admin, mine_only=True)
        finally:
            event.remove(engine, "before_cursor_execute", _capture)

        assert off["mine_open_count"] == 2
        assert on["mine_open_count"] == off["mine_open_count"]
        assert statements, "SQL 을 못 잡았다"
        worst = max(s.count("FROM orders AS orders_mine") for s in statements)
        assert worst <= len(light), f"mine 갈래가 겹쳐 들어갔다: {worst} > {len(light)}"
        # mine 절은 주문 번호를 구하는 질의 한 번만 푼다(나머지 질의는 번호 목록을 쓴다)
        assert sum("FROM orders AS orders_mine" in s for s in statements) == 1


def test_tower_mine_ids_materialized_same_payload(app, monkeypatch):
    """번호 목록으로 바꾼 mine base 가 mine 절을 그대로 건 base 와 같은 타워를 낸다."""
    from foms.services.datetime_kst import get_today_kst

    with app.app_context():
        admin = _user("목록관리", "ADMIN", role="ADMIN")
        drawer = _user("목록도면", "DRAWING")
        today = get_today_kst().isoformat()
        rows = [_order("목록관리", "MEASURE"), _order("목록관리", "CONSTRUCTION"), _order("다른사람", "MEASURE"),
                _order("다른사람", "DRAWING", drawing_assignees=["목록도면"]),
                _order("다른사람", "DRAWING", assignments={"drawing_assignees": ["목록도면"]})]
        for o in rows:
            o.received_date = today
        db_session.add_all(rows)
        db_session.commit()

        def _clause_only(base, current_user):
            conds = build_mine_sql_filter(current_user)
            return base.filter(mine_membership_clause(conds, scope_conds=[base.whereclause])) if conds else base

        for user in (admin, drawer):
            new = tower.build_mobile_control_tower(db_session, user, mine_only=True)
            with monkeypatch.context() as m:
                m.setattr(tower, "_apply_mine_only", _clause_only)
                old = tower.build_mobile_control_tower(db_session, user, mine_only=True)
            assert new == old
            assert new["mine_open_count"] >= 1, "음성만 비교했다"
        # 내 주문이 없으면 빈 타워(번호 목록이 비면 false)
        nobody = _user("목록없음", "SALES")
        empty = tower.build_mobile_control_tower(db_session, nobody, mine_only=True)
        assert empty["mine_open_count"] == 0 and empty["today_count"] == 0
