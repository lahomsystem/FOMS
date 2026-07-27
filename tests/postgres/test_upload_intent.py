"""UPLOAD-INTENT-01 PostgreSQL 계약 테스트 (PGTEST-00 lane).

pre-file 업로드 DRAFT 수명주기의 정본 계약을 실 PostgreSQL 세션으로 고정한다:

* **create**: 파일 업로드 전 DRAFT id 발급, idempotent(같은 intent 재요청은 동일 DRAFT·
  중복 생성 0), 24h expiry, Order 불변(queue 비노출·side-effect 0).
* **cancel**: CANCELLED(terminal) 마킹, 멱등(이미 terminal 이면 no-op), Order 불변.
* **finalize**: DRAFT→FINALIZED + Order ``mutation_version`` 1회 bump(REV-00), 멱등 no-op
  (재확정 시 추가 bump 0). CANCELLED/EXPIRED DRAFT 확정 거부.
* **lazy expiry**: 만료는 조회 시 :func:`effective_state` 로 계산하고 scheduler 가 상태를
  기록하지 않는다.
* **no scheduler/object cleanup/ticket**: create/cancel/finalize 는 side-effect outbox 를
  0 개 만들고(=ticket/consumer/cleanup 미배선), storage 삭제/scheduler 를 배선하지 않는다.

``FOMS_TEST_DATABASE_URL`` 미설정이면 conftest 가 lane 을 skip 한다. 커밋 파일에는 비밀번호를
넣지 않는다(env 로 주입).
"""
from __future__ import annotations

import ast
import datetime
import pathlib
import uuid

import pytest
from sqlalchemy.orm import sessionmaker

from foms.services.datetime_kst import now_utc_naive
from foms.services.orders.upload_intent import (
    UploadDraftError,
    cancel_upload_draft,
    create_upload_draft,
    effective_state,
    finalize_upload_draft,
)
from models import DomainSideEffectOutbox, Order, UploadDraft


def _session(pg_engine):
    return sessionmaker(bind=pg_engine)()


def _now():
    return now_utc_naive()


def _make_order(session) -> Order:
    """mutation_version=1 신규 주문(finalize bump 기준선)."""
    o = Order(received_date="2026-07-24", customer_name="홍길동",
              phone="010-0000-0000", address="서울", product="침대")
    session.add(o)
    session.commit()
    return o


def _key() -> str:
    return "idem-" + uuid.uuid4().hex


# --------------------------------------------------------------------------- #
# create — pre-file id · idempotent · 24h · Order 불변(queue 비노출)
# --------------------------------------------------------------------------- #
def test_create_issues_draft_id_before_file(pg_engine):
    """파일 없이 create 만으로 DRAFT id 가 발급된다(state=DRAFT)."""
    s = _session(pg_engine)
    try:
        o = _make_order(s)
        d = create_upload_draft(s, order_id=o.id, kind="drawing_revision")
        s.commit()
        assert d.id is not None
        assert d.state == "DRAFT"
        assert (d.object_keys or []) == []  # 파일 전 — key 없음
    finally:
        s.close()


def test_create_is_idempotent(pg_engine):
    """같은 (order,kind,key) 재요청은 동일 DRAFT 반환·중복 생성 0."""
    s = _session(pg_engine)
    try:
        o = _make_order(s)
        key = _key()
        d1 = create_upload_draft(s, order_id=o.id, kind="as_cycle", idempotency_key=key)
        s.commit()
        d2 = create_upload_draft(s, order_id=o.id, kind="as_cycle", idempotency_key=key)
        s.commit()
        assert d1.id == d2.id
        n = (s.query(UploadDraft)
             .filter(UploadDraft.order_id == o.id, UploadDraft.idempotency_key == key)
             .count())
        assert n == 1
    finally:
        s.close()


def test_create_sets_24h_expiry(pg_engine):
    """expires_at == created_at + 24h."""
    s = _session(pg_engine)
    try:
        o = _make_order(s)
        base = _now()
        d = create_upload_draft(s, order_id=o.id, kind="drawing_revision", now=base)
        s.commit()
        assert d.expires_at == base + datetime.timedelta(hours=24)
    finally:
        s.close()


def test_create_leaves_order_unchanged_and_queue_invisible(pg_engine):
    """create 는 Order version·structured_data 불변, side-effect outbox 0(queue 비노출)."""
    s = _session(pg_engine)
    try:
        o = _make_order(s)
        assert o.mutation_version == 1
        sd_before = o.structured_data
        before_outbox = s.query(DomainSideEffectOutbox).count()

        create_upload_draft(s, order_id=o.id, kind="drawing_revision")
        s.commit()

        s.refresh(o)
        assert o.mutation_version == 1  # Order 불변
        assert o.structured_data == sd_before  # draft 가 order 로 누출되지 않음
        assert s.query(DomainSideEffectOutbox).count() == before_outbox  # 큐/side-effect 0
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# cancel — terminal · idempotent · Order 불변
# --------------------------------------------------------------------------- #
def test_cancel_marks_terminal_idempotent_order_unchanged(pg_engine):
    """cancel → CANCELLED, 재취소 no-op(추가 bump 0), Order 불변."""
    s = _session(pg_engine)
    try:
        o = _make_order(s)
        d = create_upload_draft(s, order_id=o.id, kind="as_cycle")
        s.commit()

        cancel_upload_draft(s, d.id)
        s.commit()
        assert d.state == "CANCELLED"
        rv = d.row_version

        cancel_upload_draft(s, d.id)  # 이미 terminal → no-op
        s.commit()
        assert d.state == "CANCELLED" and d.row_version == rv

        s.refresh(o)
        assert o.mutation_version == 1  # cancel 은 Order 불변
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# finalize — final command 만 Order version 1회 bump(REV-00)
# --------------------------------------------------------------------------- #
def test_finalize_bumps_order_version_once(pg_engine):
    """finalize 만 Order version 1회 bump, DRAFT→FINALIZED, 재확정 no-op(추가 bump 0)."""
    s = _session(pg_engine)
    try:
        o = _make_order(s)
        d = create_upload_draft(s, order_id=o.id, kind="drawing_revision")
        s.commit()
        s.refresh(o)
        assert o.mutation_version == 1  # create 는 bump 안 함

        finalize_upload_draft(s, d.id)
        s.commit()
        s.refresh(o)
        assert o.mutation_version == 2  # 정확히 1회 bump
        assert d.state == "FINALIZED"

        finalize_upload_draft(s, d.id)  # 멱등 no-op
        s.commit()
        s.refresh(o)
        assert o.mutation_version == 2  # 재bump 0
    finally:
        s.close()


def test_create_and_cancel_do_not_bump_order_version(pg_engine):
    """create·cancel 는 Order version 을 올리지 않는다(finalize 만)."""
    s = _session(pg_engine)
    try:
        o = _make_order(s)
        d = create_upload_draft(s, order_id=o.id, kind="as_cycle")
        s.commit()
        cancel_upload_draft(s, d.id)
        s.commit()
        s.refresh(o)
        assert o.mutation_version == 1
    finally:
        s.close()


def test_finalize_rejects_cancelled_and_expired(pg_engine):
    """CANCELLED·만료(EXPIRED) DRAFT 는 확정 불가(version bump 없음)."""
    s = _session(pg_engine)
    try:
        o = _make_order(s)
        cancelled = create_upload_draft(s, order_id=o.id, kind="drawing_revision")
        s.commit()
        cancel_upload_draft(s, cancelled.id)
        s.commit()
        with pytest.raises(UploadDraftError):
            finalize_upload_draft(s, cancelled.id)
        s.rollback()

        past = _now() - datetime.timedelta(hours=25)
        expired = create_upload_draft(s, order_id=o.id, kind="as_cycle", now=past)
        s.commit()
        with pytest.raises(UploadDraftError):
            finalize_upload_draft(s, expired.id)
        s.rollback()

        s.refresh(o)
        assert o.mutation_version == 1  # 실패 확정은 version 불변
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# lazy expiry — 조회 시 판정, scheduler 미기록
# --------------------------------------------------------------------------- #
def test_lazy_expiry_no_scheduler_write(pg_engine):
    """만료 DRAFT 는 effective_state=EXPIRED 이지만 DB state 는 DRAFT(무기록)."""
    s = _session(pg_engine)
    try:
        o = _make_order(s)
        past = _now() - datetime.timedelta(hours=25)
        d = create_upload_draft(s, order_id=o.id, kind="drawing_revision", now=past)
        s.commit()

        assert effective_state(d) == "EXPIRED"  # lazy 판정
        s.refresh(d)
        assert d.state == "DRAFT"  # scheduler 가 상태를 기록하지 않음
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# no scheduler / object cleanup / ticket (spy 0)
# --------------------------------------------------------------------------- #
def test_lifecycle_produces_no_side_effects(pg_engine):
    """create/cancel/finalize 는 side-effect outbox 를 0 개 만든다(ticket/cleanup 미배선)."""
    s = _session(pg_engine)
    try:
        before = s.query(DomainSideEffectOutbox).count()
        o = _make_order(s)

        d_fin = create_upload_draft(s, order_id=o.id, kind="drawing_revision")
        s.commit()
        finalize_upload_draft(s, d_fin.id)
        s.commit()

        d_can = create_upload_draft(s, order_id=o.id, kind="as_cycle")
        s.commit()
        cancel_upload_draft(s, d_can.id)
        s.commit()

        assert s.query(DomainSideEffectOutbox).count() == before  # outbox 0 → ticket/side-effect/cleanup 미배선
    finally:
        s.close()


def test_service_has_no_storage_ticket_or_scheduler_wiring():
    """정적 증거: 서비스 모듈이 storage 삭제/ticket/scheduler 를 **import** 하지 않는다(경계).

    docstring/주석의 언급이 아니라 실제 import 구문만 검사한다(AST). create/cancel/finalize
    가 object cleanup·upload_ticket·만료 scheduler 로 배선되지 않음을 정적으로 고정한다.
    """
    src = pathlib.Path("foms/services/orders/upload_intent.py").read_text(encoding="utf-8")
    imported: list[str] = []
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            imported += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
            imported += [a.name for a in node.names]
    blob = " ".join(imported).lower()
    for forbidden in ("storage", "upload_ticket", "scheduler", "delete_object"):
        assert forbidden not in blob, f"upload_intent 서비스가 금지 배선 '{forbidden}' 을 import 함"
