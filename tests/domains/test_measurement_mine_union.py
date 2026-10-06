"""실측 화면 "내 주문" 조건 — 배지와 같은 UNION 멤버십 계약.

설계서 docs/specs/2026-10-06-nav-badge-count-query_SPEC.md §8.
실측 목록(대시보드·패널·보조 조회·미정 목록)은 ``build_mine_sql_filter`` 조건을
``or_(*conds)`` 대신 ``mine_membership_clause`` 로 묶는다.

1. 모양: 실측 경로 소스에 ``or_(*..mine..)`` 꼴이 남지 않고, 헬퍼 SQL 에 ``orders_mine``
   갈래가 조건 수만큼 있다. 배지도 같은 헬퍼를 쓴다(정의 한 곳).
2. 동일성: 같은 사용자·주문에서 옛 OR 꼴과 주문 번호 집합이 같다.
3. 빈 조건: 헬퍼는 None — 실측 호출부는 필터를 걸지 않는다(기존 의미).
"""
from __future__ import annotations

import inspect
import re

from sqlalchemy import or_
from sqlalchemy.dialects import postgresql
from werkzeug.security import generate_password_hash

import foms.services.dashboard_counts as dashboard_counts
import foms.services.measurement_read_model as read_model
import foms.services.measurement_undated as undated
import foms.web.measurement.dashboard as meas_dashboard
from db import db_session, get_db
from foms.services.erp_permissions import build_mine_sql_filter, mine_membership_clause
from models import Order, User

_OR_MINE_RE = re.compile(r"or_\(\*\w*(mine|conds)\w*\)")


def _user(name: str, team: str) -> User:
    user = User(
        username=f"meas_union_{name}",
        password=generate_password_hash("x"),
        role="STAFF",
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


def test_measurement_paths_use_membership_clause():
    for mod in (meas_dashboard, read_model, undated):
        src = inspect.getsource(mod)
        assert not _OR_MINE_RE.search(src), f"{mod.__name__}: or_(*mine) 꼴이 남았다"
        assert "mine_membership_clause(build_mine_sql_filter(" in src, mod.__name__
    assert "mine_membership_clause(" in inspect.getsource(dashboard_counts._apply_mine_filter)


def test_membership_clause_shape_on_postgresql(app):
    with app.app_context():
        sales = _user("모양영업", "SALES")
        conds = build_mine_sql_filter(sales)
        assert conds
        q = get_db().query(Order.id).filter(mine_membership_clause(conds))
        sql = str(q.statement.compile(dialect=postgresql.dialect()))
        assert sql.count("FROM orders AS orders_mine") == len(conds)
        outer_where = sql.split("WHERE", 1)[1].split("orders.id IN", 1)[0]
        assert "orders.structured_data" not in outer_where


def test_membership_clause_empty_is_none():
    assert mine_membership_clause([]) is None


def test_membership_ids_match_or_form(app):
    with app.app_context():
        users = [
            _user("동일영업", "SALES"),
            _user("동일시공", "CONSTRUCTION"),
            _user("동일실측", "MEASURE"),
            _user("동일도면", "DRAWING"),
        ]
        db_session.add_all(
            [
                _order("동일영업", "MEASURE"),
                _order("동일실측", "MEASURE"),
                _order("다른사람", "MEASURE"),
                _order("다른사람", "CONSTRUCTION", shipment={"construction_workers": ["동일시공"]}),
                _order("동일시공", "CS"),
                _order("다른사람", "DRAWING", assignments={"drawing_assignees": ["동일도면"]}),
            ]
        )
        db_session.commit()
        checked = 0
        matched = 0
        for user in users:
            conds = build_mine_sql_filter(user)
            if not conds:
                continue
            base = get_db().query(Order.id)
            old = sorted(r[0] for r in base.filter(or_(*conds)).all())
            new = sorted(r[0] for r in base.filter(mine_membership_clause(conds)).all())
            assert new == old, f"{user.team}: {new} != {old}"
            checked += 1
            matched += len(old)
        assert checked >= 3
        assert matched > 0, "음성만 비교했다 — 매칭 주문이 하나도 없다"
