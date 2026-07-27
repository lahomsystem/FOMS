"""SIDEFX-00 PostgreSQL 계약 테스트 (PGTEST-00 lane).

typed-domain side-effect outbox 의 정본 계약을 실 PostgreSQL 다중 커밋 세션으로 고정한다:

* one-of FK CHECK matrix — 각 source_domain 이 자기 FK 만 허용, mismatch/다중/전무 거부,
  실 FK 도메인(order_event/notification_event/chat_attachment)의 orphan 거부.
* dedupe unique ``(effect_type, dedupe_key)`` — 중복 insert 거부, NULL 은 다행 허용,
  effect_type 로 scope.
* queue/lease — ``FOR UPDATE SKIP LOCKED`` PENDING pickup, lease 획득/만료 reclaim,
  status 전이(PENDING→PROCESSING→DONE).
* tx 원자성 — repository insert 후 business tx rollback 시 outbox 도 rollback.
* retention — DONE completed_at>30d / DEAD dead_at>180d 만 purge, PENDING/PROCESSING·
  최근 terminal 은 보존.

``FOMS_TEST_DATABASE_URL`` 미설정이면 conftest 가 lane 을 skip 한다. 커밋 파일에는
비밀번호를 넣지 않는다(env 로 주입). producer/consumer(worker)는 하류 몫 — 이 테스트가
그들이 의존할 스키마 계약을 정본으로 고정한다.
"""
from __future__ import annotations

import datetime
import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from foms.services.datetime_kst import now_utc_naive
from foms.services.sidefx_outbox import (
    SideEffectValidationError,
    enqueue_side_effect,
    purge_retention,
)
from models import (
    DomainSideEffectOutbox,
    Order,
    OrderEvent,
    OrderImportArtifact,
    UploadDraft,
    UploadTicket,
)

# 부모 테이블이 없는(=FK 없는) 도메인/컬럼 — one-of CHECK 를 FK setup 없이 isolate 한다.
# UPLOAD_DRAFT 는 UPLOAD-INTENT-01 이, UPLOAD_TICKET 은 UPLOAD-02 가, ORDER_IMPORT_ARTIFACT 는
# ORDER-IMPORT-01 이 각각 부모 테이블 + 실 FK 를 부착하며 아래 FK_DOMAINS 로 이동했다(orphan 거부).
NO_FK_DOMAINS = [
    ("WIZARD_PENDING", "wizard_pending_id"),
    ("ADDRESS_LEARNING", "address_learning_request_id"),
]
# 실 FK 도메인 — orphan 을 DB 가 거부한다.
FK_DOMAINS = [
    ("ORDER_EVENT", "order_event_id"),
    ("NOTIFICATION_EVENT", "notification_event_id"),
    ("CHAT_ATTACHMENT", "chat_attachment_id"),
    ("UPLOAD_DRAFT", "upload_draft_id"),
    ("UPLOAD_TICKET", "upload_ticket_id"),
    ("ORDER_IMPORT_ARTIFACT", "order_import_artifact_id"),
]


def _session(pg_engine):
    return sessionmaker(bind=pg_engine)()


def _now():
    return now_utc_naive()


def _marker() -> str:
    """세션 공유 pg_engine 에서 테스트 간 오염을 피하는 유니크 effect_type."""
    return "T_" + uuid.uuid4().hex


def _row(**over) -> DomainSideEffectOutbox:
    """no-FK 도메인(WIZARD_PENDING) 기준 최소 유효 outbox 행."""
    base = dict(
        source_domain="WIZARD_PENDING",
        wizard_pending_id=1,
        effect_type=_marker(),
        payload={},
        status="PENDING",
        attempts=0,
        available_at=_now(),
        created_at=_now(),
    )
    base.update(over)
    return DomainSideEffectOutbox(**base)


def _make_order_event(session) -> OrderEvent:
    o = Order(received_date="2026-07-24", customer_name="홍길동",
              phone="010-0000-0000", address="서울", product="침대")
    session.add(o)
    session.commit()
    ev = OrderEvent(order_id=o.id, event_type="STAGE_CHANGED", created_at=_now())
    session.add(ev)
    session.commit()
    return ev


def _make_upload_draft(session) -> UploadDraft:
    """UPLOAD_DRAFT 도메인 실 FK happy-path 용 실존 부모 upload_draft 행."""
    o = Order(received_date="2026-07-24", customer_name="홍길동",
              phone="010-0000-0000", address="서울", product="침대")
    session.add(o)
    session.commit()
    d = UploadDraft(order_id=o.id, kind="drawing_revision", state="DRAFT",
                    created_at=_now(), expires_at=_now() + datetime.timedelta(hours=24))
    session.add(d)
    session.commit()
    return d


def _make_upload_ticket(session) -> UploadTicket:
    """UPLOAD_TICKET 도메인 실 FK happy-path 용 실존 부모 upload_ticket 행."""
    o = Order(received_date="2026-07-24", customer_name="홍길동",
              phone="010-0000-0000", address="서울", product="침대")
    session.add(o)
    session.commit()
    t = UploadTicket(
        order_id=o.id, category="measurement",
        object_key="orders/%d/measurement/%s.jpg" % (o.id, uuid.uuid4().hex),
        filename="a.jpg", file_type="image", file_size=10, state="ISSUED",
        created_at=_now(), expires_at=_now() + datetime.timedelta(seconds=900),
    )
    session.add(t)
    session.commit()
    return t


def _make_order_import_artifact(session) -> OrderImportArtifact:
    """ORDER_IMPORT_ARTIFACT 도메인 실 FK happy-path 용 실존 부모 artifact 행."""
    a = OrderImportArtifact(
        file_hash=uuid.uuid4().hex, filename="orders.xlsx", row_count=1,
        state="COMPLETED",
        source_object_key="order_imports/1/%s.xlsx" % uuid.uuid4().hex,
        created_at=_now(), expires_at=_now() + datetime.timedelta(hours=24),
    )
    session.add(a)
    session.commit()
    return a


# --------------------------------------------------------------------------- #
# 1. one-of FK CHECK matrix
# --------------------------------------------------------------------------- #
def test_check_accepts_each_domain_own_fk(pg_engine):
    """각 no-FK 도메인이 자기 FK 컬럼만 채웠을 때 accept."""
    s = _session(pg_engine)
    try:
        for domain, col in NO_FK_DOMAINS:
            r = DomainSideEffectOutbox(
                source_domain=domain, effect_type=_marker(), payload={},
                available_at=_now(), created_at=_now(),
            )
            setattr(r, col, 12345)
            s.add(r)
            s.commit()
            assert r.id is not None
    finally:
        s.close()


def test_order_event_valid_with_real_parent(pg_engine):
    """실 FK 도메인(ORDER_EVENT) happy path — 실존 부모 order_event 참조."""
    s = _session(pg_engine)
    try:
        ev = _make_order_event(s)
        r = DomainSideEffectOutbox(
            source_domain="ORDER_EVENT", order_event_id=ev.id,
            effect_type=_marker(), payload={"x": 1},
            available_at=_now(), created_at=_now(),
        )
        s.add(r)
        s.commit()
        assert r.id is not None
    finally:
        s.close()


def test_upload_draft_valid_with_real_parent(pg_engine):
    """실 FK 도메인(UPLOAD_DRAFT) happy path — 실존 부모 upload_draft 참조(UPLOAD-INTENT-01)."""
    s = _session(pg_engine)
    try:
        draft = _make_upload_draft(s)
        r = DomainSideEffectOutbox(
            source_domain="UPLOAD_DRAFT", upload_draft_id=draft.id,
            effect_type=_marker(), payload={"x": 1},
            available_at=_now(), created_at=_now(),
        )
        s.add(r)
        s.commit()
        assert r.id is not None
    finally:
        s.close()


def test_upload_ticket_valid_with_real_parent(pg_engine):
    """실 FK 도메인(UPLOAD_TICKET) happy path — 실존 부모 upload_ticket 참조(UPLOAD-02)."""
    s = _session(pg_engine)
    try:
        ticket = _make_upload_ticket(s)
        r = DomainSideEffectOutbox(
            source_domain="UPLOAD_TICKET", upload_ticket_id=ticket.id,
            effect_type=_marker(), payload={"x": 1},
            available_at=_now(), created_at=_now(),
        )
        s.add(r)
        s.commit()
        assert r.id is not None
    finally:
        s.close()


def test_order_import_artifact_valid_with_real_parent(pg_engine):
    """실 FK 도메인(ORDER_IMPORT_ARTIFACT) happy path — 실존 부모 artifact 참조(ORDER-IMPORT-01)."""
    s = _session(pg_engine)
    try:
        art = _make_order_import_artifact(s)
        r = DomainSideEffectOutbox(
            source_domain="ORDER_IMPORT_ARTIFACT", order_import_artifact_id=art.id,
            effect_type=_marker(), payload={"x": 1},
            available_at=_now(), created_at=_now(),
        )
        s.add(r)
        s.commit()
        assert r.id is not None
    finally:
        s.close()


def test_check_rejects_domain_fk_mismatch(pg_engine):
    """source_domain 과 다른 FK 컬럼을 채우면 CHECK 거부."""
    s = _session(pg_engine)
    try:
        # 순수 CHECK(도메인 mismatch) 검증 — no-FK 컬럼(address_learning_request_id)을 써서
        # FK orphan 이 CHECK 보다 먼저 걸리는 것을 피한다.
        r = DomainSideEffectOutbox(
            source_domain="WIZARD_PENDING", address_learning_request_id=5,  # 잘못된 컬럼
            effect_type=_marker(), payload={},
            available_at=_now(), created_at=_now(),
        )
        s.add(r)
        with pytest.raises(IntegrityError):
            s.commit()
        s.rollback()
    finally:
        s.close()


def test_check_rejects_two_non_null_fks(pg_engine):
    """FK 두 개 non-null 이면 CHECK 거부(정확히 하나만 허용)."""
    s = _session(pg_engine)
    try:
        # 두 컬럼 모두 no-FK 로 채워 순수 two-non-null CHECK 위반만 남긴다(FK orphan 배제).
        r = DomainSideEffectOutbox(
            source_domain="WIZARD_PENDING", wizard_pending_id=1, address_learning_request_id=2,
            effect_type=_marker(), payload={},
            available_at=_now(), created_at=_now(),
        )
        s.add(r)
        with pytest.raises(IntegrityError):
            s.commit()
        s.rollback()
    finally:
        s.close()


def test_check_rejects_zero_non_null_fk(pg_engine):
    """FK 전부 NULL 이면 CHECK 거부(orphan-less source 금지)."""
    s = _session(pg_engine)
    try:
        r = DomainSideEffectOutbox(
            source_domain="WIZARD_PENDING",  # FK 미설정
            effect_type=_marker(), payload={},
            available_at=_now(), created_at=_now(),
        )
        s.add(r)
        with pytest.raises(IntegrityError):
            s.commit()
        s.rollback()
    finally:
        s.close()


@pytest.mark.parametrize("domain,col", FK_DOMAINS)
def test_orphan_fk_rejected(pg_engine, domain, col):
    """실 FK 도메인은 존재하지 않는 부모 id 를 orphan 으로 거부한다."""
    s = _session(pg_engine)
    try:
        r = DomainSideEffectOutbox(
            source_domain=domain, effect_type=_marker(), payload={},
            available_at=_now(), created_at=_now(),
        )
        setattr(r, col, 999_999_999)  # 부모 미존재
        s.add(r)
        with pytest.raises(IntegrityError):
            s.commit()
        s.rollback()
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 2. dedupe unique
# --------------------------------------------------------------------------- #
def test_dedupe_rejects_duplicate(pg_engine):
    """같은 (effect_type, dedupe_key) 두 번째 insert 거부."""
    s = _session(pg_engine)
    try:
        et = _marker()
        s.add(_row(effect_type=et, dedupe_key="k1"))
        s.commit()
        s.add(_row(effect_type=et, dedupe_key="k1"))
        with pytest.raises(IntegrityError):
            s.commit()
        s.rollback()
    finally:
        s.close()


def test_dedupe_null_allows_many(pg_engine):
    """dedupe_key NULL 행은 partial unique 라 collapse 되지 않는다."""
    s = _session(pg_engine)
    try:
        et = _marker()
        s.add(_row(effect_type=et, dedupe_key=None))
        s.add(_row(effect_type=et, dedupe_key=None))
        s.commit()  # 예외 없음
        n = s.query(DomainSideEffectOutbox).filter_by(effect_type=et).count()
        assert n == 2
    finally:
        s.close()


def test_dedupe_scoped_by_effect_type(pg_engine):
    """같은 dedupe_key 라도 effect_type 이 다르면 허용(복합 unique)."""
    s = _session(pg_engine)
    try:
        key = "shared-" + uuid.uuid4().hex
        s.add(_row(effect_type=_marker(), dedupe_key=key))
        s.add(_row(effect_type=_marker(), dedupe_key=key))
        s.commit()  # 예외 없음
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 3. queue / lease / status 전이
# --------------------------------------------------------------------------- #
def test_queue_pickup_lease_and_reclaim(pg_engine):
    """SKIP LOCKED PENDING pickup → lease 획득 → 만료 reclaim → status 전이."""
    s = _session(pg_engine)
    try:
        base = _now()
        et = _marker()
        ids = []
        for i in range(3):
            r = _row(effect_type=et,
                     available_at=base - datetime.timedelta(seconds=10 - i))
            s.add(r)
            s.commit()
            ids.append(r.id)

        # oldest PENDING 을 SKIP LOCKED 로 pickup → lease → PROCESSING.
        picked = (
            s.query(DomainSideEffectOutbox)
            .filter(DomainSideEffectOutbox.effect_type == et,
                    DomainSideEffectOutbox.status == "PENDING")
            .order_by(DomainSideEffectOutbox.available_at.asc())
            .with_for_update(skip_locked=True)
            .first()
        )
        assert picked is not None
        picked.status = "PROCESSING"
        picked.lease_owner_hash = "w" * 64
        picked.lease_token = str(uuid.uuid4())
        picked.lease_expires_at = _now() + datetime.timedelta(seconds=60)
        picked.attempts = picked.attempts + 1
        s.commit()

        # lease 만료 → reclaim 쿼리가 회수 대상으로 찾음.
        picked.lease_expires_at = _now() - datetime.timedelta(seconds=1)
        s.commit()
        reclaimable = (
            s.query(DomainSideEffectOutbox)
            .filter(DomainSideEffectOutbox.status == "PROCESSING",
                    DomainSideEffectOutbox.lease_expires_at < _now())
            .with_for_update(skip_locked=True)
            .all()
        )
        assert picked.id in [r.id for r in reclaimable]
        for r in reclaimable:
            r.status = "PENDING"
            r.lease_owner_hash = None
            r.lease_token = None
            r.lease_expires_at = None
        s.commit()
        assert s.get(DomainSideEffectOutbox, picked.id).status == "PENDING"

        # 정상 완료 전이 → DONE.
        picked.status = "DONE"
        picked.completed_at = _now()
        s.commit()
        assert s.get(DomainSideEffectOutbox, picked.id).status == "DONE"
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 4. tx 원자성 (repository)
# --------------------------------------------------------------------------- #
def test_enqueue_rolls_back_with_business_tx(pg_engine):
    """business tx rollback 시 outbox insert 도 rollback(원자성)."""
    et = _marker()
    s = _session(pg_engine)
    try:
        row = enqueue_side_effect(
            s, source_domain="WIZARD_PENDING", source_id=7,
            effect_type=et, payload={"key": "x"},
        )
        assert row.id is not None  # flush 됨
        s.rollback()
    finally:
        s.close()
    s2 = _session(pg_engine)
    try:
        assert s2.query(DomainSideEffectOutbox).filter_by(effect_type=et).count() == 0
    finally:
        s2.close()


def test_enqueue_commits_and_sets_only_one_fk(pg_engine):
    """commit 시 1행 persist, 지정 도메인 FK 만 채워짐."""
    et = _marker()
    s = _session(pg_engine)
    try:
        ticket = _make_upload_ticket(s)  # UPLOAD_TICKET 은 실 FK — 실존 부모 필요.
        tid = ticket.id
        enqueue_side_effect(
            s, source_domain="UPLOAD_TICKET", source_id=tid,
            effect_type=et, payload={}, dedupe_key="d-" + et,
            provider_idempotency_key="prov-1", schema_version=2,
        )
        s.commit()
    finally:
        s.close()
    s2 = _session(pg_engine)
    try:
        rows = s2.query(DomainSideEffectOutbox).filter_by(effect_type=et).all()
        assert len(rows) == 1
        r = rows[0]
        assert r.upload_ticket_id == tid
        assert r.wizard_pending_id is None and r.order_event_id is None
        assert r.status == "PENDING" and r.schema_version == 2
        assert r.provider_idempotency_key == "prov-1"
    finally:
        s2.close()


def test_enqueue_rejects_unknown_domain(pg_engine):
    s = _session(pg_engine)
    try:
        with pytest.raises(SideEffectValidationError):
            enqueue_side_effect(s, source_domain="BOGUS", source_id=1,
                                effect_type="E", payload={})
    finally:
        s.close()


def test_enqueue_rejects_non_dict_payload(pg_engine):
    s = _session(pg_engine)
    try:
        with pytest.raises(SideEffectValidationError):
            enqueue_side_effect(s, source_domain="WIZARD_PENDING", source_id=1,
                                effect_type="E", payload=["not", "a", "dict"])
    finally:
        s.close()


def test_enqueue_orphan_fk_rejected(pg_engine):
    """repository 경유 실 FK orphan 도 호출자 tx 안에서 IntegrityError."""
    s = _session(pg_engine)
    try:
        with pytest.raises(IntegrityError):
            enqueue_side_effect(s, source_domain="ORDER_EVENT", source_id=999_999_999,
                                effect_type="E", payload={})
        s.rollback()
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 5. retention
# --------------------------------------------------------------------------- #
def test_purge_retention(pg_engine):
    """DONE>30d / DEAD>180d 만 삭제, 최근 terminal·PENDING 보존."""
    s = _session(pg_engine)
    try:
        now = _now()
        et = _marker()
        old_done = _row(effect_type=et, status="DONE",
                        completed_at=now - datetime.timedelta(days=31))
        recent_done = _row(effect_type=et, status="DONE",
                           completed_at=now - datetime.timedelta(days=1))
        old_dead = _row(effect_type=et, status="DEAD",
                        dead_at=now - datetime.timedelta(days=181))
        recent_dead = _row(effect_type=et, status="DEAD",
                           dead_at=now - datetime.timedelta(days=1))
        pending = _row(effect_type=et, status="PENDING")
        for r in (old_done, recent_done, old_dead, recent_dead, pending):
            s.add(r)
        s.commit()
        ids = {n: r.id for n, r in (
            ("old_done", old_done), ("recent_done", recent_done),
            ("old_dead", old_dead), ("recent_dead", recent_dead),
            ("pending", pending))}

        result = purge_retention(s, now=now)
        s.commit()

        assert result["done_purged"] >= 1 and result["dead_purged"] >= 1
        assert s.get(DomainSideEffectOutbox, ids["old_done"]) is None
        assert s.get(DomainSideEffectOutbox, ids["old_dead"]) is None
        assert s.get(DomainSideEffectOutbox, ids["recent_done"]) is not None
        assert s.get(DomainSideEffectOutbox, ids["recent_dead"]) is not None
        assert s.get(DomainSideEffectOutbox, ids["pending"]) is not None
    finally:
        s.close()
