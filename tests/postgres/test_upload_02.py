"""UPLOAD-02 PostgreSQL 계약 테스트 (PGTEST-00 lane).

per-file 업로드 ticket 수명주기 + bounded cleanup provider + worker 300s 배선을 실
PostgreSQL 세션으로 고정한다:

* **issue**: ISSUED + 900s expiry + server-derived key, auth(VIEWER 거부)·resource(order)·
  item-active·type/size 재검사.
* **complete**: 재검사(auth/resource/item-active) + tamper(key 불일치)·expiry·type/size 검증,
  첨부 생성 + Order ``mutation_version`` 1회 bump(REV-00), retry idempotent(중복 첨부/bump 0).
* **item-retire race**: retire 후 complete 거부, complete 후 retire 는 첨부 보존.
* **provider bounded scan**: 만료·item-은퇴 ISSUED 티켓 claim(EXPIRED) + 만료 DRAFT claim
  (CANCELLED) → ``STORAGE_DELETE`` outbox, advisory lock skip, bounded limit, retry idempotent.
* **worker 300s**: :func:`run_expiry_scan_once` 가 등록 provider 를 호출한다(별도 scheduler 0).

``FOMS_TEST_DATABASE_URL`` 미설정이면 conftest 가 lane 을 skip 한다. 커밋 파일에는 비밀번호를
넣지 않는다(env 로 주입).
"""
from __future__ import annotations

import datetime
import pathlib
import types
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from foms.services.datetime_kst import now_utc_naive
from foms.services.orders.item_identity import get_or_create_identity, retire_identity
from foms.services.orders.upload_intent import create_upload_draft
from foms.services.orders.upload_ticket import (
    UploadTicketError,
    UploadTicketForbidden,
    complete_ticket,
    issue_ticket,
)
from foms.services.sidefx_worker import (
    clear_expiry_scan_providers,
    register_expiry_scan_provider,
    run_expiry_scan_once,
)
from foms.services.upload_cleanup import run_upload_expiry_scan_once
from models import (
    DomainSideEffectOutbox,
    Order,
    OrderAttachment,
    UploadDraft,
    UploadTicket,
)


def _session(pg_engine):
    return sessionmaker(bind=pg_engine)()


def _now():
    return now_utc_naive()


def _staff():
    return types.SimpleNamespace(id=1, role="STAFF", team="CS")


def _viewer():
    return types.SimpleNamespace(id=2, role="VIEWER", team=None)


def _make_order(session) -> Order:
    o = Order(received_date="2026-07-24", customer_name="홍길동",
              phone="010-0000-0000", address="서울", product="침대")
    session.add(o)
    session.commit()
    return o


# --------------------------------------------------------------------------- #
# issue — ISSUED · 900s · server-derived key · 재검사
# --------------------------------------------------------------------------- #
def test_issue_creates_issued_ticket_900s(pg_engine):
    """issue 는 ISSUED·900s expiry·server-derived key(orders/{id}/...)·file_type 를 만든다."""
    s = _session(pg_engine)
    try:
        o = _make_order(s)
        base = _now()
        t = issue_ticket(s, order_id=o.id, filename="a.jpg", file_size=1000,
                         user=_staff(), category="measurement", now=base)
        s.commit()
        assert t.state == "ISSUED"
        assert t.expires_at == base + datetime.timedelta(seconds=900)
        assert t.object_key.startswith(f"orders/{o.id}/measurement/")
        assert t.file_type == "image"
        assert t.issued_by == 1
    finally:
        s.close()


def test_issue_forbidden_for_viewer(pg_engine):
    """VIEWER 는 issue 불가(auth 재검사)."""
    s = _session(pg_engine)
    try:
        o = _make_order(s)
        with pytest.raises(UploadTicketForbidden):
            issue_ticket(s, order_id=o.id, filename="a.jpg", file_size=10,
                         user=_viewer(), category="measurement")
        s.rollback()
    finally:
        s.close()


def test_issue_rejects_missing_order_and_bad_type_size(pg_engine):
    """부재 order·허용 안 된 확장자·초과 크기는 거부(resource·type·size 재검사)."""
    s = _session(pg_engine)
    try:
        with pytest.raises(UploadTicketError):
            issue_ticket(s, order_id=999999, filename="a.jpg", file_size=10, user=_staff())
        s.rollback()
        o = _make_order(s)
        with pytest.raises(UploadTicketError):  # .exe 불허
            issue_ticket(s, order_id=o.id, filename="x.exe", file_size=10, user=_staff())
        s.rollback()
        with pytest.raises(UploadTicketError):  # 이미지 20MB 초과
            issue_ticket(s, order_id=o.id, filename="a.jpg",
                         file_size=21 * 1024 * 1024, user=_staff())
        s.rollback()
    finally:
        s.close()


def test_issue_item_active_recheck(pg_engine):
    """item_index 는 활성 identity 를 재검사한다(없거나 은퇴면 거부)."""
    s = _session(pg_engine)
    try:
        o = _make_order(s)
        with pytest.raises(UploadTicketError):  # 활성 identity 없는 슬롯
            issue_ticket(s, order_id=o.id, filename="a.jpg", file_size=10,
                         user=_staff(), item_index=0)
        s.rollback()
        ident = get_or_create_identity(s, o.id, 0)
        s.commit()
        t = issue_ticket(s, order_id=o.id, filename="a.jpg", file_size=10,
                         user=_staff(), item_index=0)
        s.commit()
        assert t.item_id == ident.id and t.item_index == 0
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# complete — 재검사·tamper·expiry·retry idempotent · REV-00
# --------------------------------------------------------------------------- #
def test_complete_creates_attachment_and_bumps_order(pg_engine):
    """complete 는 첨부 생성 + Order version 1회 bump + ticket COMPLETED."""
    s = _session(pg_engine)
    try:
        o = _make_order(s)
        assert o.mutation_version == 1
        t = issue_ticket(s, order_id=o.id, filename="a.jpg", file_size=1000, user=_staff())
        s.commit()
        ticket, att = complete_ticket(s, ticket_id=t.id, object_key=t.object_key,
                                      user=_staff(), file_size=1000)
        s.commit()
        s.refresh(o)
        assert ticket.state == "COMPLETED" and ticket.completed_at is not None
        assert att.storage_key == t.object_key and att.file_size == 1000
        assert o.mutation_version == 2
    finally:
        s.close()


def test_complete_retry_idempotent(pg_engine):
    """재확정은 no-op — 중복 첨부/Order version bump 0, 최초 첨부 반환."""
    s = _session(pg_engine)
    try:
        o = _make_order(s)
        t = issue_ticket(s, order_id=o.id, filename="a.jpg", file_size=10, user=_staff())
        s.commit()
        _, att1 = complete_ticket(s, ticket_id=t.id, object_key=t.object_key, user=_staff())
        s.commit()
        _, att2 = complete_ticket(s, ticket_id=t.id, object_key=t.object_key, user=_staff())
        s.commit()
        s.refresh(o)
        assert att1.id == att2.id
        assert o.mutation_version == 2  # 재bump 0
        n = s.query(OrderAttachment).filter(
            OrderAttachment.storage_key == t.object_key).count()
        assert n == 1  # 중복 첨부 0
    finally:
        s.close()


def test_complete_rejects_tamper_and_expired(pg_engine):
    """key 불일치(tamper)·만료 ticket 은 확정 거부."""
    s = _session(pg_engine)
    try:
        o = _make_order(s)
        t = issue_ticket(s, order_id=o.id, filename="a.jpg", file_size=10, user=_staff())
        s.commit()
        with pytest.raises(UploadTicketError):  # tamper
            complete_ticket(s, ticket_id=t.id,
                            object_key=f"orders/{o.id}/measurement/evil.jpg", user=_staff())
        s.rollback()
        with pytest.raises(UploadTicketError):  # 만료(now>=expires_at)
            complete_ticket(s, ticket_id=t.id, object_key=t.object_key, user=_staff(),
                            now=_now() + datetime.timedelta(seconds=901))
        s.rollback()
    finally:
        s.close()


def test_complete_rejects_after_item_retire(pg_engine):
    """item-retire race: retire 가 먼저면 complete 는 은퇴 아이템 확정을 거부한다."""
    s = _session(pg_engine)
    try:
        o = _make_order(s)
        ident = get_or_create_identity(s, o.id, 0)
        s.commit()
        t = issue_ticket(s, order_id=o.id, filename="a.jpg", file_size=10,
                         user=_staff(), item_index=0)
        s.commit()
        retire_identity(s, ident.id)
        s.commit()
        with pytest.raises(UploadTicketError):
            complete_ticket(s, ticket_id=t.id, object_key=t.object_key, user=_staff())
        s.rollback()
    finally:
        s.close()


def test_complete_then_retire_keeps_attachment(pg_engine):
    """complete 가 먼저면 첨부가 활성 아이템에 묶이고, 이후 retire 는 첨부를 지우지 않는다."""
    s = _session(pg_engine)
    try:
        o = _make_order(s)
        ident = get_or_create_identity(s, o.id, 0)
        s.commit()
        t = issue_ticket(s, order_id=o.id, filename="a.jpg", file_size=10,
                         user=_staff(), item_index=0)
        s.commit()
        _, att = complete_ticket(s, ticket_id=t.id, object_key=t.object_key, user=_staff())
        s.commit()
        retire_identity(s, ident.id)
        s.commit()
        s.refresh(att)
        assert att.item_id == ident.id  # no-reuse tombstone; 첨부는 그대로
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# provider bounded scan — expired/orphan claim + STORAGE_DELETE · advisory lock
# --------------------------------------------------------------------------- #
def _expired_ticket(s, order_id, *, item_index=None) -> UploadTicket:
    """created_at 을 과거로 밀어 즉시 만료된 ISSUED 티켓을 만든다."""
    past = _now() - datetime.timedelta(seconds=1000)
    t = issue_ticket(s, order_id=order_id, filename="a.jpg", file_size=10,
                     user=_staff(), item_index=item_index, now=past)
    s.commit()
    return t


def test_provider_claims_expired_ticket_enqueues_storage_delete(pg_engine):
    """만료 ISSUED → EXPIRED + UPLOAD_TICKET STORAGE_DELETE outbox 1개."""
    s = _session(pg_engine)
    try:
        o = _make_order(s)
        t = _expired_ticket(s, o.id)
        res = run_upload_expiry_scan_once(pg_engine, limit=50)
        assert res["skipped"] == 0 and res["tickets_expired"] >= 1
        s.expire_all()
        s.refresh(t)
        assert t.state == "EXPIRED"
        n = s.query(DomainSideEffectOutbox).filter(
            DomainSideEffectOutbox.effect_type == "STORAGE_DELETE",
            DomainSideEffectOutbox.upload_ticket_id == t.id).count()
        assert n == 1
    finally:
        s.close()


def test_provider_claims_item_retired_ticket(pg_engine):
    """만료 전이라도 item 이 은퇴한 ISSUED 티켓은 provider 가 claim(EXPIRED + STORAGE_DELETE)."""
    s = _session(pg_engine)
    try:
        o = _make_order(s)
        ident = get_or_create_identity(s, o.id, 0)
        s.commit()
        t = issue_ticket(s, order_id=o.id, filename="a.jpg", file_size=10,
                         user=_staff(), item_index=0)  # 만료 전(now)
        s.commit()
        retire_identity(s, ident.id)
        s.commit()
        run_upload_expiry_scan_once(pg_engine, limit=50)
        s.expire_all()
        s.refresh(t)
        assert t.state == "EXPIRED"
        n = s.query(DomainSideEffectOutbox).filter(
            DomainSideEffectOutbox.upload_ticket_id == t.id).count()
        assert n == 1
    finally:
        s.close()


def test_provider_claims_expired_draft(pg_engine):
    """만료 DRAFT → CANCELLED + object_key 별 UPLOAD_DRAFT STORAGE_DELETE."""
    s = _session(pg_engine)
    try:
        o = _make_order(s)
        past = _now() - datetime.timedelta(hours=25)
        d = create_upload_draft(s, order_id=o.id, kind="drawing_revision",
                                object_keys=[f"orders/{o.id}/drawing/k1",
                                             f"orders/{o.id}/drawing/k2"], now=past)
        s.commit()
        run_upload_expiry_scan_once(pg_engine, limit=50)
        s.expire_all()
        s.refresh(d)
        assert d.state == "CANCELLED"
        n = s.query(DomainSideEffectOutbox).filter(
            DomainSideEffectOutbox.upload_draft_id == d.id,
            DomainSideEffectOutbox.effect_type == "STORAGE_DELETE").count()
        assert n == 2
    finally:
        s.close()


def test_provider_retry_idempotent(pg_engine):
    """provider 재호출은 중복 STORAGE_DELETE 0(이미 terminal 인 행 재claim 안 함)."""
    s = _session(pg_engine)
    try:
        o = _make_order(s)
        t = _expired_ticket(s, o.id)
        run_upload_expiry_scan_once(pg_engine, limit=50)
        res2 = run_upload_expiry_scan_once(pg_engine, limit=50)
        # 두 번째 run 은 이 티켓을 다시 집지 않는다.
        s.expire_all()
        n = s.query(DomainSideEffectOutbox).filter(
            DomainSideEffectOutbox.upload_ticket_id == t.id).count()
        assert n == 1
        assert res2["skipped"] == 0
    finally:
        s.close()


def test_provider_bounded_limit(pg_engine):
    """bounded: limit 만큼만 티켓을 처리한다(한 scan 무한 금지)."""
    s = _session(pg_engine)
    try:
        o = _make_order(s)
        for _ in range(4):
            _expired_ticket(s, o.id)
        res = run_upload_expiry_scan_once(pg_engine, limit=2)
        assert res["tickets_expired"] == 2  # limit 상한
    finally:
        s.close()


def test_provider_advisory_lock_skips_when_held(pg_engine):
    """다른 세션이 advisory lock 을 잡고 있으면 provider 는 benign skip(중복 scan 0)."""
    holder = pg_engine.connect()
    try:
        holder.execute(text("SELECT pg_advisory_lock(hashtext('foms:upload_expiry_scan'))"))
        holder.commit()
        res = run_upload_expiry_scan_once(pg_engine, limit=50)
        assert res["skipped"] == 1
    finally:
        holder.execute(text("SELECT pg_advisory_unlock(hashtext('foms:upload_expiry_scan'))"))
        holder.commit()
        holder.close()


# --------------------------------------------------------------------------- #
# worker 300s 배선 — provider dispatch · 별도 scheduler 0
# --------------------------------------------------------------------------- #
def test_worker_expiry_scan_dispatches_provider(pg_engine):
    """run_expiry_scan_once 는 outbox reclaim + 등록 provider 를 같은 scan 에서 호출한다."""
    clear_expiry_scan_providers()
    calls = []
    register_expiry_scan_provider("spy", lambda eng: calls.append(1) or {"ok": 1})
    try:
        res = run_expiry_scan_once(pg_engine)
        assert calls == [1]
        assert "reclaim" in res and res["providers"]["spy"] == {"ok": 1}
    finally:
        clear_expiry_scan_providers()


def test_no_separate_scheduler_wiring():
    """정적 증거: 런너는 provider 를 300s expiry scan 에 register 로 배선하고 별도 loop 0.

    ``run_upload_expiry_scan_once`` 를 자체 loop/thread 에서 직접 호출(``(``)하지 않고,
    provider 객체로 register 만 한다 — 300s expiry scan 이 dispatch 한다.
    """
    src = pathlib.Path(
        "tools/ops/run_domain_side_effect_outbox.py").read_text(encoding="utf-8")
    assert 'register_expiry_scan_provider("upload_expiry"' in src
    assert "run_upload_expiry_scan_once(" not in src  # 별도 직접 호출 loop 없음
    assert "--expiry-scan-interval" in src  # 기존 300s scan 재사용
