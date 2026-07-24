"""DELETE-RETENTION-01 PostgreSQL 계약 테스트 (PGTEST-00 lane).

soft-delete + retention 경과 주문의 **OPS-APPROVAL 게이트 하드 삭제**를 실 PostgreSQL 로
검증한다: dry-run 기본(소비 0·삭제 0), 승인 토큰 소비 후에만 실행·one-time, exact
order-ID·첨부 file hash·before snapshot·expected count hash 검증(불일치 시 중단·삭제 0),
soft-delete + retention 경과만 삭제, advisory·batch·resume. ``FOMS_TEST_DATABASE_URL``
미설정이면 lane 자체가 skip(conftest). 커밋 파일에 비밀번호 0(env 로 주입).

주문 변수는 int id 로 보관한다 — 하드 삭제 commit 후 ORM 인스턴스의 ``.id`` 접근은
refresh 를 유발해 ObjectDeletedError 가 나므로, 생성 즉시 id 를 확정한다.
"""
from __future__ import annotations

import datetime
import time
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker
from werkzeug.security import generate_password_hash

from foms.services.datetime_kst import now_utc_naive
from models import Order, OrderAttachment, OpsApprovalRequest, SecurityPrincipalVersion, User
from foms.services.orders.soft_delete import restore_order, soft_delete_order
from foms.services.security import ops_control_root as root_store
from foms.services.security.ops_approval import (
    ApprovalConsumeError,
    compute_scope_sha256,
    nonce_hash_from_secret,
)
from foms.services.orders.delete_retention import (
    DeleteRetentionDriftError,
    _assert_fk_coverage,
    _ops_scope,
    apply_delete_retention,
    build_delete_plan,
    select_retention_targets,
)


# --------------------------------------------------------------------------- #
# fixtures / helpers
# --------------------------------------------------------------------------- #
@pytest.fixture(autouse=True)
def _reset(pg_engine):
    """각 테스트 후 orders/approvals 를 청소해 대상 스캔 격리(throwaway DB)."""
    yield
    s = sessionmaker(bind=pg_engine)()
    try:
        s.execute(text("DELETE FROM order_mutation_read_resources"))
        s.execute(text("UPDATE chat_rooms SET order_id = NULL"))
        s.execute(text("DELETE FROM orders"))
        s.execute(text("DELETE FROM ops_approval_requests"))
        s.commit()
    finally:
        s.close()


def _session(pg_engine):
    return sessionmaker(bind=pg_engine)()


_SEQ = [0]


def _admin(session, *, role="ADMIN", active=True):
    """admin User 생성(insert trigger 가 principal version 1 seed)."""
    _SEQ[0] += 1
    u = User(
        username=f"dr_admin_{_SEQ[0]}_{int(time.time() * 1000) % 100000}",
        password=generate_password_hash("pw-not-committed"),
        name="승인자",
        role=role,
        team=None,
        is_active=active,
    )
    session.add(u)
    session.commit()
    return u


def _pv(session, user_id):
    return (
        session.query(SecurityPrincipalVersion)
        .filter(SecurityPrincipalVersion.user_id == user_id)
        .one()
    ).version


def _order(session, *, customer="홍길동") -> int:
    """Order 생성 후 int id 반환(하드 삭제 후 ORM refresh 회피)."""
    o = Order(
        received_date="2026-01-01",
        customer_name=customer,
        phone="010-1234-5678",
        address="서울시",
        product="붙박이장",
        status="RECEIVED",
    )
    session.add(o)
    session.commit()
    return int(o.id)


def _soft_delete(session, order_id, actor_id, *, days_ago):
    """order 를 days_ago 일 전 시각으로 soft-delete(그만큼 retention 경과 모사)."""
    when = now_utc_naive() - datetime.timedelta(days=days_ago)
    soft_delete_order(session, order_id=order_id, actor_user_id=actor_id, reason="retention", now=when)
    session.commit()


def _attach(session, order_id, *, filename="a.jpg"):
    a = OrderAttachment(
        order_id=order_id, filename=filename, file_type="image",
        category="measurement", file_size=123, storage_key=f"uploads/{filename}",
    )
    session.add(a)
    session.commit()
    return a


def _approve(session, approver, plan, *, now=None, state="APPROVED", expires=600):
    """plan 에 바인딩된 OPS-APPROVAL row(+raw secret) 생성. artifact_sha256=plan_sha256."""
    now = now or now_utc_naive()
    scope = _ops_scope(plan)
    _b64, raw = root_store.new_one_time_secret()
    row = OpsApprovalRequest(
        id=str(uuid.uuid4()),
        operation_type="DELETE_RETENTION_APPLY",
        scope_sha256=compute_scope_sha256(scope),
        artifact_sha256=plan["plan_sha256"],
        expected_version=plan["expected_count"],
        expected_generation=None,
        nonce_hash=nonce_hash_from_secret(raw),
        expires_at=now + datetime.timedelta(seconds=expires),
        state=state,
        approved_by_user_id=approver.id if state in ("APPROVED", "RESERVED") else None,
        approved_principal_version=_pv(session, approver.id) if state in ("APPROVED", "RESERVED") else None,
        approved_at=now if state in ("APPROVED", "RESERVED") else None,
        operator_identity_hash="0" * 64,
        created_at=now,
    )
    session.add(row)
    session.commit()
    return row, raw


def _exists(session, order_id):
    return session.execute(
        text("SELECT deleted_at FROM orders WHERE id = :id"), {"id": order_id}
    ).one_or_none()


# --------------------------------------------------------------------------- #
# 0. FK coverage (참조 무결성 fail-closed 계약이 green)
# --------------------------------------------------------------------------- #
def test_fk_coverage_is_complete():
    _assert_fk_coverage()  # 미처리 NOT NULL non-cascade 참조자 있으면 raise


# --------------------------------------------------------------------------- #
# 1. dry-run 기본: 승인 미소비·삭제 0
# --------------------------------------------------------------------------- #
def test_dry_run_default_consumes_nothing_and_deletes_nothing(pg_engine):
    s = _session(pg_engine)
    try:
        admin = _admin(s)
        a = _order(s); b = _order(s)
        _soft_delete(s, a, admin.id, days_ago=400)
        _soft_delete(s, b, admin.id, days_ago=400)
        plan = build_delete_plan(s, retention_days=365)
        assert plan["expected_count"] == 2
        row, raw = _approve(s, admin, plan)

        res = apply_delete_retention(s, approved_plan=plan, raw_secret=raw, apply=False)
        s.commit()

        assert res.applied is False and res.consumed is False and res.deleted == 0
        assert _exists(s, a) is not None and _exists(s, b) is not None
        s.refresh(row)
        assert row.state == "APPROVED"  # 토큰 미소비
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 2. apply: 승인 소비 후 정확히 대상만 하드 삭제
# --------------------------------------------------------------------------- #
def test_apply_consumes_token_and_hard_deletes_only_targets(pg_engine):
    s = _session(pg_engine)
    try:
        admin = _admin(s)
        aged1 = _order(s); aged2 = _order(s)
        recent = _order(s)          # soft-delete 됐지만 미경과
        live = _order(s)            # 삭제 안 됨
        _soft_delete(s, aged1, admin.id, days_ago=400)
        _soft_delete(s, aged2, admin.id, days_ago=400)
        _soft_delete(s, recent, admin.id, days_ago=1)

        plan = build_delete_plan(s, retention_days=365)
        assert plan["exact_order_ids"] == sorted([aged1, aged2])
        row, raw = _approve(s, admin, plan)

        res = apply_delete_retention(s, approved_plan=plan, raw_secret=raw, apply=True)
        s.commit()

        assert res.applied and res.consumed and res.deleted == 2
        assert _exists(s, aged1) is None and _exists(s, aged2) is None
        assert _exists(s, recent) is not None      # 미경과 soft-delete 보존
        assert _exists(s, live) is not None         # live 보존
        s.refresh(row)
        assert row.state == "CONSUMED" and row.result_sha256 == res.result_sha256
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 3. 승인 없이 삭제 0 (PENDING 토큰은 소비 불가)
# --------------------------------------------------------------------------- #
def test_unapproved_pending_token_cannot_delete(pg_engine):
    s = _session(pg_engine)
    try:
        admin = _admin(s)
        a = _order(s)
        _soft_delete(s, a, admin.id, days_ago=400)
        plan = build_delete_plan(s, retention_days=365)
        _row, raw = _approve(s, admin, plan, state="PENDING")

        with pytest.raises(ApprovalConsumeError):
            apply_delete_retention(s, approved_plan=plan, raw_secret=raw, apply=True)
        s.rollback()

        assert _exists(s, a) is not None  # 삭제 0
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 4. one-time: 소비된 토큰 재사용 거부
# --------------------------------------------------------------------------- #
def test_token_is_one_time(pg_engine):
    s = _session(pg_engine)
    try:
        admin = _admin(s)
        a = _order(s); b = _order(s)
        _soft_delete(s, a, admin.id, days_ago=400)
        _soft_delete(s, b, admin.id, days_ago=400)
        plan = build_delete_plan(s, retention_days=365)
        _row, raw = _approve(s, admin, plan)
        apply_delete_retention(s, approved_plan=plan, raw_secret=raw, apply=True)
        s.commit()  # 토큰 CONSUMED

        # 새 대상으로 valid 한 plan2 를 만들어도, 소비된 토큰(raw)은 거부되어야 한다.
        c = _order(s); d = _order(s)
        _soft_delete(s, c, admin.id, days_ago=400)
        _soft_delete(s, d, admin.id, days_ago=400)
        plan2 = build_delete_plan(s, retention_days=365)

        with pytest.raises(ApprovalConsumeError):
            apply_delete_retention(s, approved_plan=plan2, raw_secret=raw, apply=True)
        s.rollback()

        assert _exists(s, c) is not None and _exists(s, d) is not None  # 삭제 0
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 5. expected count hash 불일치 → 중단·삭제 0 (승인 후 대상 복구)
# --------------------------------------------------------------------------- #
def test_count_drift_after_restore_aborts(pg_engine):
    s = _session(pg_engine)
    try:
        admin = _admin(s)
        a = _order(s); b = _order(s)
        _soft_delete(s, a, admin.id, days_ago=400)
        _soft_delete(s, b, admin.id, days_ago=400)
        plan = build_delete_plan(s, retention_days=365)
        _row, raw = _approve(s, admin, plan)

        # 승인 후 b 를 복구 → live 대상 집합 {a} → count/set drift.
        restore_order(s, order_id=b, actor_user_id=admin.id)
        s.commit()

        with pytest.raises(DeleteRetentionDriftError):
            apply_delete_retention(s, approved_plan=plan, raw_secret=raw, apply=True)
        s.rollback()

        assert _exists(s, a) is not None and _exists(s, b) is not None  # 삭제 0
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 6. before snapshot / file hash drift → plan hash 불일치 중단
# --------------------------------------------------------------------------- #
def test_snapshot_or_attachment_drift_aborts(pg_engine):
    s = _session(pg_engine)
    try:
        admin = _admin(s)
        a = _order(s)
        _attach(s, a, filename="before.jpg")
        _soft_delete(s, a, admin.id, days_ago=400)
        plan = build_delete_plan(s, retention_days=365)
        # 첨부에 ref_sha256(파일 해시)·before snapshot 이 실제 담겼는지 확인.
        snap = next(o for o in plan["orders"] if o["order_id"] == a)
        assert snap["order"]["customer_name"] == "홍길동"           # before snapshot
        assert snap["attachments"][0]["ref_sha256"]                 # 첨부 file hash
        assert plan["dependency_totals"]["order_attachments.order_id"] == 1

        _row, raw = _approve(s, admin, plan)

        # 승인 후 첨부 메타데이터 변경 → plan_sha256 drift.
        s.execute(text("UPDATE order_attachments SET storage_key = 'uploads/tampered.jpg' WHERE order_id = :id"), {"id": a})
        s.commit()

        with pytest.raises(DeleteRetentionDriftError):
            apply_delete_retention(s, approved_plan=plan, raw_secret=raw, apply=True)
        s.rollback()
        assert _exists(s, a) is not None
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 7. soft-delete + retention 경과만 대상 (select)
# --------------------------------------------------------------------------- #
def test_only_soft_deleted_and_elapsed_selected(pg_engine):
    s = _session(pg_engine)
    try:
        admin = _admin(s)
        live = _order(s)
        recent = _order(s)
        aged = _order(s)
        _soft_delete(s, recent, admin.id, days_ago=10)
        _soft_delete(s, aged, admin.id, days_ago=400)

        targets = select_retention_targets(s, retention_days=365)
        assert targets == [aged]
        assert live not in targets and recent not in targets
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 8. batch: batch_size=1 로도 전량 삭제
# --------------------------------------------------------------------------- #
def test_batch_delete_all(pg_engine):
    s = _session(pg_engine)
    try:
        admin = _admin(s)
        ids = []
        for _ in range(5):
            oid = _order(s)
            _soft_delete(s, oid, admin.id, days_ago=400)
            ids.append(oid)
        plan = build_delete_plan(s, retention_days=365)
        assert plan["expected_count"] == 5
        _row, raw = _approve(s, admin, plan)

        res = apply_delete_retention(s, approved_plan=plan, raw_secret=raw, apply=True, batch_size=1)
        s.commit()

        assert res.deleted == 5
        for oid in ids:
            assert _exists(s, oid) is None
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 9. resume: 실패한 apply 는 토큰을 소비하지 않고 rollback → 재실행 가능
# --------------------------------------------------------------------------- #
def test_failed_apply_leaves_token_for_resume(pg_engine):
    s = _session(pg_engine)
    try:
        admin = _admin(s)
        a = _order(s); b = _order(s)
        _soft_delete(s, a, admin.id, days_ago=400)
        _soft_delete(s, b, admin.id, days_ago=400)
        plan = build_delete_plan(s, retention_days=365)
        row, raw = _approve(s, admin, plan)

        # 잘못된 plan(count 조작)로 첫 시도 → drift 중단, rollback.
        bad = dict(plan)
        bad["expected_count"] = 99
        bad["count_sha256"] = "0" * 64
        with pytest.raises(DeleteRetentionDriftError):
            apply_delete_retention(s, approved_plan=bad, raw_secret=raw, apply=True)
        s.rollback()
        s.refresh(row)
        assert row.state == "APPROVED"  # 토큰 미소비 → resume 가능

        # 올바른 plan + 같은 토큰으로 재실행 → 성공(resume).
        res = apply_delete_retention(s, approved_plan=plan, raw_secret=raw, apply=True)
        s.commit()
        assert res.deleted == 2 and res.consumed
        assert _exists(s, a) is None and _exists(s, b) is None
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 10. advisory lock: apply 진행 중(미commit) 다른 연결의 동일 락 획득 실패
# --------------------------------------------------------------------------- #
def test_advisory_lock_serializes_apply(pg_engine):
    s = _session(pg_engine)
    other = pg_engine.connect()
    try:
        admin = _admin(s)
        a = _order(s)
        _soft_delete(s, a, admin.id, days_ago=400)
        plan = build_delete_plan(s, retention_days=365)
        _row, raw = _approve(s, admin, plan)

        # apply(미commit): xact advisory lock 을 s 의 tx 가 보유.
        apply_delete_retention(s, approved_plan=plan, raw_secret=raw, apply=True)

        got = other.execute(
            text("SELECT pg_try_advisory_xact_lock(hashtext(:k))"),
            {"k": "foms:delete_retention_apply"},
        ).scalar()
        assert got is False  # 동시 apply 는 직렬화됨

        s.commit()  # 락 해제
    finally:
        other.close()
        s.close()
