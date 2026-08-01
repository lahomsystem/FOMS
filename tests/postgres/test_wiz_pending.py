"""WIZ-01-COMPLETION PostgreSQL 계약 테스트 (PGTEST 레인).

``drawing_wizard_pending`` child 테이블·pending store 서비스·outbox ``wizard_pending_id``
FK 의 정본 계약을 실 PostgreSQL 다중 커밋 세션으로 고정한다:

* schema/state machine — READY→CLAIMED/DELETE_PENDING/QUARANTINED 허용, DELETED terminal,
  불법 전이 거부, row_version optimistic lock.
* server-derived object_key — exports 접두만 허용(traversal/타 경로 거부), unique.
* collection ETag — 어떤 pending 전이든 ETag 변경.
* outbox WIZARD_PENDING FK — orphan 거부·실 부모 happy-path.
* WIZ-DELETE-01 구현 가능성(선행 충족) — record READY → DELETE_PENDING + STORAGE_DELETE
  outbox 를 **한 tx** 로 → worker 확인 후 DELETED(child-only, Order JSON/version/event 0).

``FOMS_TEST_DATABASE_URL`` 미설정이면 conftest 가 lane 을 skip 한다(SQLite 대체 증거는
개발 로그 참조). 커밋 파일에 비밀번호를 넣지 않는다(env 로 주입).
"""
from __future__ import annotations

import datetime
import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from foms.services.datetime_kst import now_utc_naive
from foms.services.orders import drawing_wizard_pending as store
from foms.services.sidefx_outbox import enqueue_side_effect
from models import DomainSideEffectOutbox, DrawingWizardPending, Order


def _session(pg_engine):
    return sessionmaker(bind=pg_engine)()


def _now():
    return now_utc_naive()


def _make_order(session) -> Order:
    o = Order(received_date="2026-07-24", customer_name="홍길동",
              phone="010-0000-0000", address="서울", product="침대")
    session.add(o)
    session.commit()
    return o


def _key(order_id: int) -> str:
    return f"orders/{order_id}/drawing_wizard/exports/{uuid.uuid4().hex}.png"


# --------------------------------------------------------------------------- #
# 1. record / server-derived key
# --------------------------------------------------------------------------- #
def test_record_pending_ready(pg_engine):
    """record_pending 은 READY·row_version 1·expires_at 로 child row 를 만든다."""
    s = _session(pg_engine)
    try:
        o = _make_order(s)
        p = store.record_pending(s, order_id=o.id, object_key=_key(o.id), owner_user_id=None)
        s.commit()
        assert p.id is not None
        assert p.state == "READY" and p.row_version == 1
        assert p.expires_at > p.created_at
    finally:
        s.close()


@pytest.mark.parametrize("bad", [
    "orders/{oid}/measurement/x.png",     # 실측 경로(도면 아님)
    "orders/{oid}/drawing_wizard/x.png",  # exports 접두 아님
    "/orders/{oid}/drawing_wizard/exports/x.png",  # 절대경로
    "orders/{oid}/drawing_wizard/exports/../../etc/passwd",  # traversal
])
def test_record_pending_rejects_non_exports_key(pg_engine, bad):
    """server-derived exports 접두가 아닌 key 는 거부한다(경로 격리)."""
    s = _session(pg_engine)
    try:
        o = _make_order(s)
        with pytest.raises(store.DrawingWizardPendingError):
            store.record_pending(s, order_id=o.id, object_key=bad.format(oid=o.id))
    finally:
        s.close()


def test_object_key_unique(pg_engine):
    """server-derived object_key 는 pending 당 유일(중복 export 차단)."""
    s = _session(pg_engine)
    try:
        o = _make_order(s)
        key = _key(o.id)
        store.record_pending(s, order_id=o.id, object_key=key)
        s.commit()
        s.add(DrawingWizardPending(
            order_id=o.id, object_key=key, state="READY", row_version=1,
            created_at=_now(), expires_at=_now() + datetime.timedelta(days=7)))
        with pytest.raises(IntegrityError):
            s.commit()
        s.rollback()
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 2. state machine / optimistic lock
# --------------------------------------------------------------------------- #
def test_transition_ready_to_claimed_to_deleted(pg_engine):
    """READY→CLAIMED→DELETE_PENDING→DELETED 경로와 row_version bump."""
    s = _session(pg_engine)
    try:
        o = _make_order(s)
        p = store.record_pending(s, order_id=o.id, object_key=_key(o.id))
        s.commit()
        store.mark_claimed(s, p)
        assert p.state == "CLAIMED" and p.row_version == 2
        store.mark_delete_pending(s, p)
        assert p.state == "DELETE_PENDING" and p.row_version == 3
        store.mark_deleted(s, p)
        assert p.state == "DELETED" and p.row_version == 4
        s.commit()
    finally:
        s.close()


def test_illegal_transition_rejected(pg_engine):
    """DELETED 는 terminal — 어떤 전이도 PendingStateError."""
    s = _session(pg_engine)
    try:
        o = _make_order(s)
        p = store.record_pending(s, order_id=o.id, object_key=_key(o.id))
        store.mark_delete_pending(s, p)
        store.mark_deleted(s, p)
        s.commit()
        with pytest.raises(store.PendingStateError):
            store.mark_claimed(s, p)
    finally:
        s.close()


def test_ready_cannot_go_straight_to_deleted(pg_engine):
    """READY→DELETED 직행은 금지(DELETE_PENDING 경유 필수)."""
    s = _session(pg_engine)
    try:
        o = _make_order(s)
        p = store.record_pending(s, order_id=o.id, object_key=_key(o.id))
        with pytest.raises(store.PendingStateError):
            store.mark_deleted(s, p)
    finally:
        s.close()


def test_optimistic_row_version_mismatch(pg_engine):
    """expected_row_version 불일치는 PendingConcurrencyError."""
    s = _session(pg_engine)
    try:
        o = _make_order(s)
        p = store.record_pending(s, order_id=o.id, object_key=_key(o.id))
        s.commit()
        with pytest.raises(store.PendingConcurrencyError):
            store.mark_claimed(s, p, expected_row_version=99)
        assert p.state == "READY"  # 전이 없음
    finally:
        s.close()


def test_quarantine_preserves_row(pg_engine):
    """invalid pending 은 삭제하지 않고 QUARANTINED 로 보존한다(§2.6)."""
    s = _session(pg_engine)
    try:
        o = _make_order(s)
        p = store.record_pending(s, order_id=o.id, object_key=_key(o.id))
        store.quarantine(s, p)
        s.commit()
        assert p.state == "QUARANTINED"
        assert s.get(DrawingWizardPending, p.id) is not None
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 3. collection ETag
# --------------------------------------------------------------------------- #
def test_collection_etag_changes_on_mutation(pg_engine):
    """빈 order 는 sentinel, record·전이마다 ETag 가 바뀐다."""
    s = _session(pg_engine)
    try:
        o = _make_order(s)
        assert store.collection_etag(s, o.id) == "empty"
        p = store.record_pending(s, order_id=o.id, object_key=_key(o.id))
        s.commit()
        e1 = store.collection_etag(s, o.id)
        assert e1 != "empty"
        store.mark_claimed(s, p)
        s.commit()
        assert store.collection_etag(s, o.id) != e1
    finally:
        s.close()


def test_list_pending_excludes_deleted(pg_engine):
    """list_pending 기본은 DELETED terminal 제외, include_terminal=True 면 포함."""
    s = _session(pg_engine)
    try:
        o = _make_order(s)
        p1 = store.record_pending(s, order_id=o.id, object_key=_key(o.id))
        p2 = store.record_pending(s, order_id=o.id, object_key=_key(o.id))
        store.mark_delete_pending(s, p2)
        store.mark_deleted(s, p2)
        s.commit()
        active = store.list_pending(s, o.id)
        assert [p.id for p in active] == [p1.id]
        allrows = store.list_pending(s, o.id, include_terminal=True)
        assert {p.id for p in allrows} == {p1.id, p2.id}
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 4. outbox WIZARD_PENDING FK
# --------------------------------------------------------------------------- #
def test_outbox_orphan_wizard_pending_rejected(pg_engine):
    """WIZARD_PENDING outbox 는 존재하지 않는 pending 부모를 orphan 으로 거부한다."""
    s = _session(pg_engine)
    try:
        with pytest.raises(IntegrityError):
            enqueue_side_effect(s, source_domain="WIZARD_PENDING", source_id=999_999_999,
                                effect_type="STORAGE_DELETE", payload={})
        s.rollback()
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 5. WIZ-DELETE-01 구현 가능성(선행 충족)
# --------------------------------------------------------------------------- #
def test_wiz_delete_flow_on_this_schema(pg_engine):
    """WIZ-DELETE-01 이 이 스키마/서비스 위에 구현 가능함을 증명한다.

    한 business tx: pending 을 DELETE_PENDING 으로 마크 + STORAGE_DELETE outbox(실 FK)
    enqueue. worker 확인 후 DELETED 전이. Order JSON/version/event 는 건드리지 않는다(child-only).
    """
    s = _session(pg_engine)
    try:
        o = _make_order(s)
        base_version = o.mutation_version
        p = store.record_pending(s, order_id=o.id, object_key=_key(o.id))
        s.commit()

        # WIZ-DELETE business tx: DELETE_PENDING + STORAGE_DELETE outbox(한 tx).
        locked = store.get_pending(s, p.id, for_update=True)
        store.mark_delete_pending(s, locked, expected_row_version=locked.row_version)
        row = enqueue_side_effect(
            s, source_domain="WIZARD_PENDING", source_id=locked.id,
            effect_type="STORAGE_DELETE", payload={"object_key": locked.object_key},
            dedupe_key=f"WIZDEL:{locked.id}",
        )
        s.commit()
        assert row.wizard_pending_id == p.id and row.status == "PENDING"
        assert s.get(DrawingWizardPending, p.id).state == "DELETE_PENDING"

        # worker: object 삭제 확인 → child 만 DELETED. Order 는 무변경.
        store.mark_deleted(s, locked)
        s.commit()
        assert s.get(DrawingWizardPending, p.id).state == "DELETED"
        assert s.get(Order, o.id).mutation_version == base_version  # Order version bump 0
    finally:
        s.close()
