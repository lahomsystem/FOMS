"""STATE-DRAWING-01 PostgreSQL 계약 테스트 (PGTEST-00 lane).

도면 전달 취소가 회수 blob 삭제를 STORAGE_DELETE outbox 로 예약하는 배선을 실 PostgreSQL
로 고정한다 — SQLite domain lane 이 잡지 못하는 것:

* cancel 이 만든 ``OrderEvent`` + ``STORAGE_DELETE`` outbox + ``mutation_version`` bump 이
  한 커밋으로 원자적으로 남고, 별도 세션에서 그대로 보인다.
* outbox one-of FK 매트릭스(``ORDER_EVENT`` → ``order_event_id`` 만 non-null)와 dedupe
  unique(effect_type, dedupe_key)가 실제로 강제된다(SQLite 는 이를 완전히 재현하지 못함).

핸들러(:func:`~foms.api.drawing.erp_orders_drawing.api_order_cancel_transfer`)는 Flask
요청/세션 결합이라 route 를 직접 돌리지 않고, 그 락-아래 DB 효과(event + enqueue + version)
를 그대로 미러한 조립을 실 PG 세션에 커밋해 검증한다(tests/postgres 관례).

``FOMS_TEST_DATABASE_URL`` 미설정이면 conftest 가 lane 을 skip 한다(dev DSN 은 env 로만
주입, 커밋 파일에 비밀번호 금지).
"""
from __future__ import annotations

import time

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from foms.services.sidefx_outbox import enqueue_side_effect
from models import DomainSideEffectOutbox, Order, OrderEvent, User

_SEQ = [0]


def _session(pg_engine):
    return sessionmaker(bind=pg_engine)()


def _make_order(session) -> Order:
    _SEQ[0] += 1
    o = Order(
        received_date="2026-07-24", customer_name="홍길동", phone="010-0000-0000",
        address="서울", product="침대", is_erp_order=True, status="DRAWING",
        erp_stage_code="DRAWING",
        structured_data={"workflow": {"stage": "DRAWING"}, "drawing_status": "TRANSFERRED"},
    )
    session.add(o)
    session.commit()
    return o


def _make_actor(session) -> User:
    _SEQ[0] += 1
    u = User(username=f"sd_{_SEQ[0]}_{int(time.time() * 1000) % 100000}",
             password="pw-not-committed", name="도면", role="ADMIN",
             team="DRAWING", is_active=True)
    session.add(u)
    session.commit()
    return u


def _cancel_effect(session, order, actor_id, keys):
    """cancel 핸들러의 락-아래 DB 효과를 미러: event + version bump + STORAGE_DELETE enqueue."""
    ev = OrderEvent(
        order_id=order.id,
        event_type="DRAWING_TRANSFER_CANCELLED",
        payload={"action": "CANCEL_TRANSFER", "deleted_keys": sorted(keys)},
        created_by_user_id=actor_id,
    )
    session.add(ev)
    session.flush()
    order.mutation_version = (order.mutation_version or 0) + 1
    for key in sorted(keys):
        enqueue_side_effect(
            session,
            source_domain="ORDER_EVENT",
            source_id=ev.id,
            effect_type="STORAGE_DELETE",
            payload={"object_key": key, "order_id": order.id},
            dedupe_key=f"drawing_cancel:{order.id}:{key}",
        )
    return ev


def test_pg_cancel_enqueues_storage_delete_atomically(pg_engine):
    """cancel 효과(event + STORAGE_DELETE outbox + version)가 한 커밋으로 원자 반영된다."""
    s = _session(pg_engine)
    try:
        actor = _make_actor(s)
        order = _make_order(s)
        oid = order.id
        base_version = order.mutation_version
        key = f"orders/{oid}/drawing_wizard/exports/new.png"
        ev = _cancel_effect(s, order, actor.id, [key])
        s.commit()
        ev_id = ev.id
    finally:
        s.close()

    check = _session(pg_engine)
    try:
        o = check.query(Order).filter_by(id=oid).one()
        assert o.mutation_version == base_version + 1
        row = check.query(DomainSideEffectOutbox).filter_by(
            effect_type="STORAGE_DELETE", order_event_id=ev_id).one()
        assert row.payload["object_key"] == key
        assert row.status == "PENDING"
        # one-of FK 매트릭스: ORDER_EVENT source 는 order_event_id 만 non-null.
        assert row.order_event_id == ev_id
        assert row.upload_ticket_id is None and row.notification_event_id is None
    finally:
        check.close()


def test_pg_cancel_storage_delete_dedupe(pg_engine):
    """같은 (effect_type, dedupe_key) 재enqueue 는 unique 로 거부된다(중복 STORAGE_DELETE 0)."""
    s = _session(pg_engine)
    try:
        actor = _make_actor(s)
        order = _make_order(s)
        key = f"orders/{order.id}/drawing_wizard/exports/dup.png"
        _cancel_effect(s, order, actor.id, [key])
        s.commit()
    finally:
        s.close()

    s2 = _session(pg_engine)
    try:
        o = s2.query(Order).filter_by(id=order.id).one()
        actor2 = o  # noqa: F841 (reuse committed order)
        with pytest.raises(IntegrityError):
            _cancel_effect(s2, o, actor.id, [key])
            s2.flush()
    finally:
        s2.rollback()
        s2.close()
