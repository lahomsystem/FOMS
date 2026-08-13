"""NAVER-INGEST-01 T10 (PG 레인): 수집 주문 담당자 교체 계약.

**SQLite 레인에서는 성립하지 않는다.** SALES active-owner 유일성은 `postgresql_where`
부분 유니크라 SQLite create_all 에서는 predicate 없는 **전체 유니크**가 되어, 보류함 owner 를
실제 담당자로 교체하는 순간 UNIQUE 위반이 난다. 그래서 실 PostgreSQL 로만 고정한다.
"""

from __future__ import annotations

import hashlib
import json

import pytest
from sqlalchemy.orm import Session

from foms.services.integrations.naver_commerce.ingest import OWNER_USERNAME
from foms.services.orders.assignment import set_sales_assignee
from foms.services.orders.order_create import create_order
from models import Order, OrderAssignment, OrderEvent, User

_SEQ = [0]


def _uid() -> str:
    _SEQ[0] += 1
    return str(_SEQ[0])


def _user(session: Session, *, username: str, name: str) -> User:
    user = User(username=username, password="pw-not-committed", name=name,
                role="STAFF", team="SALES", is_active=True)
    session.add(user)
    session.flush()
    return user


def _ingested_order(session: Session, owner: User) -> Order:
    """수집 파이프라인이 만드는 모양의 주문(보류함 owner)."""
    order = create_order(
        session,
        actor_user_id=owner.id, owner_user_id=owner.id,
        order_fields=dict(received_date="2026-08-13", customer_name="이수취",
                          phone="010-3333-4444", address="서울 강남구 1 101호",
                          product="붙박이장", status="RECEIVED"),
        structured_data={"source": "NAVER_SMARTSTORE"},
        is_erp_order=True,
    )
    session.flush()
    return order


def _hashes(order_id: int, user_id: int) -> tuple[str, str]:
    """라우트와 같은 방식으로 scope/request 해시를 만든다."""
    scope = hashlib.sha256(f"SET_SALES_ASSIGNEE:{order_id}".encode("utf-8")).hexdigest()
    request = hashlib.sha256(
        json.dumps({"user_id": user_id}, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return (scope, request)


def test_holding_owner_is_replaced_by_the_real_assignee(pg_session: Session) -> None:
    """보류함 owner → 실제 담당자 교체 후 active SALES owner 는 정확히 1명이다."""
    holding = _user(pg_session, username=OWNER_USERNAME, name="미배정 (네이버 수집)")
    real = _user(pg_session, username=f"sales_{_uid()}", name="실제담당")
    order = _ingested_order(pg_session, holding)
    scope, request = _hashes(order.id, real.id)

    set_sales_assignee(
        pg_session, actor_user_id=real.id, order_id=order.id, user_id=real.id,
        reason="네이버 수집 주문 담당자 지정", scope_hash=scope, request_hash=request,
    )
    pg_session.commit()

    active = (pg_session.query(OrderAssignment)
              .filter(OrderAssignment.order_id == order.id,
                      OrderAssignment.domain == "SALES",
                      OrderAssignment.active.is_(True)).all())
    assert [row.user_id for row in active] == [real.id]


def test_replacement_emits_assignee_event_and_bumps_version(pg_session: Session) -> None:
    """canonical 엔진 경유의 증거 — 직접 row 를 만들면 이벤트도 version 도 안 생긴다."""
    holding = _user(pg_session, username=OWNER_USERNAME, name="미배정 (네이버 수집)")
    real = _user(pg_session, username=f"sales_{_uid()}", name="실제담당")
    order = _ingested_order(pg_session, holding)
    before = order.mutation_version
    scope, request = _hashes(order.id, real.id)

    set_sales_assignee(
        pg_session, actor_user_id=real.id, order_id=order.id, user_id=real.id,
        reason="네이버 수집 주문 담당자 지정", scope_hash=scope, request_hash=request,
    )
    pg_session.commit()

    events = [e.event_type for e in pg_session.query(OrderEvent)
              .filter(OrderEvent.order_id == order.id).all()]
    assert "SALES_ASSIGNEE_SET" in events
    pg_session.refresh(order)
    assert order.mutation_version > before


def test_replacement_requires_a_reason(pg_session: Session) -> None:
    """보류함에서 옮기는 것도 **교체**라 사유가 필수다 — 화면이 안 보내면 서버가 채워야 한다."""
    holding = _user(pg_session, username=OWNER_USERNAME, name="미배정 (네이버 수집)")
    real = _user(pg_session, username=f"sales_{_uid()}", name="실제담당")
    order = _ingested_order(pg_session, holding)
    scope, request = _hashes(order.id, real.id)

    with pytest.raises(Exception):
        set_sales_assignee(
            pg_session, actor_user_id=real.id, order_id=order.id, user_id=real.id,
            reason=None, scope_hash=scope, request_hash=request,
        )
    pg_session.rollback()
