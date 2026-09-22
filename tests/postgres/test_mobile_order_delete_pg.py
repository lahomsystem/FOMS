"""MOBILE-DELETE-01: 모바일 단건 삭제·되돌리기의 실 PostgreSQL 계약 (PGTEST-00 lane).

SQLite 도메인 레인(``tests/domains/test_mobile_order_delete.py``)이 못 증명하는 것만 고정한다.

1. canonical soft delete 가 JSONB ``structured_data['delete']`` projection 을 남기고 ``status``
   는 보존하며, ``order_events`` FK 가 실제로 걸린다.
2. 사유 원장(``record_action_reason``)이 삭제 트랜잭션과 함께 커밋되고 ``other`` 메모가 보존된다.
3. 되돌리기(``restore_order``)가 ``deleted_at`` 을 지우고 ``Order.active_filter()`` 에 다시 잡힌다.

``FOMS_TEST_DATABASE_URL`` 미설정이면 lane 자체가 skip 된다(conftest).
"""

from __future__ import annotations

import uuid

from sqlalchemy import text

from foms.services.orders.change_reason import record_action_reason
from foms.services.orders.soft_delete import restore_order, soft_delete_order
from models import Order, OrderEvent, User

_N = [0]


def _sfx() -> int:
    _N[0] += 1
    return _N[0]


def _make_user(session, *, role="STAFF", team="CS") -> User:
    n = _sfx()
    user = User(
        username=f"mdel_pg_{n}", password="x", role=role, team=team,
        name=f"mdel-{n}", is_active=True,
    )
    session.add(user)
    session.flush()
    return user


def _make_order(session, stage="DRAWING") -> Order:
    order = Order(
        received_date="2026-09-22", customer_name=f"모바일삭제_{_sfx()}",
        phone="010-1234-5678", address="서울 테헤란로 123", product="붙박이장",
        status=stage, erp_stage_code=stage, is_erp_order=True,
    )
    session.add(order)
    session.flush()
    return order


def _mobile_delete(session, order: Order, actor: User, *, code: str, note: str = "") -> str:
    """API 본문(``mobile_delete_order_response``)과 같은 순서를 세션 위에서 재현한다."""
    soft_delete_order(session, order_id=order.id, actor_user_id=actor.id, reason=code)
    change_set = str(uuid.uuid4())
    record_action_reason(
        session, order_id=order.id, change_set_id=change_set,
        code=code, note=note, actor_user_id=actor.id,
    )
    session.commit()
    return change_set


def test_soft_delete_writes_jsonb_projection_mirror_and_event(pg_session):
    actor = _make_user(pg_session)
    order = _make_order(pg_session, "DRAWING")
    oid = order.id
    pg_session.commit()

    _mobile_delete(pg_session, order, actor, code="customer_request")
    pg_session.expire_all()

    row = pg_session.execute(text(
        "SELECT status, original_status, deleted_at, "
        "structured_data->'delete' AS delete_meta, mutation_version "
        "FROM orders WHERE id = :i"
    ), {"i": oid}).mappings().one()
    assert row["status"] == "DRAWING"
    assert row["original_status"] is None
    assert row["deleted_at"] is not None
    assert row["delete_meta"] is not None, "JSONB delete projection 이 없다"
    assert row["mutation_version"] >= 2

    events = pg_session.query(OrderEvent).filter(OrderEvent.order_id == oid).all()
    assert any(e.event_type == "ORDER_SOFT_DELETED" for e in events)
    # active_filter 에서 빠진다.
    assert pg_session.query(Order).filter(Order.id == oid, Order.active_filter()).first() is None


def test_reason_ledger_commits_with_delete_and_keeps_other_note(pg_session):
    actor = _make_user(pg_session, team="SALES")
    order = _make_order(pg_session, "RECEIVED")
    oid = order.id
    pg_session.commit()

    change_set = _mobile_delete(pg_session, order, actor, code="other", note="네이버 중복 주문")
    pg_session.expire_all()

    rows = pg_session.execute(text(
        "SELECT reason_code AS code, reason_note AS note FROM order_change_reasons WHERE order_id = :i AND change_set_id = :c"
    ), {"i": oid, "c": change_set}).mappings().all()
    assert len(rows) == 1, rows
    assert rows[0]["code"] == "other"
    assert rows[0]["note"] == "네이버 중복 주문"


def test_restore_returns_to_active_filter(pg_session):
    actor = _make_user(pg_session, role="ADMIN", team=None)
    order = _make_order(pg_session, "MEASURE")
    oid = order.id
    pg_session.commit()
    _mobile_delete(pg_session, order, actor, code="input_correction")
    pg_session.expire_all()

    assert pg_session.get(Order, oid).deleted_at is not None
    restore_order(pg_session, order_id=oid, actor_user_id=actor.id)
    pg_session.commit()
    pg_session.expire_all()

    restored = pg_session.query(Order).filter(Order.id == oid, Order.active_filter()).first()
    assert restored is not None
    assert restored.status == "MEASURE" and restored.original_status is None
    assert restored.deleted_at is None
