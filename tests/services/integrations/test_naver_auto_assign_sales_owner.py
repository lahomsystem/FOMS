"""수집 주문 담당자 자동 배정 계약 (2026-08-26).

배경: 현장은 워크벤치 '담당자 지정' 대신 ERP 상세의 주문담당자 칸에 이름을 타이핑한다.
그러면 화면엔 담당자가 있는데 배정 원장은 보류함(``naver_unassigned``) 그대로라, 취소·반품
알림이 담당자에게 가지 않았다.

고정하는 계약:

* 보류함이 owner 인 주문에 주문담당자 이름을 적으면 SALES owner 가 그 사람으로 바뀐다.
* 이름이 활성 사용자 **정확히 1명**과 맞을 때만 바꾼다 — 0명(오타·외부인)·2명 이상
  (동명이인)이면 아무것도 하지 않는다.
* 사람이 이미 owner 면 자동으로 갈아치우지 않는다(자유 텍스트로 실제 배정을 뺏지 않는다).
* 비활성 계정으로는 배정하지 않는다.
* 배정 전환은 ``SALES_ASSIGNEE_SET`` 이벤트로 원장에 남는다.

**보류함 → 사람 교체가 실제로 일어나는 경로는 이 레인에서 검증할 수 없다.** SQLite 는
``order_assignments`` 의 partial unique(active 행만)를 전체 unique 로 굳혀, 이력용
비활성 행이 남는 교체 자체가 IntegrityError 로 죽는다(원장 T10 레인 함정). 교체 계약은
:mod:`tests.postgres.test_naver_auto_assign_pg` 가 실 PostgreSQL 로 고정한다.
여기서는 **아무것도 하지 않아야 하는 경우**를 지킨다.
"""

from __future__ import annotations

from db import db_session
from foms.services.integrations.naver_commerce.auto_assign import (
    auto_assign_sales_owner_from_manager,
)
from foms.services.integrations.naver_commerce.constants import OWNER_USERNAME, SOURCE_MARKER
from models import Order, OrderAssignment, User

_SEQ = [0]


def _uid() -> str:
    _SEQ[0] += 1
    return f"auto-{_SEQ[0]}"


def _user(name: str, *, active: bool = True, username: str | None = None) -> User:
    user = User(username=username or _uid(), password="pw-not-committed", name=name,
                role="STAFF", team="SALES", is_active=active)
    db_session.add(user)
    db_session.commit()
    return user


def _sd(manager_name: str | None) -> dict:
    sd: dict = {"source": SOURCE_MARKER, "parties": {"customer": {"name": "테스트고객"}}}
    if manager_name is not None:
        sd["parties"]["manager"] = {"name": manager_name}
    return sd


def _order(sd: dict, *, owner: User | None) -> Order:
    order = Order(customer_name="테스트고객", phone="010-0000-0000", address="서울",
                  product="붙박이장", options="", received_date="2026-08-26",
                  status="RECEIVED", is_erp_order=True, structured_data=sd)
    db_session.add(order)
    db_session.commit()
    if owner is not None:
        db_session.add(OrderAssignment(order_id=order.id, domain="SALES", user_id=owner.id,
                                       source="INITIAL_OWNER", active=True,
                                       assigned_by_user_id=owner.id))
        db_session.commit()
    return order


def _active_owner_id(order_id: int) -> int | None:
    row = (db_session.query(OrderAssignment)
           .filter(OrderAssignment.order_id == order_id,
                   OrderAssignment.domain == "SALES",
                   OrderAssignment.active.is_(True))
           .first())
    return None if row is None else int(row.user_id)


def _run(order: Order, sd: dict, actor: User | None = None) -> int | None:
    result = auto_assign_sales_owner_from_manager(
        db_session, order_id=order.id, structured_data=sd,
        actor_user_id=None if actor is None else actor.id,
    )
    db_session.commit()
    return result


def test_unknown_name_changes_nothing(app):
    """일치하는 사용자가 없으면 배정은 그대로다(오타·외부 협력사 이름)."""
    holding = _user("미배정", username=OWNER_USERNAME)
    sd = _sd("없는사람")
    order = _order(sd, owner=holding)

    assert _run(order, sd) is None
    assert _active_owner_id(order.id) == holding.id


def test_duplicate_names_are_not_guessed(app):
    """동명이인이면 자동으로 고르지 않는다 — 잘못 고르면 남의 알림이 된다."""
    holding = _user("미배정", username=OWNER_USERNAME)
    _user("김철수")
    _user("김철수")
    sd = _sd("김철수")
    order = _order(sd, owner=holding)

    assert _run(order, sd) is None
    assert _active_owner_id(order.id) == holding.id


def test_inactive_user_is_not_assigned(app):
    """퇴사(비활성) 계정으로는 배정하지 않는다."""
    holding = _user("미배정", username=OWNER_USERNAME)
    _user("퇴사자", active=False)
    sd = _sd("퇴사자")
    order = _order(sd, owner=holding)

    assert _run(order, sd) is None
    assert _active_owner_id(order.id) == holding.id


def test_real_owner_is_never_replaced_automatically(app):
    """사람이 이미 owner 면 담당자 칸 글자만으로 뺏지 않는다."""
    _user("미배정", username=OWNER_USERNAME)
    current = _user("박영업")
    _user("강민경")
    sd = _sd("강민경")
    order = _order(sd, owner=current)

    assert _run(order, sd) is None
    assert _active_owner_id(order.id) == current.id


def test_blank_manager_name_does_nothing(app):
    """공백만 적힌 담당자는 배정 신호가 아니다."""
    holding = _user("미배정", username=OWNER_USERNAME)
    sd = _sd("   ")
    order = _order(sd, owner=holding)

    assert _run(order, sd) is None
    assert _active_owner_id(order.id) == holding.id
