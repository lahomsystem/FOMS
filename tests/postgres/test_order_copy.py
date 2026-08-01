"""ORDER-COPY-01 PostgreSQL 계약 테스트 (PGTEST-00 lane).

주문 복사가 create_order 를 경유해 **fresh identity**(새 item UUID·SALES owner·RECEIVED
quest·version=1·GEOCODE outbox)를 부여하고, 서버 소유/운영 상태(상태·일정·도면·배정)와 첨부를
복제하지 않으며, 다건 복사가 실 PostgreSQL ``FOR UPDATE`` 정렬 lock 으로 **all-or-none**·
deadlock-free 임을 실 DB 다중 커밋으로 고정한다.

``FOMS_TEST_DATABASE_URL`` 미설정이면 lane 자체가 skip 된다(conftest). 커밋 파일에는
비밀번호를 넣지 않는다(env 로 주입). 이 DSN 이 없는 환경에서는 SQLite 증거
``tests/domains/test_order_copy_api.py`` 가 서비스 로직을 green 으로 증명한다.
"""

from __future__ import annotations

import threading
import time

import pytest
from sqlalchemy.orm import sessionmaker

from foms.services.order_copy import OrderCopyError, copy_orders_batch
from foms.services.orders.item_identity import get_or_create_identity
from foms.services.orders.order_create import OwnerPolicyError
from models import (
    DomainSideEffectOutbox,
    Order,
    OrderAssignment,
    OrderAttachment,
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
        username=f"copy_{_sfx()}",
        password="pw-not-committed",
        name=f"{role}_{team}",
        role=role,
        team=team,
        is_active=is_active,
    )
    session.add(u)
    session.commit()
    return u


def _erp_original(session, *, owner: User) -> Order:
    """DRAWING 단계·운영 상태(일정·도면·배정)·item identity·첨부를 가진 원본 ERP 주문."""
    order = Order(
        received_date="2026-07-01",
        received_time="09:00",
        customer_name="원본 고객",
        phone="010-1111-2222",
        address="서울 원본 주소",
        product="원본 제품",
        status="DRAWING",
        is_erp_order=True,
        structured_data={
            "workflow": {"stage": "DRAWING", "stage_updated_at": "2026-07-01T10:00:00"},
            "assignments": {"owner_team": "DRAWING", "drawing_assignee_user_ids": [7]},
            "shipment": {"construction_workers": ["원본 시공자"]},
            "schedule": {
                "measurement": {"date": "2026-07-05"},
                "construction": {"date": "2026-07-12"},
            },
            "parties": {"customer": {"name": "구조 고객", "phone": "010-3333-4444"}},
            "site": {"address_full": "대구 구조 주소"},
            "items": [
                {"product_name": "붙박이장", "price": 1000000},
                {"product_name": "수납장", "price": 500000},
            ],
            "payment": {"deposit": "300,000"},
            "drawing_current_files": [{"key": "drawing/original.png"}],
            "quests": [{"stage": "DRAWING", "title": "원본 퀘스트"}],
            "meta": {"draft": False, "created_via": "ERP_ORDER", "wdc_estimate_id": 5},
        },
        structured_schema_version=1,
    )
    session.add(order)
    session.flush()
    # 원본에 item identity·첨부·SALES owner 배정을 부여(복제 0 을 증명하기 위한 대조군).
    get_or_create_identity(session, order.id, 0)
    get_or_create_identity(session, order.id, 1)
    session.add(
        OrderAttachment(
            order_id=order.id, filename="d.png", file_type="image",
            category="drawing", storage_key="orders/d.png", file_size=1,
        )
    )
    session.add(
        OrderAssignment(
            order_id=order.id, domain="SALES", user_id=owner.id,
            source="INITIAL_OWNER", active=True, assigned_by_user_id=owner.id,
        )
    )
    session.commit()
    return order


# --------------------------------------------------------------------------- #
# fresh identity + server-owned reset
# --------------------------------------------------------------------------- #
def test_copy_erp_fresh_identity_and_reset(pg_engine):
    s = _session(pg_engine)
    try:
        original_owner = _user(s, role="STAFF", team="SALES")
        admin = _user(s, role="ADMIN", team="CS")
        new_owner = _user(s, role="STAFF", team="SALES")
        original = _erp_original(s, owner=original_owner)
        original_id = original.id
        original_uuids = {
            r.id for r in s.query(OrderItemIdentity).filter_by(order_id=original_id).all()
        }
        assert len(original_uuids) == 2

        results = copy_orders_batch(
            s, actor=admin, order_ids=[original_id], requested_owner_user_id=new_owner.id
        )
        s.commit()

        assert len(results) == 1
        new_id = results[0][1].id
        assert new_id != original_id

        copied = s.get(Order, new_id)
        assert copied.status == "RECEIVED"
        assert copied.mutation_version == 1
        assert copied.is_erp_order is True
        assert copied.customer_name == "구조 고객"
        assert copied.address == "대구 구조 주소"
        # 일정 미복사 → flat 실측/시공일 비어 있음.
        assert copied.measurement_date == ""
        assert copied.scheduled_date == ""

        sd = copied.structured_data
        assert sd["workflow"]["stage"] == "RECEIVED"
        assert "schedule" not in sd
        assert "assignments" not in sd
        assert "shipment" not in sd
        assert "drawing_current_files" not in sd
        assert any(q.get("stage") == "RECEIVED" for q in sd["quests"])
        assert all(q.get("stage") != "DRAWING" for q in sd["quests"])
        assert sd["meta"]["created_via"] == "ORDER_COPY"
        assert sd["meta"]["copied_from_order_id"] == original_id
        assert "wdc_estimate_id" not in sd["meta"]

        # fresh item UUID — 원본 identity 와 disjoint(클론 0).
        new_uuids = {
            r.id for r in s.query(OrderItemIdentity).filter_by(order_id=new_id, is_active=True).all()
        }
        assert len(new_uuids) == 2
        assert new_uuids.isdisjoint(original_uuids)

        # owner 는 원본 owner 가 아니라 지정된 새 SALES owner 로 재초기화(클론 0).
        owners = s.query(OrderAssignment).filter_by(order_id=new_id, domain="SALES", active=True).all()
        assert len(owners) == 1
        assert owners[0].user_id == new_owner.id
        assert owners[0].source == "INITIAL_OWNER"

        assert s.query(OrderEvent).filter_by(order_id=new_id, event_type="ORDER_CREATED").count() == 1
        # 주소 있음 → geocode outbox 예약(ADDRESS_CHANGED anchor).
        anchor = s.query(OrderEvent).filter_by(order_id=new_id, event_type="ADDRESS_CHANGED").one()
        outbox = s.query(DomainSideEffectOutbox).filter_by(
            source_domain="ORDER_EVENT", order_event_id=anchor.id, effect_type="GEOCODE"
        ).one()
        assert outbox.status == "PENDING"

        # 첨부 미복사.
        assert s.query(OrderAttachment).filter_by(order_id=new_id).count() == 0

        # 원본 불변.
        original_saved = s.get(Order, original_id)
        assert original_saved.status == "DRAWING"
        assert original_saved.structured_data["workflow"]["stage"] == "DRAWING"
        assert s.query(OrderAttachment).filter_by(order_id=original_id).count() == 1
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# all-or-none + owner 정책
# --------------------------------------------------------------------------- #
def test_copy_all_or_none_on_missing(pg_engine):
    s = _session(pg_engine)
    try:
        staff = _user(s, role="STAFF", team="SALES")
        original = _erp_original(s, owner=staff)
        before = s.query(Order).count()

        with pytest.raises(OrderCopyError):
            copy_orders_batch(s, actor=staff, order_ids=[original.id, 10_000_000])
        s.rollback()

        assert s.query(Order).count() == before
    finally:
        s.close()


def test_copy_admin_requires_owner(pg_engine):
    s = _session(pg_engine)
    try:
        admin = _user(s, role="ADMIN", team="CS")
        original = _erp_original(s, owner=_user(s, role="STAFF", team="SALES"))
        before = s.query(Order).count()

        with pytest.raises(OwnerPolicyError):
            copy_orders_batch(s, actor=admin, order_ids=[original.id])
        s.rollback()

        assert s.query(Order).count() == before
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# sorted lock — 겹치는 원본을 역순 입력으로 동시 복사해도 deadlock 0
# --------------------------------------------------------------------------- #
def test_copy_batch_sorted_lock_no_deadlock(pg_engine):
    setup = _session(pg_engine)
    try:
        staff = _user(setup, role="STAFF", team="SALES")
        o1 = _erp_original(setup, owner=staff)
        o2 = _erp_original(setup, owner=_user(setup, role="STAFF", team="SALES"))
        ids = sorted([o1.id, o2.id])
        staff_id = staff.id
    finally:
        setup.close()

    outcome: dict[str, str] = {}

    def _run(tag, order_seq):
        sess = _session(pg_engine)
        try:
            actor = sess.get(User, staff_id)
            copy_orders_batch(
                sess, actor=actor, order_ids=order_seq, requested_owner_user_id=staff_id
            )
            sess.commit()
            outcome[tag] = "ok"
        except Exception as exc:  # noqa: BLE001 - 테스트: deadlock/실패를 표면화
            sess.rollback()
            outcome[tag] = f"error:{type(exc).__name__}"
        finally:
            sess.close()

    ta = threading.Thread(target=_run, args=("A", ids))
    tb = threading.Thread(target=_run, args=("B", list(reversed(ids))))
    ta.start(); tb.start(); ta.join(15.0); tb.join(15.0)

    # 내부 정렬 lock 이라 역순 입력이어도 교차 대기(deadlock) 없이 둘 다 성공.
    assert outcome == {"A": "ok", "B": "ok"}, outcome

    check = _session(pg_engine)
    try:
        for oid in ids:
            copies = (
                check.query(Order)
                .filter(
                    Order.structured_data[("meta", "copied_from_order_id")].as_integer() == oid
                )
                .all()
            )
            assert len(copies) == 2  # 두 배치가 각각 독립 복사본 1개씩 생성(partial 0)
    finally:
        check.close()
