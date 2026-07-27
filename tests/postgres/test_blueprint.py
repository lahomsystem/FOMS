"""BLUEPRINT-01 PostgreSQL 계약 테스트 (PGTEST-00 lane).

BLUEPRINT-01 typed current projection·safe backfill 을 실 PostgreSQL 세션(JSONB·FK CHECK·
STORAGE_DELETE outbox one-of 매트릭스)으로 고정한다:

* **ORDER_BLUEPRINT ticket → projection**: issue_ticket(server-derived key)+complete_ticket
  (exact-match tamper)로 첨부를 만들고 set_current_blueprint 가 ``structured_data['blueprint']
  ['current']`` typed projection·파생 scalar·SET event 를 만든다(scalar direct write 0).
* **exact key**: complete_ticket 은 ticket key 와 다른 key(substring 포함)를 거부한다.
* **typed replace**: 두 번째 blueprint 는 이전 object 를 STORAGE_DELETE outbox(source_domain
  ORDER_EVENT)로 예약하고 REPLACED event·이전 첨부 제거를 남긴다(동기 R2 삭제 0).
* **delete outbox**: clear_current_blueprint 은 projection·scalar 를 비우고 STORAGE_DELETE
  outbox·DELETED event 를 남긴다.
* **legacy safe backfill 100%**: exact 유도 + ambiguous 무손실 보존(auto-map 0), coverage
  complete, 멱등, downgrade 는 backfill provenance 만 제거.

``FOMS_TEST_DATABASE_URL`` 미설정이면 conftest 가 lane 을 skip 한다. 커밋 파일에는 비밀번호를
넣지 않는다(env 로 주입).
"""
from __future__ import annotations

import types

import pytest
from sqlalchemy.orm import sessionmaker

from foms.services.orders.blueprint_projection import (
    apply_blueprint_backfill,
    clear_current_blueprint,
    get_current_blueprint,
    remove_backfill_projection,
    set_current_blueprint,
    verify_blueprint_coverage,
)
from foms.services.orders.upload_ticket import (
    UploadTicketError,
    UploadTicketForbidden,
    complete_ticket,
    issue_ticket,
)
from models import DomainSideEffectOutbox, Order, OrderAttachment, OrderEvent


def _session(pg_engine):
    return sessionmaker(bind=pg_engine)()


def _staff():
    return types.SimpleNamespace(id=1, role="STAFF", team="CS")


def _viewer():
    return types.SimpleNamespace(id=2, role="VIEWER", team=None)


def _make_order(session, scalar=None) -> Order:
    o = Order(received_date="2026-07-27", customer_name="홍길동", phone="010-0000-0000",
              address="서울", product="침대", blueprint_image_url=scalar)
    session.add(o)
    session.commit()
    return o


def _upload(session, order_id, filename="plan.png"):
    """issue→complete 로 blueprint 첨부를 만들고 projection 을 설정한다(한 tx)."""
    ticket = issue_ticket(session, order_id=order_id, filename=filename, file_size=1000,
                          user=_staff(), category="measurement")
    _ticket, attachment = complete_ticket(
        session, ticket_id=ticket.id, object_key=ticket.object_key, user=_staff())
    order = session.get(Order, order_id)
    current = set_current_blueprint(session, order, attachment=attachment, actor_user_id=1)
    session.commit()
    return ticket, attachment, current


# --------------------------------------------------------------------------- #
# ticket → typed current projection (scalar direct write 0)
# --------------------------------------------------------------------------- #
def test_upload_sets_typed_projection_and_parallel_scalar(pg_engine):
    """complete → set_current_blueprint: projection·파생 scalar·version bump·SET event."""
    s = _session(pg_engine)
    try:
        o = _make_order(s)
        v0 = o.mutation_version
        _t, att, current = _upload(s, o.id)
        order = s.get(Order, o.id)
        cur = get_current_blueprint(order)
        assert cur["object_key"] == att.storage_key == current["object_key"]
        assert cur["provenance"] == "ticket"
        assert order.blueprint_image_url == cur["view_url"]  # 병행 파생 projection
        assert order.mutation_version > v0                    # complete_ticket REV-00 bump
        assert s.query(OrderEvent).filter_by(order_id=o.id,
                                             event_type="BLUEPRINT_SET").count() == 1
    finally:
        s.close()


def test_complete_rejects_tampered_key(pg_engine):
    """complete_ticket 은 ticket key 와 다른 key(substring superstring)를 exact-match 로 거부."""
    s = _session(pg_engine)
    try:
        o = _make_order(s)
        ticket = issue_ticket(s, order_id=o.id, filename="a.png", file_size=10, user=_staff())
        s.commit()
        with pytest.raises(UploadTicketError):
            complete_ticket(s, ticket_id=ticket.id, object_key=ticket.object_key + "x",
                            user=_staff())
    finally:
        s.close()


def test_issue_rejects_viewer(pg_engine):
    """issue_ticket 은 VIEWER(무권한)를 거부한다(login-only 아님·auth 재검사)."""
    s = _session(pg_engine)
    try:
        o = _make_order(s)
        with pytest.raises(UploadTicketForbidden):
            issue_ticket(s, order_id=o.id, filename="a.png", file_size=10, user=_viewer())
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# typed replace / delete outbox (동기 R2 삭제 0)
# --------------------------------------------------------------------------- #
def test_replace_enqueues_storage_delete_and_removes_prev(pg_engine):
    """두 번째 업로드: 이전 object STORAGE_DELETE outbox·REPLACED event·이전 첨부 제거."""
    s = _session(pg_engine)
    try:
        o = _make_order(s)
        _t1, att1, _c1 = _upload(s, o.id, filename="a.png")
        _t2, att2, _c2 = _upload(s, o.id, filename="b.png")

        rows = s.query(DomainSideEffectOutbox).filter_by(effect_type="STORAGE_DELETE").all()
        assert any(r.payload.get("object_key") == att1.storage_key for r in rows)
        assert all(r.source_domain == "ORDER_EVENT" for r in rows)
        assert s.query(OrderEvent).filter_by(order_id=o.id,
                                             event_type="BLUEPRINT_REPLACED").count() == 1
        keys = {a.storage_key for a in s.query(OrderAttachment).filter_by(order_id=o.id)}
        assert keys == {att2.storage_key}
        assert get_current_blueprint(s.get(Order, o.id))["object_key"] == att2.storage_key
    finally:
        s.close()


def test_delete_enqueues_outbox_and_clears(pg_engine):
    """clear_current_blueprint: projection·scalar 비우고 STORAGE_DELETE outbox·DELETED event."""
    s = _session(pg_engine)
    try:
        o = _make_order(s)
        _t, att, _c = _upload(s, o.id)
        order = s.get(Order, o.id)
        removed = clear_current_blueprint(s, order, actor_user_id=1)
        order.mutation_version = (order.mutation_version or 0) + 1  # 호출자 version bump(REV-00)
        s.commit()

        assert removed["object_key"] == att.storage_key
        assert get_current_blueprint(s.get(Order, o.id)) is None
        assert s.get(Order, o.id).blueprint_image_url is None
        rows = s.query(DomainSideEffectOutbox).filter_by(effect_type="STORAGE_DELETE").all()
        assert any(r.payload.get("object_key") == att.storage_key for r in rows)
        assert s.query(OrderEvent).filter_by(order_id=o.id,
                                             event_type="BLUEPRINT_DELETED").count() == 1
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# legacy safe backfill 100% (ambiguous auto-map 0)
# --------------------------------------------------------------------------- #
def test_backfill_exact_ambiguous_coverage_idempotent(pg_engine):
    """scalar → projection: exact 유도·ambiguous 무손실 보존·coverage 100%·멱등·downgrade."""
    s = _session(pg_engine)
    try:
        oe = _make_order(s)
        oe.blueprint_image_url = f"/api/files/view/orders/{oe.id}/blueprint/plan.png"
        oa = _make_order(s, scalar="https://cdn.example.com/legacy.png")
        s.commit()

        dry = apply_blueprint_backfill(s, apply=False)
        assert dry.total == 2 and dry.exact == 1 and dry.ambiguous == 1 and not dry.applied
        assert get_current_blueprint(s.get(Order, oe.id)) is None  # 무쓰기

        apply_blueprint_backfill(s, apply=True)
        s.commit()
        ce = get_current_blueprint(s.get(Order, oe.id))
        assert ce["object_key"] == f"orders/{oe.id}/blueprint/plan.png"
        ca = get_current_blueprint(s.get(Order, oa.id))
        assert ca["object_key"] is None and ca["ambiguous"] is True     # auto-map 금지
        assert ca["view_url"] == "https://cdn.example.com/legacy.png"   # 원문 무손실
        assert s.get(Order, oa.id).blueprint_image_url == "https://cdn.example.com/legacy.png"

        cov = verify_blueprint_coverage(s)
        assert cov.total == 2 and cov.missing == 0 and cov.coverage_complete

        again = apply_blueprint_backfill(s, apply=True)  # 멱등
        assert again.projected == 0 and again.already_present == 2

        assert remove_backfill_projection(s) == 2  # downgrade: backfill provenance 만 제거
        s.commit()
        assert get_current_blueprint(s.get(Order, oe.id)) is None
    finally:
        s.close()
