"""BACKFILL-ARTIFACT-00 PostgreSQL 계약 테스트 (PGTEST-00 lane).

run_id 결정성, 60초 lease + expired-only reclaim + active-lease 재획득 거부, batch
business write + checkpoint + heartbeat 의 same-tx 원자성, fingerprint drift STOPPED_DRIFT
(mutation 0), OPS-APPROVAL(BACKFILL_APPLY seq1 / BACKFILL_REAUTHORIZE append-only) 소비를
실 PostgreSQL 다중 커밋 세션으로 검증한다. ``FOMS_TEST_DATABASE_URL`` 미설정이면 lane 자체가
skip 된다(conftest). 커밋 파일에는 비밀번호를 넣지 않는다(env 로 주입).

DB(pg_engine)는 pytest 세션 범위라 각 테스트가 commit 한 run row 가 남는다. run_id 가
manifest/mapping 에서 결정적이므로 테스트마다 고유 identity(``ident`` fixture)로 run_id 를
분리해 상태 누수를 막는다.
"""
from __future__ import annotations

import datetime
import hashlib
import uuid

import pytest
from sqlalchemy.orm import sessionmaker
from werkzeug.security import generate_password_hash

from foms.services.datetime_kst import now_utc_naive
from models import (
    MaintenanceBackfillApproval,
    MaintenanceBackfillCheckpoint,
    MaintenanceBackfillRun,
    OpsApprovalRequest,
    SecurityPrincipalVersion,
    User,
)
from foms.services.security import ops_control_root as root_store
from foms.services.security.ops_approval import (
    compute_scope_sha256,
    nonce_hash_from_secret,
)
from foms.services.security.backfill import manifest as bmanifest
from foms.services.security.backfill import runs


# --------------------------------------------------------------------------- #
# helpers / fixtures
# --------------------------------------------------------------------------- #
def _session(pg_engine):
    return sessionmaker(bind=pg_engine)()


_SEQ = [0]


@pytest.fixture
def ident():
    """테스트별 고유 run identity(고유 manifest/mapping → 고유 run_id → 상태 격리)."""
    tok = uuid.uuid4().hex
    return {
        "packet_id": "ASSIGN-PKT",
        "phase": "ASSIGNMENT",
        "db_instance_id": "db-1",
        "manifest_sha256": hashlib.sha256(("m" + tok).encode()).hexdigest(),
        "mapping_sha256": hashlib.sha256(("p" + tok).encode()).hexdigest(),
    }


def _make_admin(session, *, role="ADMIN", active=True):
    _SEQ[0] += 1
    user = User(
        username=f"bf_admin_{_SEQ[0]}_{uuid.uuid4().hex[:6]}",
        password=generate_password_hash("pw-not-committed"),
        name="승인자",
        role=role,
        is_active=active,
    )
    session.add(user)
    session.commit()
    return user


def _principal_version(session, user_id):
    return (
        session.query(SecurityPrincipalVersion)
        .filter(SecurityPrincipalVersion.user_id == user_id)
        .one()
        .version
    )


def _approval_scope(ident, expected_run_row_version=1):
    return bmanifest.build_approval_scope(
        packet_id=ident["packet_id"],
        phase=ident["phase"],
        manifest_sha256=ident["manifest_sha256"],
        mapping_sha256=ident["mapping_sha256"],
        db_instance_id=ident["db_instance_id"],
        source_composite_sha256="s" * 64,
        expected_run_row_version=expected_run_row_version,
        masked_counts={"safe": 3, "ambiguous": 0},
    )


def _seed_ops_approval(session, admin, approval_scope, *, operation_id, expires_delta=600):
    """OPS APPROVED row + raw secret 생성(create_ops_approval_request 를 흉내)."""
    ops_scope = runs.ops_scope_for_backfill(approval_scope, operation_id)
    _b64, raw = root_store.new_one_time_secret()
    now = now_utc_naive()
    row = OpsApprovalRequest(
        id=str(uuid.uuid4()),
        operation_type=operation_id,
        scope_sha256=compute_scope_sha256(ops_scope),
        artifact_sha256=ops_scope["artifact_sha256"],
        expected_version=ops_scope["expected_version"],
        expected_generation=None,
        nonce_hash=nonce_hash_from_secret(raw),
        expires_at=now + datetime.timedelta(seconds=expires_delta),
        state="APPROVED",
        approved_by_user_id=admin.id,
        approved_principal_version=_principal_version(session, admin.id),
        approved_at=now,
        operator_identity_hash="0" * 64,
        created_at=now,
    )
    session.add(row)
    session.commit()
    return row, raw


# --------------------------------------------------------------------------- #
# 1. run_id 결정성
# --------------------------------------------------------------------------- #
def test_run_id_deterministic(pg_engine, ident):
    m, p = ident["manifest_sha256"], ident["mapping_sha256"]
    a = runs.compute_run_id("ASSIGN-PKT", "ASSIGNMENT", m, p)
    b = runs.compute_run_id("ASSIGN-PKT", "ASSIGNMENT", m, p)
    c = runs.compute_run_id("ASSIGN-PKT", "ASSIGNMENT", m, "q" * 64)
    assert a == b and a != c and len(a) == 64
    s = _session(pg_engine)
    try:
        run = runs.ensure_run(s, total_rows=5, **ident)
        s.commit()
        assert run.run_id == a and run.state == "PENDING"
        run2 = runs.ensure_run(s, total_rows=5, **ident)  # idempotent 재확보.
        s.commit()
        assert run2.run_id == a
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 2. lease: 60초 · expired reclaim only · active 재획득 거부
# --------------------------------------------------------------------------- #
def test_lease_acquire_and_active_reacquire_rejected(pg_engine, ident):
    s = _session(pg_engine)
    try:
        run = runs.ensure_run(s, **ident)
        run_id = run.run_id
        run.current_approval_seq = 1  # apply 소비를 흉내(lease 는 active approval 필요).
        s.commit()

        raw_a, _ = runs.new_lease_token()
        now = now_utc_naive()
        leased = runs.acquire_lease(
            s, run_id, owner_identity_hash=runs.owner_hash("host-A"), raw_token=raw_a, now=now
        )
        s.commit()
        assert leased.state == "RUNNING"
        assert leased.lease_expires_at == now + datetime.timedelta(seconds=runs.LEASE_TTL_SECONDS)
        # raw lease token 은 저장되지 않는다(hash 만).
        assert run.lease_token_hash == runs._lease_token_hash(raw_a)
        assert run.lease_token_hash != raw_a.hex()

        # active·미만료 lease 를 다른 token 으로 재획득 → 거부.
        raw_b, _ = runs.new_lease_token()
        with pytest.raises(runs.BackfillLeaseError):
            runs.acquire_lease(
                s, run_id, owner_identity_hash=runs.owner_hash("host-B"), raw_token=raw_b, now=now
            )
        s.rollback()
    finally:
        s.close()


def test_lease_expired_reclaim_only(pg_engine, ident):
    s = _session(pg_engine)
    try:
        run = runs.ensure_run(s, **ident)
        run_id = run.run_id
        run.current_approval_seq = 1
        s.commit()

        raw_a, _ = runs.new_lease_token()
        t0 = now_utc_naive()
        runs.acquire_lease(s, run_id, owner_identity_hash=runs.owner_hash("A"), raw_token=raw_a, now=t0)
        s.commit()

        # lease 만료 후(> 60초) 다른 owner 가 reclaim → 허용.
        t1 = t0 + datetime.timedelta(seconds=runs.LEASE_TTL_SECONDS + 1)
        raw_b, _ = runs.new_lease_token()
        reclaimed = runs.acquire_lease(
            s, run_id, owner_identity_hash=runs.owner_hash("B"), raw_token=raw_b, now=t1
        )
        s.commit()
        assert reclaimed.lease_token_hash == runs._lease_token_hash(raw_b)
        assert reclaimed.lease_expires_at == t1 + datetime.timedelta(seconds=runs.LEASE_TTL_SECONDS)
    finally:
        s.close()


def test_lease_requires_active_approval(pg_engine, ident):
    s = _session(pg_engine)
    try:
        run = runs.ensure_run(s, **ident)  # current_approval_seq=0
        s.commit()
        raw, _ = runs.new_lease_token()
        with pytest.raises(runs.BackfillLeaseError):
            runs.acquire_lease(s, run.run_id, owner_identity_hash=runs.owner_hash("A"), raw_token=raw)
        s.rollback()
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 3. batch write + checkpoint + heartbeat = same tx
# --------------------------------------------------------------------------- #
def test_batch_write_checkpoint_heartbeat_same_tx(pg_engine, ident):
    s = _session(pg_engine)
    try:
        run = runs.ensure_run(s, total_rows=2, **ident)
        run_id = run.run_id
        run.current_approval_seq = 1
        s.commit()
        raw, _ = runs.new_lease_token()
        runs.acquire_lease(s, run_id, owner_identity_hash=runs.owner_hash("A"), raw_token=raw)
        s.commit()

        writes = []
        outcome = runs.write_batch(
            s, run_id, raw_token=raw,
            expected_fingerprint="fp", live_fingerprint="fp",
            batch_business_write=lambda _s: writes.append(1),
            completed_delta=2, batch_seq=1, checkpoint_sha256="cp" * 32,
        )
        s.commit()
        assert outcome.applied and not outcome.stopped_drift and outcome.completed_rows == 2
        assert writes == [1]

        # checkpoint + run 진행이 같은 commit 으로 함께 보였다.
        chk = _session(pg_engine)
        try:
            cps = chk.query(MaintenanceBackfillCheckpoint).filter_by(run_id=run_id).all()
            r = chk.query(MaintenanceBackfillRun).filter_by(run_id=run_id).one()
            assert len(cps) == 1 and cps[0].completed_rows == 2
            assert r.completed_rows == 2 and r.heartbeat_at is not None
        finally:
            chk.close()
    finally:
        s.close()


def test_batch_write_without_lease_rejected(pg_engine, ident):
    s = _session(pg_engine)
    try:
        run = runs.ensure_run(s, total_rows=1, **ident)
        run_id = run.run_id
        run.current_approval_seq = 1
        s.commit()
        wrong, _ = runs.new_lease_token()  # lease 미획득 상태의 임의 token
        writes = []
        with pytest.raises(runs.BackfillLeaseError):
            runs.write_batch(
                s, run_id, raw_token=wrong, expected_fingerprint="fp", live_fingerprint="fp",
                batch_business_write=lambda _s: writes.append(1),
                completed_delta=1, batch_seq=1, checkpoint_sha256="c" * 64,
            )
        s.rollback()
        assert writes == []
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 4. fingerprint drift → STOPPED_DRIFT, business mutation 0
# --------------------------------------------------------------------------- #
def test_fingerprint_drift_stops_before_write(pg_engine, ident):
    s = _session(pg_engine)
    try:
        run = runs.ensure_run(s, total_rows=5, **ident)
        run_id = run.run_id
        run.current_approval_seq = 1
        s.commit()
        raw, _ = runs.new_lease_token()
        runs.acquire_lease(s, run_id, owner_identity_hash=runs.owner_hash("A"), raw_token=raw)
        s.commit()

        writes = []
        outcome = runs.write_batch(
            s, run_id, raw_token=raw,
            expected_fingerprint="fp-baseline", live_fingerprint="fp-DRIFTED",
            batch_business_write=lambda _s: writes.append(1),
            completed_delta=1, batch_seq=1, checkpoint_sha256="c" * 64,
        )
        s.commit()  # STOPPED_DRIFT 상태를 유지.
        assert outcome.stopped_drift and not outcome.applied
        assert writes == [], "drift 시 business write 는 호출되지 않는다"

        chk = _session(pg_engine)
        try:
            r = chk.query(MaintenanceBackfillRun).filter_by(run_id=run_id).one()
            assert r.state == "STOPPED_DRIFT" and r.last_error_code == "FINGERPRINT_DRIFT"
            assert r.completed_rows == 0
            assert chk.query(MaintenanceBackfillCheckpoint).filter_by(run_id=run_id).count() == 0
        finally:
            chk.close()
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 5. OPS-APPROVAL 소비: BACKFILL_APPLY seq1 + REAUTHORIZE append-only
# --------------------------------------------------------------------------- #
def test_backfill_apply_consume_creates_seq1(pg_engine, ident):
    s = _session(pg_engine)
    try:
        admin = _make_admin(s)
        run = runs.ensure_run(s, **ident)
        run_id = run.run_id
        s.commit()
        assert run.row_version == 1

        scope = _approval_scope(ident, expected_run_row_version=1)
        row, raw = _seed_ops_approval(s, admin, scope, operation_id="BACKFILL_APPLY")

        seq, _sha = runs.consume_backfill_apply(
            s, run_id, approval_scope=scope, approval_id=row.id,
            admin_principal_version=_principal_version(s, admin.id), raw_secret=raw,
        )
        s.commit()
        assert seq == 1
        s.refresh(run)
        assert run.current_approval_seq == 1

        approvals = s.query(MaintenanceBackfillApproval).filter_by(run_id=run_id).all()
        assert len(approvals) == 1 and approvals[0].kind == "APPLY" and approvals[0].seq == 1
        s.refresh(row)
        assert row.state == "CONSUMED"  # OPS approval 이 one-time 소비됨.
    finally:
        s.close()


def test_reauthorize_appends_seq2_and_row_is_append_only(pg_engine, ident):
    s = _session(pg_engine)
    try:
        admin = _make_admin(s)
        admin2 = _make_admin(s)
        run = runs.ensure_run(s, **ident)
        run_id = run.run_id
        s.commit()

        # APPLY seq1 (expected_run_row_version=1).
        scope1 = _approval_scope(ident, expected_run_row_version=1)
        row1, raw1 = _seed_ops_approval(s, admin, scope1, operation_id="BACKFILL_APPLY")
        runs.consume_backfill_apply(
            s, run_id, approval_scope=scope1, approval_id=row1.id,
            admin_principal_version=_principal_version(s, admin.id), raw_secret=raw1,
        )
        s.commit()
        s.refresh(run)
        assert run.current_approval_seq == 1 and run.row_version == 2

        # REAUTHORIZE seq2 — 현재 run row_version(2) CAS.
        scope2 = _approval_scope(ident, expected_run_row_version=run.row_version)
        row2, raw2 = _seed_ops_approval(s, admin2, scope2, operation_id="BACKFILL_REAUTHORIZE")
        seq2, _sha = runs.reauthorize(
            s, run_id, approval_scope=scope2, approval_id=row2.id,
            admin_principal_version=_principal_version(s, admin2.id),
            reason_code="ADMIN_ROTATION", raw_secret=raw2,
        )
        s.commit()
        assert seq2 == 2
        approvals = (
            s.query(MaintenanceBackfillApproval)
            .filter_by(run_id=run_id).order_by(MaintenanceBackfillApproval.seq).all()
        )
        assert [a.kind for a in approvals] == ["APPLY", "REAUTHORIZE"]

        # append-only: 기존 approval row UPDATE 는 DB trigger 가 거부.
        upd = _session(pg_engine)
        try:
            target = upd.query(MaintenanceBackfillApproval).filter_by(run_id=run_id, seq=1).one()
            target.reason_code = "TAMPER"
            with pytest.raises(Exception):
                upd.commit()
            upd.rollback()
        finally:
            upd.close()

        # append-only: 기존 approval row DELETE 도 거부.
        dele = _session(pg_engine)
        try:
            row_seq1 = dele.query(MaintenanceBackfillApproval).filter_by(run_id=run_id, seq=1).one()
            dele.delete(row_seq1)
            with pytest.raises(Exception):
                dele.commit()
            dele.rollback()
        finally:
            dele.close()

        # trigger 거부 후에도 두 approval row 는 온전하다.
        chk = _session(pg_engine)
        try:
            assert chk.query(MaintenanceBackfillApproval).filter_by(run_id=run_id).count() == 2
        finally:
            chk.close()
    finally:
        s.close()


def test_reauthorize_stale_row_version_rejected(pg_engine, ident):
    """run row_version CAS 불일치 → REAUTHORIZE 거부(mutation 0)."""
    s = _session(pg_engine)
    try:
        admin = _make_admin(s)
        run = runs.ensure_run(s, **ident)
        run_id = run.run_id
        s.commit()
        scope1 = _approval_scope(ident, expected_run_row_version=1)
        row1, raw1 = _seed_ops_approval(s, admin, scope1, operation_id="BACKFILL_APPLY")
        runs.consume_backfill_apply(
            s, run_id, approval_scope=scope1, approval_id=row1.id,
            admin_principal_version=_principal_version(s, admin.id), raw_secret=raw1,
        )
        s.commit()  # run.row_version → 2

        # 잘못된 expected_run_row_version(1) 로 REAUTHORIZE → CAS 불일치 거부.
        stale = _approval_scope(ident, expected_run_row_version=1)
        row2, raw2 = _seed_ops_approval(s, admin, stale, operation_id="BACKFILL_REAUTHORIZE")
        with pytest.raises(runs.BackfillRunError):
            runs.reauthorize(
                s, run_id, approval_scope=stale, approval_id=row2.id,
                admin_principal_version=_principal_version(s, admin.id),
                reason_code="X", raw_secret=raw2,
            )
        s.rollback()
        chk = _session(pg_engine)
        try:
            assert chk.query(MaintenanceBackfillApproval).filter_by(run_id=run_id).count() == 1
        finally:
            chk.close()
    finally:
        s.close()
