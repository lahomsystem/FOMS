"""PARTNER-04 (PG 레인): 협력사 주문 담당 바꾸기 — 실제 교체 계약.

SQLite 레인은 ``order_assignments`` 부분 유니크(active 행만)를 전체 유니크로 굳혀, 이력용 비활성 행이
남는 교체 자체가 IntegrityError 로 죽는다. 그래서 교체 성공 경로는 실 PostgreSQL 로만 고정한다
(거부 경로는 :mod:`tests.security.test_partner_manager`).

1. 같은 회사 직원으로 바꾸면 그 직원이 active SALES owner 가 되고, 앞 담당은 비활성 이력으로 남는다.
2. 담당 칸(이름 · 연락처) · ``orders.manager_name`` · 담당이던 사람의 quest ``owner_person`` 이 함께 바뀐다.
3. 바꾼 뒤 앞 담당이 연락처를 바꿔도 이 주문은 안 바뀐다(새 담당 몫).
"""

from __future__ import annotations

import time

from sqlalchemy.orm import Session

from foms.services.partners.manager import change_partner_order_manager, set_partner_user_phone
from foms.services.partners.orders import create_partner_order
from models import OrderAssignment, PartnerOrg, User


def _suffix() -> str:
    return str(int(time.time() * 1_000_000) % 10_000_000)


def _partner(session: Session, org: PartnerOrg, name: str, phone: str) -> User:
    user = User(username=f"pm-{_suffix()}", password="pw-not-committed", name=name, role="PARTNER",
                team=None, is_active=True, partner_org_id=org.id, contact_phone=phone)
    session.add(user)
    session.flush()
    return user


def test_partner_manager_change_replaces_sales_owner(pg_session: Session) -> None:
    org = PartnerOrg(name=f"가나가구-{_suffix()}")
    pg_session.add(org)
    pg_session.flush()
    first = _partner(pg_session, org, "가나 직원", "010-1111-2222")
    second = _partner(pg_session, org, "가나 둘째", "010-3333-4444")
    order = create_partner_order(pg_session, first, org, {
        "customer_name": "홍길동", "customer_phone": "010-0000-0000", "address": "서울 1",
        "items": [{"product_name": "붙박이장"}],
    })
    pg_session.flush()

    change_partner_order_manager(pg_session, first, order.id, second.id)
    pg_session.flush()
    pg_session.expire_all()

    rows = (pg_session.query(OrderAssignment)
            .filter(OrderAssignment.order_id == order.id, OrderAssignment.domain == "SALES")
            .order_by(OrderAssignment.id).all())
    assert [(r.user_id, r.active) for r in rows] == [(first.id, False), (second.id, True)]
    sd = order.structured_data
    assert sd["parties"]["manager"]["name"] == f"가나 둘째 ({org.name})"
    assert sd["parties"]["manager"]["phone"] == "010-3333-4444"
    assert order.manager_name == f"가나 둘째 ({org.name})"
    quest = next(q for q in sd["quests"] if q.get("stage") == "MEASURE")
    assert quest["owner_person"] == str(second.id)

    assert set_partner_user_phone(pg_session, first, "010-5555-6666", actor_user_id=first.id) == 0
    assert set_partner_user_phone(pg_session, second, "010-7777-8888", actor_user_id=second.id) == 1
    pg_session.flush()
    pg_session.expire_all()
    assert order.structured_data["parties"]["manager"]["phone"] == "010-7777-8888"


def test_backfill_moves_old_partner_orders_to_submitter(pg_session: Session) -> None:
    """옛 규칙(우리 영업 직원이 담당)으로 만든 주문을 백필이 등록한 협력사 직원으로 옮긴다."""
    from tools.ops.backfill_partner_order_manager import backfill

    staff = User(username=f"pm-sales-{_suffix()}", password="pw-not-committed", name="영업김",
                 role="STAFF", team="SALES", is_active=True)
    pg_session.add(staff)
    org = PartnerOrg(name=f"다라가구-{_suffix()}")
    pg_session.add(org)
    pg_session.flush()
    submitter = _partner(pg_session, org, "다라 직원", "010-2222-3333")
    order = create_partner_order(pg_session, submitter, org, {
        "customer_name": "홍길동", "customer_phone": "010-0000-0000", "address": "서울 1",
        "items": [{"product_name": "붙박이장"}],
    })
    pg_session.flush()
    # 옛 모양으로 되돌린다: SALES = 우리 직원, 담당 칸 = 직원 이름.
    row = pg_session.query(OrderAssignment).filter(OrderAssignment.order_id == order.id).one()
    row.user_id = staff.id
    sd = dict(order.structured_data)
    sd["parties"] = {**sd["parties"], "manager": {"name": "영업김"}}
    order.structured_data = sd
    pg_session.flush()

    dry = backfill(pg_session, apply=False)
    mine = [r for r in dry["rows"] if r["order_id"] == order.id]
    assert mine and mine[0]["verdict"] == "CHANGE"

    backfill(pg_session, apply=True)
    pg_session.expire_all()
    active = (pg_session.query(OrderAssignment.user_id)
              .filter(OrderAssignment.order_id == order.id, OrderAssignment.active.is_(True)).scalar())
    assert active == submitter.id
    assert order.structured_data["parties"]["manager"]["phone"] == "010-2222-3333"
    again = backfill(pg_session, apply=False)
    assert [r["verdict"] for r in again["rows"] if r["order_id"] == order.id] == ["ALREADY_OK"]
