"""nav 배지 "내 주문" 조건 — 갈래별 번호 목록 UNION 계약.

설계서 docs/specs/2026-10-06-nav-badge-count-query_SPEC.md.
OR 하나로 묶은 조건은 PostgreSQL 이 trgm 인덱스를 못 써 운영 평균 696ms 였다.
``_apply_mine_filter`` 는 조건마다 별칭 ``orders_mine`` 에서 id 를 뽑아 UNION 한다.

1. 모양: 그린 SQL 에 ``orders_mine`` 갈래가 조건 수만큼 있고, 바깥 ``orders`` 의
   ``structured_data`` 는 WHERE 에서 읽지 않는다(상관 없음).
2. 동일성: 같은 사용자·주문에 대해 옛 OR 꼴과 상태별 개수가 같다(팀 섞어서).
"""
from __future__ import annotations

from sqlalchemy import func, or_
from sqlalchemy.dialects import postgresql
from werkzeug.security import generate_password_hash

from db import db_session, get_db
from foms.services.dashboard_counts import _apply_mine_filter
from foms.services.erp_permissions import build_mine_sql_filter
from models import Order, User


def _user(name: str, team: str) -> User:
    user = User(
        username=f"badge_union_{name}",
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


def _base():
    return get_db().query(Order.status, func.count(Order.id)).filter(
        Order.active_filter(), Order.is_erp_order.is_(True)
    )


def _counts(query) -> dict[str, int]:
    return dict(query.group_by(Order.status).all())


def test_union_shape_on_postgresql(app):
    with app.app_context():
        sales = _user("모양영업", "SALES")
        conds = build_mine_sql_filter(sales)
        assert conds, "영업 사용자 조건이 비었다 — 계약 전제가 깨졌다"
        sql = str(
            _apply_mine_filter(_base(), sales)
            .group_by(Order.status)
            .statement.compile(dialect=postgresql.dialect())
        )
        assert sql.count("FROM orders AS orders_mine") == len(conds)
        assert " UNION " in sql or len(conds) == 1
        outer_where = sql.split("WHERE", 1)[1].split("orders.id IN", 1)[0]
        assert "orders.structured_data" not in outer_where.replace(
            "orders_mine.structured_data", ""
        )


def test_union_counts_match_or_form(app):
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
                _order("동일영업", "RECEIVED"),
                _order("다른사람", "MEASURE"),
                _order("다른사람", "CONSTRUCTION", construction={"crew": "동일시공"}),
                _order("동일시공", "CS"),
                _order("다른사람", "DRAWING", drawing={"assignee": "동일도면"}),
            ]
        )
        db_session.commit()
        for user in users:
            conds = build_mine_sql_filter(user)
            if not conds:
                continue
            old = _counts(_base().filter(or_(*conds)))
            new = _counts(_apply_mine_filter(_base(), user))
            assert new == old, f"{user.team}: {new} != {old}"
