"""수집 주문 담당자 자동 배정 — 실 PostgreSQL 교체 계약 (PGTEST-00 lane).

SQLite 도메인 레인(:mod:`tests.services.integrations.test_naver_auto_assign_sales_owner`)은
"아무것도 하지 않아야 하는 경우"까지만 지킨다. 보류함(``naver_unassigned``) → 사람으로
**실제로 교체되는 경로**는 SQLite 에서 검증 자체가 불가능하다 — partial unique(active 행만)가
전체 unique 로 굳어, 이력용 비활성 행이 남는 순간 IntegrityError 로 죽기 때문이다.

여기서 고정하는 것:

1. 보류함이 owner 인 주문에 주문담당자 이름을 적으면 **그 사람이 active owner** 가 된다.
2. 보류함 행은 지워지지 않고 ``active=False`` 이력으로 남는다.
3. 교체는 ``SALES_ASSIGNEE_SET`` 이벤트로 원장에 남고, 사유가 자동 배정임을 밝힌다.
4. 주문당 active SALES 는 여전히 1명이다(partial unique 가 실제로 강제된다).
"""

from __future__ import annotations

import time

from sqlalchemy.orm import sessionmaker

from foms.services.integrations.naver_commerce.auto_assign import (
    AUTO_ASSIGN_REASON,
    auto_assign_sales_owner_from_manager,
)
from foms.services.integrations.naver_commerce.constants import OWNER_USERNAME, SOURCE_MARKER
from models import Order, OrderAssignment, OrderEvent, User

_SEQ = [0]


def _suffix() -> str:
    _SEQ[0] += 1
    return f"{_SEQ[0]}_{int(time.time() * 1000) % 100000}"


def _session(pg_engine):
    return sessionmaker(bind=pg_engine)()


def _user(session, name: str, *, username: str | None = None) -> User:
    user = User(username=username or f"auto-{_suffix()}", password="pw-not-committed",
                name=name, role="STAFF", team="SALES", is_active=True)
    session.add(user)
    session.commit()
    return user


def _holdbox(session) -> User:
    """보류함 계정 get-or-create — PG 레인은 모듈 안에서 데이터가 이어진다."""
    found = session.query(User).filter(User.username == OWNER_USERNAME).first()
    return found if found is not None else _user(session, "미배정", username=OWNER_USERNAME)


def _sd(manager_name: str | None) -> dict:
    sd: dict = {"source": SOURCE_MARKER, "parties": {"customer": {"name": "테스트고객"}}}
    if manager_name is not None:
        sd["parties"]["manager"] = {"name": manager_name}
    return sd


def _order_owned_by(session, owner: User, sd: dict) -> Order:
    order = Order(customer_name="테스트고객", phone="010-0000-0000", address="서울",
                  product="붙박이장", options="", received_date="2026-08-26",
                  status="RECEIVED", is_erp_order=True, structured_data=sd)
    session.add(order)
    session.commit()
    session.add(OrderAssignment(order_id=order.id, domain="SALES", user_id=owner.id,
                                source="INITIAL_OWNER", active=True,
                                assigned_by_user_id=owner.id))
    session.commit()
    return order


def _sales_rows(session, order_id: int) -> list[OrderAssignment]:
    return (session.query(OrderAssignment)
            .filter(OrderAssignment.order_id == order_id,
                    OrderAssignment.domain == "SALES")
            .order_by(OrderAssignment.id)
            .all())


def test_holdbox_is_replaced_by_the_typed_manager(pg_engine):
    """이름 한 줄이 배정 원장을 사람으로 옮긴다 — 취소 알림이 담당자에게 가는 조건."""
    session = _session(pg_engine)
    holding = _holdbox(session)
    sales = _user(session, f"강민경{_suffix()}")
    sd = _sd(sales.name)
    order = _order_owned_by(session, holding, sd)

    assigned = auto_assign_sales_owner_from_manager(
        session, order_id=order.id, structured_data=sd, actor_user_id=sales.id,
    )
    session.commit()

    assert assigned == sales.id
    rows = _sales_rows(session, order.id)
    active = [r for r in rows if r.active]
    released = [r for r in rows if not r.active]
    # active owner 는 정확히 1명(partial unique 계약)이고 그 사람이 담당자다.
    assert len(active) == 1 and int(active[0].user_id) == sales.id
    # 보류함 행은 이력으로 남는다 — 지우면 "언제까지 주인이 없었는지"를 잃는다.
    assert len(released) == 1 and int(released[0].user_id) == holding.id
    assert released[0].release_reason == AUTO_ASSIGN_REASON

    events = (session.query(OrderEvent)
              .filter(OrderEvent.order_id == order.id,
                      OrderEvent.event_type == "SALES_ASSIGNEE_SET")
              .all())
    assert len(events) == 1
    assert events[0].payload["user_id"] == sales.id
    assert events[0].payload["reason"] == AUTO_ASSIGN_REASON
    session.close()


def test_second_save_with_the_same_name_is_a_no_op(pg_engine):
    """이미 그 사람이 owner 면 저장할 때마다 배정 이벤트를 새로 쌓지 않는다."""
    session = _session(pg_engine)
    holding = _holdbox(session)
    sales = _user(session, f"강민경{_suffix()}")
    sd = _sd(sales.name)
    order = _order_owned_by(session, holding, sd)

    auto_assign_sales_owner_from_manager(
        session, order_id=order.id, structured_data=sd, actor_user_id=sales.id)
    session.commit()
    again = auto_assign_sales_owner_from_manager(
        session, order_id=order.id, structured_data=sd, actor_user_id=sales.id)
    session.commit()

    assert again is None, "사람이 owner 인 뒤에는 자동 배정이 다시 개입하면 안 된다"
    events = (session.query(OrderEvent)
              .filter(OrderEvent.order_id == order.id,
                      OrderEvent.event_type == "SALES_ASSIGNEE_SET")
              .all())
    assert len(events) == 1
    session.close()


def test_claim_notification_reaches_the_auto_assigned_owner(pg_engine):
    """자동 배정 뒤에는 취소 알림 수신자에 담당자가 들어온다(이 기능의 목적)."""
    from foms.services.integrations.naver_commerce.claim_watch import _notify_targets
    from models import ExternalOrderLink

    session = _session(pg_engine)
    holding = _holdbox(session)
    sales = _user(session, f"강민경{_suffix()}")
    admin = User(username=f"admin-{_suffix()}", password="pw-not-committed", name="관리자",
                 role="ADMIN", team="CS", is_active=True)
    session.add(admin)
    session.commit()
    sd = _sd(sales.name)
    order = _order_owned_by(session, holding, sd)
    link = ExternalOrderLink(channel="NAVER", external_id=f"PO-{_suffix()}",
                             sync_status="COLLECTED", order_id=order.id, raw_snapshot={})
    session.add(link)
    session.commit()

    before_holders, before_admins = _notify_targets(session, link)
    assert before_holders == [] and admin.id in before_admins

    auto_assign_sales_owner_from_manager(
        session, order_id=order.id, structured_data=sd, actor_user_id=sales.id)
    session.commit()

    after_holders, after_admins = _notify_targets(session, link)
    assert after_holders == [sales.id]
    assert admin.id in after_admins
    session.close()
