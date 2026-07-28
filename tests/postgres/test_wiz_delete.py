"""WIZ-DELETE-01 PostgreSQL 계약 테스트 (PGTEST 레인).

도면 pending 삭제 command 와 공용 ``STORAGE_DELETE`` handler(task #44 해소)를 실 PostgreSQL
다중 커밋 세션으로 고정한다:

* **delete command 브리지**: JSON pending export → ``drawing_wizard_pending`` child 로
  materialize → ``DELETE_PENDING`` + ``WIZARD_PENDING`` ``STORAGE_DELETE`` outbox(실 FK)를
  **한 tx**. object_key 는 server-derived exports 접두만 허용(타 주문/실측 key 거부).
* **공용 handler**: ``WIZARD_PENDING`` → R2 삭제 + child ``DELETED`` 전이, worker 는 Order
  JSON/version 을 쓰지 않는다(child-only). retry idempotent(이미 DELETED 면 중복 삭제 0).
* **타 도메인**: ``ORDER_EVENT`` 등 다른 도메인 ``STORAGE_DELETE`` 도 payload object_key R2
  삭제로 공용 처리(child terminal 은 producer 소관). object_key 없으면 안전 skip.

``FOMS_TEST_DATABASE_URL`` 미설정이면 conftest 가 lane 을 skip 한다(SQLite 대체 증거는 domain
lane ``tests/domains/test_drawing_wizard_api.py`` 참조). 커밋 파일에 비밀번호를 넣지 않는다
(env 로 주입). 세션 공유 pg_engine 이라 전역 claim 을 쓰는 handler 테스트는 ``_quiesce`` 로
PENDING/PROCESSING/DEAD 를 중립화한 뒤 시작한다.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

import foms.services.storage_delete_handler as sdh
from foms.api.drawing.wizard import _enqueue_pending_export_delete
from foms.services.datetime_kst import now_utc_naive
from foms.services.orders import drawing_wizard_pending as store
from foms.services.sidefx_outbox import enqueue_side_effect
from foms.services.sidefx_worker import (
    clear_handlers,
    register_handler,
    run_delivery_once,
)
from foms.services.storage_delete_handler import handle_storage_delete
from models import (
    DomainSideEffectOutbox,
    DrawingWizardPending,
    Order,
    OrderEvent,
)


class _RecordingStorage:
    """delete_file 호출 key 를 기록하는 테스트용 스토리지(중복 삭제 계수)."""

    def __init__(self):
        self.deleted: list[str] = []

    def delete_file(self, key):
        self.deleted.append(key)
        return True


@pytest.fixture
def storage(monkeypatch):
    """handler 의 get_storage 를 recording fake 로 교체하고 인스턴스를 돌려준다."""
    fake = _RecordingStorage()
    monkeypatch.setattr(sdh, "get_storage", lambda: fake)
    return fake


@pytest.fixture(autouse=True)
def _handler_registry():
    """STORAGE_DELETE handler 를 등록하고 테스트 후 registry 를 비운다(격리)."""
    clear_handlers()
    register_handler("STORAGE_DELETE", handle_storage_delete, replace=True)
    yield
    clear_handlers()


def _session(pg_engine):
    return sessionmaker(bind=pg_engine)()


def _make_order(session) -> Order:
    o = Order(received_date="2026-07-24", customer_name="홍길동",
              phone="010-0000-0000", address="서울", product="침대")
    session.add(o)
    session.commit()
    return o


def _key(order_id: int) -> str:
    return f"orders/{order_id}/drawing_wizard/exports/{uuid.uuid4().hex}.png"


def _quiesce(pg_engine) -> None:
    """다른 테스트가 남긴 PENDING/PROCESSING/DEAD outbox 를 recent DONE 으로 중립화한다."""
    now = now_utc_naive()
    with pg_engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE domain_side_effect_outbox "
                "SET status='DONE', completed_at=:now, dead_at=NULL, "
                "    lease_owner_hash=NULL, lease_token=NULL, lease_expires_at=NULL "
                "WHERE status IN ('PENDING','PROCESSING','DEAD')"
            ),
            {"now": now},
        )


# --------------------------------------------------------------------------- #
# 1. delete command 브리지 — JSON pending → child DELETE_PENDING + outbox(한 tx)
# --------------------------------------------------------------------------- #
def test_delete_command_bridges_json_pending_to_child_and_outbox(pg_engine):
    """JSON pending export → child DELETE_PENDING + WIZARD_PENDING STORAGE_DELETE outbox(한 tx).

    요청 tx 에서 R2 를 동기 삭제하지 않고(브리지 함수는 storage 참조 자체가 없음) child +
    outbox 만 원자 예약한다. worker 가 뒤에서 삭제한다.
    """
    s = _session(pg_engine)
    try:
        o = _make_order(s)
        base_version = o.mutation_version
        key = _key(o.id)
        deleted_key, pending_id = _enqueue_pending_export_delete(
            s, o.id, {"key": key}, owner_user_id=None)
        s.commit()

        assert deleted_key == key and pending_id is not None
        child = s.get(DrawingWizardPending, pending_id)
        assert child.object_key == key and child.state == "DELETE_PENDING"
        outbox = s.query(DomainSideEffectOutbox).filter_by(
            source_domain="WIZARD_PENDING", wizard_pending_id=child.id,
            effect_type="STORAGE_DELETE").one()
        assert outbox.status == "PENDING"
        assert (outbox.payload or {}).get("object_key") == key
        # command tx 는 Order version 을 건드리지 않는다(structured_data 는 route 가 별도 관리).
        assert s.get(Order, o.id).mutation_version == base_version
    finally:
        s.close()


@pytest.mark.parametrize("bad_key", [
    "orders/{oid}/measurement/x.png",       # 실측 경로(도면 아님)
    "orders/{other}/drawing_wizard/exports/x.png",  # 타 주문 exports
    "orders/{oid}/drawing_wizard/exports/../../etc/passwd",  # traversal
])
def test_delete_command_rejects_non_server_derived_key(pg_engine, bad_key):
    """server-derived exports 접두가 아닌(또는 타 주문) key 는 child·outbox 를 만들지 않는다."""
    s = _session(pg_engine)
    try:
        o = _make_order(s)
        entry = {"key": bad_key.format(oid=o.id, other=o.id + 987654)}
        deleted_key, pending_id = _enqueue_pending_export_delete(
            s, o.id, entry, owner_user_id=None)
        s.commit()
        assert deleted_key is None and pending_id is None
        assert s.query(DrawingWizardPending).filter_by(order_id=o.id).count() == 0
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 2. 공용 handler — WIZARD_PENDING child DELETED + R2 삭제 · Order write 0
# --------------------------------------------------------------------------- #
def test_handler_wizard_pending_deletes_object_and_marks_child(pg_engine, storage):
    """worker delivery: R2 object 삭제 + child DELETED, outbox DONE. Order version 무변경."""
    _quiesce(pg_engine)
    s = _session(pg_engine)
    try:
        o = _make_order(s)
        base_version = o.mutation_version
        base_sd = o.structured_data
        key = _key(o.id)
        child = store.record_pending(s, order_id=o.id, object_key=key)
        store.mark_delete_pending(s, child)
        row = enqueue_side_effect(
            s, source_domain="WIZARD_PENDING", source_id=child.id,
            effect_type="STORAGE_DELETE", payload={"object_key": key},
            dedupe_key=f"wizdel:{child.id}")
        s.commit()
        order_id, child_id, row_id = o.id, child.id, row.id
    finally:
        s.close()

    result = run_delivery_once(
        pg_engine, owner_hash="w" * 64, lease_token_fn=lambda: str(uuid.uuid4()))
    assert result["done"] >= 1

    # R2 object 정확히 1회 삭제.
    assert storage.deleted == [key]
    s = _session(pg_engine)
    try:
        assert s.get(DrawingWizardPending, child_id).state == "DELETED"
        assert s.get(DomainSideEffectOutbox, row_id).status == "DONE"
        # worker Order write 0 — version·structured_data 무변경.
        order = s.get(Order, order_id)
        assert order.mutation_version == base_version
        assert order.structured_data == base_sd
    finally:
        s.close()


def test_handler_retry_idempotent_no_duplicate_delete(pg_engine, storage):
    """이미 DELETED 인 child 를 다시 배달해도 R2 재삭제 0(retry idempotent)."""
    _quiesce(pg_engine)
    s = _session(pg_engine)
    try:
        o = _make_order(s)
        key = _key(o.id)
        child = store.record_pending(s, order_id=o.id, object_key=key)
        store.mark_delete_pending(s, child)
        enqueue_side_effect(
            s, source_domain="WIZARD_PENDING", source_id=child.id,
            effect_type="STORAGE_DELETE", payload={"object_key": key},
            dedupe_key=f"wizdel:{child.id}")
        s.commit()
        child_id = child.id
    finally:
        s.close()

    run_delivery_once(pg_engine, owner_hash="w" * 64, lease_token_fn=lambda: str(uuid.uuid4()))
    assert storage.deleted == [key]  # 1회

    # 같은 child(now DELETED)로 두 번째 outbox 를 만들어 재배달 → 중복 삭제 0.
    s = _session(pg_engine)
    try:
        assert s.get(DrawingWizardPending, child_id).state == "DELETED"
        row2 = enqueue_side_effect(
            s, source_domain="WIZARD_PENDING", source_id=child_id,
            effect_type="STORAGE_DELETE", payload={"object_key": key},
            dedupe_key=f"wizdel-retry:{child_id}")
        s.commit()
        row2_id = row2.id
    finally:
        s.close()

    run_delivery_once(pg_engine, owner_hash="w" * 64, lease_token_fn=lambda: str(uuid.uuid4()))
    assert storage.deleted == [key]  # 여전히 1회 — 중복 삭제 0
    s = _session(pg_engine)
    try:
        assert s.get(DomainSideEffectOutbox, row2_id).status == "DONE"
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 3. 공용 handler — 타 도메인 object_key 삭제 · 미지원 payload 안전 skip
# --------------------------------------------------------------------------- #
def test_handler_other_domain_deletes_object_key_only(pg_engine, storage):
    """ORDER_EVENT STORAGE_DELETE 는 payload object_key R2 삭제만(child terminal 은 producer 소관)."""
    _quiesce(pg_engine)
    s = _session(pg_engine)
    try:
        o = _make_order(s)
        ev = OrderEvent(order_id=o.id, event_type="DRAWING_TRANSFER_CANCELLED",
                        payload={"x": 1})
        s.add(ev)
        s.flush()
        att_key = f"orders/{o.id}/drawing/att-{uuid.uuid4().hex}.png"
        row = enqueue_side_effect(
            s, source_domain="ORDER_EVENT", source_id=ev.id,
            effect_type="STORAGE_DELETE",
            payload={"object_key": att_key, "order_id": o.id},
            dedupe_key=f"evdel:{ev.id}")
        s.commit()
        ev_id, row_id = ev.id, row.id
    finally:
        s.close()

    run_delivery_once(pg_engine, owner_hash="w" * 64, lease_token_fn=lambda: str(uuid.uuid4()))
    assert storage.deleted == [att_key]
    s = _session(pg_engine)
    try:
        assert s.get(DomainSideEffectOutbox, row_id).status == "DONE"
        # handler 는 source OrderEvent 를 건드리지 않는다(child terminal 은 producer 몫).
        assert s.get(OrderEvent, ev_id) is not None
    finally:
        s.close()


def test_handler_missing_object_key_safe_skip(pg_engine, storage):
    """object_key 없는 STORAGE_DELETE 는 안전 skip(DONE, R2 삭제 0, DEAD 아님)."""
    _quiesce(pg_engine)
    s = _session(pg_engine)
    try:
        o = _make_order(s)
        ev = OrderEvent(order_id=o.id, event_type="DRAWING_TRANSFER_CANCELLED", payload={})
        s.add(ev)
        s.flush()
        row = enqueue_side_effect(
            s, source_domain="ORDER_EVENT", source_id=ev.id,
            effect_type="STORAGE_DELETE", payload={}, dedupe_key=f"evnokey:{ev.id}")
        s.commit()
        row_id = row.id
    finally:
        s.close()

    result = run_delivery_once(
        pg_engine, owner_hash="w" * 64, lease_token_fn=lambda: str(uuid.uuid4()))
    assert result["dead"] == 0
    assert storage.deleted == []
    s = _session(pg_engine)
    try:
        assert s.get(DomainSideEffectOutbox, row_id).status == "DONE"
    finally:
        s.close()
