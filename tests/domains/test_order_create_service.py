"""ORDER-CREATE-01 service-logic evidence (SQLite lane).

PG 계약(partial unique·다중 커밋 동시성)은 ``tests/postgres/test_order_create.py`` 가
실 PostgreSQL 로 고정한다. dev DSN 이 없을 때 이 파일이 canonical constructor 의 원자 조립
(item identity·RECEIVED quest·version=1·SALES owner·ORDER_CREATED event·GEOCODE outbox)과
owner 정책(STAFF self / Admin explicit active SALES / admin·타 STAFF 금지), 그리고 ``/add``
endpoint 에서 raw ``Order(...)`` 가 사라졌음을 in-memory SQLite + 소스 검사로 증명한다.
"""
from __future__ import annotations

import inspect

import pytest

from db import db_session
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


def _uid() -> str:
    _SEQ[0] += 1
    return str(_SEQ[0])


def _user(role="STAFF", team="SALES", is_active=True) -> User:
    u = User(
        username=f"oc_{role}_{_uid()}",
        password="pw-not-committed",
        name=f"{role}_{team}",
        role=role,
        team=team,
        is_active=is_active,
    )
    db_session.add(u)
    db_session.commit()
    return u


def _erp_sd() -> dict:
    return {
        "parties": {"customer": {"name": "홍길동", "phone": "010-1234-5678"}},
        "site": {"address_full": "서울시 강남구 1"},
        "items": [{"product_name": "붙박이장", "price": 1000000}, {"product_name": "수납장", "price": 500000}],
    }


# --------------------------------------------------------------------------- #
# owner 정책
# --------------------------------------------------------------------------- #
def test_owner_staff_self_default(app) -> None:
    staff = _user(role="STAFF", team="CS")
    assert resolve_order_owner(db_session, actor=staff, requested_owner_user_id=None) == staff.id
    # 명시적으로 본인을 지정하는 것도 허용.
    assert resolve_order_owner(db_session, actor=staff, requested_owner_user_id=staff.id) == staff.id


def test_owner_staff_other_staff_rejected(app) -> None:
    staff = _user(role="STAFF", team="SALES")
    other = _user(role="STAFF", team="SALES")
    with pytest.raises(OwnerPolicyError):
        resolve_order_owner(db_session, actor=staff, requested_owner_user_id=other.id)


def test_owner_admin_requires_explicit_active_sales(app) -> None:
    admin = _user(role="ADMIN", team="CS")
    sales = _user(role="STAFF", team="SALES")
    assert resolve_order_owner(db_session, actor=admin, requested_owner_user_id=sales.id) == sales.id


def test_owner_admin_missing_owner_rejected(app) -> None:
    admin = _user(role="ADMIN", team="CS")
    with pytest.raises(OwnerPolicyError):
        resolve_order_owner(db_session, actor=admin, requested_owner_user_id=None)


def test_owner_admin_self_owner_rejected(app) -> None:
    admin = _user(role="ADMIN", team="SALES")
    with pytest.raises(OwnerPolicyError):
        resolve_order_owner(db_session, actor=admin, requested_owner_user_id=admin.id)


def test_owner_admin_nonsales_owner_rejected(app) -> None:
    admin = _user(role="ADMIN", team="CS")
    drawing = _user(role="STAFF", team="DRAWING")
    with pytest.raises(OwnerPolicyError):
        resolve_order_owner(db_session, actor=admin, requested_owner_user_id=drawing.id)


def test_owner_admin_inactive_sales_rejected(app) -> None:
    admin = _user(role="ADMIN", team="CS")
    inactive = _user(role="STAFF", team="SALES", is_active=False)
    with pytest.raises(OwnerPolicyError):
        resolve_order_owner(db_session, actor=admin, requested_owner_user_id=inactive.id)


# --------------------------------------------------------------------------- #
# 생성자 원자 조립
# --------------------------------------------------------------------------- #
def test_erp_create_assembles_all_atomic_items(app) -> None:
    staff = _user(role="STAFF", team="SALES")
    order = create_order(
        db_session,
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
    db_session.commit()

    # version=1
    assert order.mutation_version == 1
    # RECEIVED quest seed
    quests = (order.structured_data or {}).get("quests")
    assert isinstance(quests, list) and any(q.get("stage") == "RECEIVED" for q in quests)
    # item identities: 아이템 슬롯당 1개
    ids = db_session.query(OrderItemIdentity).filter_by(order_id=order.id, is_active=True).all()
    assert len(ids) == 2
    # SALES owner 배정 1건(INITIAL_OWNER)
    owners = db_session.query(OrderAssignment).filter_by(
        order_id=order.id, domain="SALES", active=True
    ).all()
    assert len(owners) == 1
    assert owners[0].user_id == staff.id and owners[0].source == "INITIAL_OWNER"
    # 생성 event
    assert db_session.query(OrderEvent).filter_by(order_id=order.id, event_type="ORDER_CREATED").count() == 1
    # geocode outbox 예약(주소 있음) + postcommit 직접 지오코드 0
    outbox = db_session.query(DomainSideEffectOutbox).filter_by(effect_type="GEOCODE").all()
    assert len(outbox) == 1 and outbox[0].status == "PENDING"


def test_legacy_create_owner_and_geocode_without_quest_or_items(app) -> None:
    staff = _user(role="STAFF", team="CS")
    order = create_order(
        db_session,
        actor_user_id=staff.id,
        owner_user_id=staff.id,
        order_fields=dict(
            received_date="2026-07-24", customer_name="김철수",
            phone="010-9999-8888", address="부산시 해운대구 2", product="침대",
            status="RECEIVED",
        ),
        is_erp_order=False,
    )
    db_session.commit()

    assert order.is_erp_order is False
    assert order.structured_data is None  # 레거시는 quest/items 를 강제하지 않는다
    assert db_session.query(OrderItemIdentity).filter_by(order_id=order.id).count() == 0
    assert db_session.query(OrderAssignment).filter_by(order_id=order.id, domain="SALES", active=True).count() == 1
    assert db_session.query(OrderEvent).filter_by(order_id=order.id, event_type="ORDER_CREATED").count() == 1
    assert db_session.query(DomainSideEffectOutbox).filter_by(effect_type="GEOCODE").count() == 1


def test_blank_address_skips_geocode_outbox(app) -> None:
    staff = _user(role="STAFF", team="SALES")
    create_order(
        db_session,
        actor_user_id=staff.id,
        owner_user_id=staff.id,
        order_fields=dict(
            received_date="2026-07-24", customer_name="주소없음",
            phone="010-0000-0000", address="-", product="상담",
            status="RECEIVED",
        ),
        is_erp_order=False,
    )
    db_session.commit()
    assert db_session.query(DomainSideEffectOutbox).filter_by(effect_type="GEOCODE").count() == 0


def test_partial_failure_rolls_back_whole_order(app, monkeypatch) -> None:
    staff = _user(role="STAFF", team="SALES")
    before_orders = db_session.query(Order).count()
    before_outbox = db_session.query(DomainSideEffectOutbox).count()

    import foms.services.orders.order_create as oc

    def _boom(*_a, **_k):
        raise RuntimeError("identity mint failed")

    monkeypatch.setattr(oc, "get_or_create_identity", _boom)
    with pytest.raises(RuntimeError):
        create_order(
            db_session,
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
    db_session.rollback()

    assert db_session.query(Order).count() == before_orders
    assert db_session.query(DomainSideEffectOutbox).count() == before_outbox


# --------------------------------------------------------------------------- #
# endpoint raw Order(...) == 0
# --------------------------------------------------------------------------- #
def test_add_order_endpoint_has_no_raw_order_constructor() -> None:
    from foms.web.orders.listing import add_order

    source = inspect.getsource(add_order)
    assert "create_order(" in source
    assert "Order(" not in source  # raw Order(...) endpoint constructor 잔존 0
