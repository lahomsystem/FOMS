"""ORDER-CREATE-01 PostgreSQL 계약 테스트 (PGTEST-00 lane).

canonical Order 생성자의 **원자 조립**(item identity·RECEIVED quest·mutation_version=1·
SALES owner 배정·ORDER_CREATED event·GEOCODE outbox 를 한 tx)과 **owner 정책**(STAFF self
default / Admin explicit active SALES / admin·타 STAFF 명의 금지), 그리고 실 PostgreSQL
partial unique 가 강제하는 **SALES 단일 owner**·부분 실패 롤백을 실 DB 다중 커밋으로 고정한다.

``FOMS_TEST_DATABASE_URL`` 미설정이면 lane 자체가 skip 된다(conftest). 커밋 파일에는
비밀번호를 넣지 않는다(env 로 주입). 이 DSN 이 없는 환경에서는 SQLite service 증거
``tests/domains/test_order_create_service.py`` 가 서비스 로직을 green 으로 증명한다.
"""
from __future__ import annotations

import time

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from foms.services.orders.order_create import (
    OwnerPolicyError,
    create_order,
    resolve_order_owner,
)
from models import (
    DomainSideEffectOutbox,
    Order,
    OrderAssignment,
    OrderEvent,
    OrderItemIdentity,
    User,
)

_SEQ = [0]


def _session(pg_engine):
    return sessionmaker(bind=pg_engine)()


def _sfx() -> str:
    _SEQ[0] += 1
    return f"{_SEQ[0]}_{int(time.time() * 1000) % 1000000}"


def _user(session, *, role="STAFF", team="SALES", is_active=True) -> User:
    u = User(
        username=f"ocpg_{_sfx()}",
        password="pw-not-committed",
        name=f"{role}_{team}",
        role=role,
        team=team,
        is_active=is_active,
    )
    session.add(u)
    session.commit()
    return u


def _erp_sd() -> dict:
    return {
        "parties": {"customer": {"name": "홍길동", "phone": "010-1234-5678"}},
        "site": {"address_full": "서울시 강남구 1"},
        "items": [
            {"product_name": "붙박이장", "price": 1000000},
            {"product_name": "수납장", "price": 500000},
        ],
    }


# --------------------------------------------------------------------------- #
# 원자 조립
# --------------------------------------------------------------------------- #
def test_erp_create_is_atomic(pg_engine):
    s = _session(pg_engine)
    try:
        staff = _user(s, role="STAFF", team="SALES")
        order = create_order(
            s,
            actor_user_id=staff.id,
            owner_user_id=staff.id,
            order_fields=dict(
                received_date="2026-07-24", customer_name="홍길동",
                phone="010-1234-5678", address="서울시 강남구 1", product="붙박이장",
                status="RECEIVED",
            ),
            structured_data=_erp_sd(),
            is_erp_order=True,
        )
        s.commit()

        assert order.mutation_version == 1
        quests = (order.structured_data or {}).get("quests")
        assert isinstance(quests, list) and any(q.get("stage") == "RECEIVED" for q in quests)
        assert s.query(OrderItemIdentity).filter_by(order_id=order.id, is_active=True).count() == 2
        owners = s.query(OrderAssignment).filter_by(order_id=order.id, domain="SALES", active=True).all()
        assert len(owners) == 1 and owners[0].user_id == staff.id and owners[0].source == "INITIAL_OWNER"
        assert s.query(OrderEvent).filter_by(order_id=order.id, event_type="ORDER_CREATED").count() == 1
        outbox = s.query(DomainSideEffectOutbox).filter_by(effect_type="GEOCODE").all()
        assert len(outbox) == 1 and outbox[0].status == "PENDING"
    finally:
        s.close()


def test_partial_failure_rolls_back(pg_engine, monkeypatch):
    s = _session(pg_engine)
    try:
        staff = _user(s, role="STAFF", team="SALES")
        before = s.query(Order).count()

        import foms.services.orders.order_create as oc

        def _boom(*_a, **_k):
            raise RuntimeError("identity mint failed")

        monkeypatch.setattr(oc, "get_or_create_identity", _boom)
        with pytest.raises(RuntimeError):
            create_order(
                s,
                actor_user_id=staff.id,
                owner_user_id=staff.id,
                order_fields=dict(
                    received_date="2026-07-24", customer_name="롤백",
                    phone="010-1111-2222", address="서울시 3", product="붙박이장",
                    status="RECEIVED",
                ),
                structured_data=_erp_sd(),
                is_erp_order=True,
            )
        s.rollback()
        assert s.query(Order).count() == before
    finally:
        s.close()


def test_sales_single_owner_partial_unique_enforced(pg_engine):
    """생성자가 만든 SALES owner 위에 두 번째 active SALES 배정은 DB 가 거부한다."""
    s = _session(pg_engine)
    try:
        staff = _user(s, role="STAFF", team="SALES")
        other = _user(s, role="STAFF", team="SALES")
        order = create_order(
            s,
            actor_user_id=staff.id,
            owner_user_id=staff.id,
            order_fields=dict(
                received_date="2026-07-24", customer_name="단일owner",
                phone="010-1234-5678", address="서울시 4", product="침대",
                status="RECEIVED",
            ),
            is_erp_order=False,
        )
        s.commit()
        s.add(OrderAssignment(
            order_id=order.id, domain="SALES", user_id=other.id,
            source="TEAM_REPLACE", active=True, assigned_by_user_id=staff.id,
        ))
        with pytest.raises(IntegrityError):
            s.commit()
        s.rollback()
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# owner 정책
# --------------------------------------------------------------------------- #
def test_owner_staff_self_default(pg_engine):
    s = _session(pg_engine)
    try:
        staff = _user(s, role="STAFF", team="CS")
        assert resolve_order_owner(s, actor=staff, requested_owner_user_id=None) == staff.id
    finally:
        s.close()


def test_owner_staff_other_staff_rejected(pg_engine):
    s = _session(pg_engine)
    try:
        staff = _user(s, role="STAFF", team="SALES")
        other = _user(s, role="STAFF", team="SALES")
        with pytest.raises(OwnerPolicyError):
            resolve_order_owner(s, actor=staff, requested_owner_user_id=other.id)
    finally:
        s.close()


def test_owner_admin_explicit_active_sales(pg_engine):
    s = _session(pg_engine)
    try:
        admin = _user(s, role="ADMIN", team="CS")
        sales = _user(s, role="STAFF", team="SALES")
        assert resolve_order_owner(s, actor=admin, requested_owner_user_id=sales.id) == sales.id
    finally:
        s.close()


def test_owner_admin_rejects_self_missing_and_nonsales(pg_engine):
    s = _session(pg_engine)
    try:
        admin = _user(s, role="ADMIN", team="SALES")
        drawing = _user(s, role="STAFF", team="DRAWING")
        inactive = _user(s, role="STAFF", team="SALES", is_active=False)
        with pytest.raises(OwnerPolicyError):
            resolve_order_owner(s, actor=admin, requested_owner_user_id=None)
        with pytest.raises(OwnerPolicyError):
            resolve_order_owner(s, actor=admin, requested_owner_user_id=admin.id)
        with pytest.raises(OwnerPolicyError):
            resolve_order_owner(s, actor=admin, requested_owner_user_id=drawing.id)
        with pytest.raises(OwnerPolicyError):
            resolve_order_owner(s, actor=admin, requested_owner_user_id=inactive.id)
    finally:
        s.close()
