"""주문 ↔ 프리랜서 연결 표 — 실제 PostgreSQL 에서만 잴 수 있는 것(FCOMM-01 T13 · PGTEST-00 lane).

1. 주문 하드 삭제 → 연결 줄도 같이 지워진다(``ON DELETE CASCADE`` — 삭제 보존 FK 검사와 같은 뜻).
2. 관계 CHECK · (주문, 사람, 관계) UNIQUE 가 PG 에서 막는다.
3. 일괄 맞추기(:func:`sync_links_for_orders`)가 SQL 투영 길(PostgreSQL 16+ — 이름 칸만 줄여 읽기)에서도
   SQLite 레인과 같은 연결을 만들고, 두 번 돌려도 같다.

``FOMS_TEST_DATABASE_URL`` 미설정이면 lane 자체가 skip 된다(conftest). 이름은 모두 가짜 값이다.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from foms.services.sales_commission.links import (
    REL_MANAGER,
    REL_MANAGER_PRIMARY,
    REL_ORDERER,
    sync_links_for_orders,
)
from foms.services.sales_commission.settings import save_freelancer
from models import Order, OrderFreelancerLink, User


def _user(session, username: str) -> int:
    user = User(username=username, password="x", role="STAFF", team="SALES", name=f"{username}-name",
                is_active=True)
    session.add(user)
    session.flush()
    return user.id


def _order(session, manager: str = "", names=None, orderer: str = "") -> int:
    manager_party: dict = {"name": manager}
    if names:
        manager_party["names"] = list(names)
    sd = {"parties": {"manager": manager_party, "orderer": {"name": orderer}, "customer": {"name": "가짜손님"}},
          "items": [{"product_name": "가짜장", "price": 1}], "quests": {"big": "읽지 않는 칸"}}
    order = Order(received_date="2026-11-06", customer_name="FCOMM-LINK-PG", phone="010-0000-0000",
                  address="가짜시", product="가짜장", status="RECEIVED", is_erp_order=True, structured_data=sd)
    session.add(order)
    session.flush()
    return order.id


def _links(session, order_id: int) -> set[tuple[int, str]]:
    rows = session.execute(text("SELECT user_id, relation FROM order_freelancer_links WHERE order_id = :o"),
                           {"o": order_id}).all()
    return {(int(u), str(r)) for u, r in rows}


def test_hard_delete_cascades_links(pg_session):
    uid = _user(pg_session, "fcomm_pg_u1")
    oid = _order(pg_session)
    pg_session.add(OrderFreelancerLink(order_id=oid, user_id=uid, relation=REL_MANAGER))
    pg_session.flush()
    assert _links(pg_session, oid) == {(uid, REL_MANAGER)}
    pg_session.execute(text("DELETE FROM orders WHERE id = :o"), {"o": oid})
    assert _links(pg_session, oid) == set()


def test_relation_check_and_unique(pg_session):
    uid = _user(pg_session, "fcomm_pg_u2")
    oid = _order(pg_session)
    pg_session.add(OrderFreelancerLink(order_id=oid, user_id=uid, relation=REL_MANAGER))
    pg_session.flush()
    nested = pg_session.begin_nested()
    pg_session.add(OrderFreelancerLink(order_id=oid, user_id=uid, relation=REL_MANAGER))
    with pytest.raises(IntegrityError):
        pg_session.flush()
    nested.rollback()
    nested = pg_session.begin_nested()
    pg_session.add(OrderFreelancerLink(order_id=oid, user_id=uid, relation="BOSS"))
    with pytest.raises(IntegrityError):
        pg_session.flush()
    nested.rollback()


def test_sync_on_sql_projection_matches_rules_and_is_idempotent(pg_session):
    first_order = _order(pg_session, "가짜프리", names=["가짜프리", "다른가짜"], orderer="다른가짜")
    second_order = _order(pg_session, "일반직원")
    f1, f2 = _user(pg_session, "fcomm_pg_f1"), _user(pg_session, "fcomm_pg_f2")
    version = 0
    for uid, name in ((f1, "가짜프리"), (f2, "다른가짜")):
        version, _cfg, _changed = save_freelancer(
            pg_session, uid, {"match_name": name, "start_month": "2026-01", "tax_type": "NONE", "active": True},
            base_version=version, actor_user_id=None)
    pg_session.add(OrderFreelancerLink(order_id=second_order, user_id=f1, relation=REL_MANAGER))  # 낡은 줄
    pg_session.flush()

    stats = sync_links_for_orders(pg_session, [first_order, second_order])
    assert (stats["orders"], stats["removed"]) == (2, 1)
    assert _links(pg_session, first_order) == {(f1, REL_MANAGER_PRIMARY), (f2, REL_MANAGER), (f2, REL_ORDERER)}
    assert _links(pg_session, second_order) == set()
    again = sync_links_for_orders(pg_session, [first_order, second_order])
    assert (again["added"], again["removed"]) == (0, 0)
