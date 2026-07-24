"""SESSION-SIGNING-STATE-00 PostgreSQL 계약 테스트 (PGTEST-00 lane).

security_signing_state singleton(id=1) EMPTY/OFF/gen0 seed·id=1 CHECK·mode CHECK·
row_version, wam_entry_nonces PK, 그리고 approval 소비로 EMPTY→READY cutover **준비**
(deadline-null·activation 없음)를 실 PostgreSQL 세션으로 검증한다. ``FOMS_TEST_DATABASE_URL``
미설정이면 skip 된다(conftest). 커밋 파일에는 비밀번호를 넣지 않는다(dev DSN 은 env).

상태를 변경하는 테스트는 rollback 으로 끝내 singleton 을 seed 상태(EMPTY/row_version=1)로
되돌려 순서 독립성을 유지한다.
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
from models import OpsApprovalRequest, SecurityPrincipalVersion, SecuritySigningState, User
from foms.services.security import ops_control_root as root_store
from foms.services.security.ops_approval import (
    compute_scope_sha256,
    consume_same_db,
    nonce_hash_from_secret,
)
from foms.services.security.signing import prepare_ops


def _session(pg_engine):
    return sessionmaker(bind=pg_engine)()


_UNAME_SEQ = [0]


def _make_admin(session):
    _UNAME_SEQ[0] += 1
    u = User(
        username=f"signadmin_{_UNAME_SEQ[0]}_{int(time.time() * 1000) % 100000}",
        password=generate_password_hash("pw-not-committed"),
        name="승인자", role="ADMIN", team=None, is_active=True,
    )
    session.add(u)
    session.commit()
    return u


# --------------------------------------------------------------------------- #
# 1. singleton seed (create_all lane): id=1, EMPTY/OFF/gen0
# --------------------------------------------------------------------------- #
def test_singleton_seeded_empty_off_gen0(pg_engine):
    s = _session(pg_engine)
    try:
        rows = s.execute(text("SELECT id, mode, maintenance_mode, generation, session_epoch, "
                              "grace_seconds, row_version FROM security_signing_state")).all()
        assert len(rows) == 1
        r = rows[0]
        assert r[0] == 1            # id (singleton)
        assert r[1] == "EMPTY"      # mode
        assert r[2] == "OFF"        # maintenance_mode
        assert r[3] == 0            # generation
        assert r[4] == 0            # session_epoch
        assert r[5] == 0            # grace_seconds
        assert r[6] == 1            # row_version
        # 미활성 경계: key/deadline/activation 은 전부 NULL.
        nulls = s.execute(text(
            "SELECT active_key_id, previous_key_id, pending_key_id, legacy_cutover_mode, "
            "legacy_flask_not_after, legacy_wam_not_after, previous_not_after, "
            "prepared_at, activated_at FROM security_signing_state WHERE id=1")).first()
        assert all(v is None for v in nulls)
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 2. singleton CHECK (id != 1 거부) + mode CHECK
# --------------------------------------------------------------------------- #
def test_singleton_check_rejects_second_row(pg_engine):
    s = _session(pg_engine)
    try:
        with pytest.raises(Exception):
            s.execute(text("INSERT INTO security_signing_state (id) VALUES (2)"))
            s.commit()
        s.rollback()
    finally:
        s.close()


def test_mode_check_rejects_invalid(pg_engine):
    s = _session(pg_engine)
    try:
        with pytest.raises(Exception):
            s.execute(text("UPDATE security_signing_state SET mode='NONSENSE' WHERE id=1"))
            s.commit()
        s.rollback()
    finally:
        s.close()


def test_maintenance_and_legacy_mode_checks(pg_engine):
    s = _session(pg_engine)
    try:
        with pytest.raises(Exception):
            s.execute(text("UPDATE security_signing_state SET maintenance_mode='BOGUS' WHERE id=1"))
            s.commit()
        s.rollback()
        with pytest.raises(Exception):
            s.execute(text("UPDATE security_signing_state SET legacy_cutover_mode='BOGUS' WHERE id=1"))
            s.commit()
        s.rollback()
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 3. wam_entry_nonces PK (중복 nonce_hash 거부)
# --------------------------------------------------------------------------- #
def test_wam_entry_nonce_pk_rejects_duplicate(pg_engine):
    s = _session(pg_engine)
    try:
        now = now_utc_naive()
        exp = now + datetime.timedelta(seconds=300)
        s.execute(text("INSERT INTO wam_entry_nonces (nonce_hash, subject_hash, expires_at) "
                       "VALUES (:n, :sub, :exp)"),
                  {"n": "a" * 64, "sub": "b" * 64, "exp": exp})
        s.commit()
        with pytest.raises(Exception):
            s.execute(text("INSERT INTO wam_entry_nonces (nonce_hash, subject_hash, expires_at) "
                           "VALUES (:n, :sub, :exp)"),
                      {"n": "a" * 64, "sub": "c" * 64, "exp": exp})
            s.commit()
        s.rollback()
        s.execute(text("DELETE FROM wam_entry_nonces WHERE nonce_hash=:n"), {"n": "a" * 64})
        s.commit()
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 4. cutover prepare: approval 소비로 EMPTY→READY (deadline-null, activation 없음)
# --------------------------------------------------------------------------- #
def test_cutover_prepare_empty_to_ready_via_approval(pg_engine):
    s = _session(pg_engine)
    try:
        admin = _make_admin(s)
        pv = s.query(SecurityPrincipalVersion).filter_by(user_id=admin.id).one().version

        row = prepare_ops.read_state(s)
        assert row.mode == "EMPTY"
        ver, gen = row.row_version, row.generation  # 1, 0

        artifact_sha = "e" * 64
        scope = prepare_ops.build_scope(
            "SIGNING_CUTOVER_PREPARE", "cutover_prepare", artifact_sha, ver, gen)
        secret_b64, raw = root_store.new_one_time_secret()
        now = now_utc_naive()
        approval = OpsApprovalRequest(
            id=str(uuid.uuid4()), operation_type="SIGNING_CUTOVER_PREPARE",
            scope_sha256=compute_scope_sha256(scope), artifact_sha256=artifact_sha,
            expected_version=ver, expected_generation=gen,
            nonce_hash=nonce_hash_from_secret(raw),
            expires_at=now + datetime.timedelta(seconds=600), state="APPROVED",
            approved_by_user_id=admin.id, approved_principal_version=pv, approved_at=now,
            operator_identity_hash="0" * 64, created_at=now,
        )
        s.add(approval)
        s.commit()
        approval_id = approval.id

        def _mut(session):
            appr = session.query(OpsApprovalRequest).filter_by(
                nonce_hash=nonce_hash_from_secret(raw)).one()
            return prepare_ops.prepare_cutover(
                session,
                pending_key_id="2rFCxPgnSga75Qat5uzTqA",
                prepared_key_artifact_sha256=artifact_sha,
                legacy_cutover_mode="BRIDGE",
                grace_seconds=86400,
                prepared_consumer_sha="c" * 64,
                expected_version=ver,
                updated_by_admin_user_id=appr.approved_by_user_id,
            )

        consume_same_db(
            s, operation_id="SIGNING_CUTOVER_PREPARE", scope_obj=scope,
            artifact_sha256=artifact_sha, expected_version=ver, expected_generation=gen,
            raw_secret=raw, target_mutation=_mut,
        )
        s.flush()

        st = prepare_ops.read_state(s)
        assert st.mode == "READY"                      # EMPTY→READY
        assert st.pending_key_id == "2rFCxPgnSga75Qat5uzTqA"
        assert st.prepared_key_artifact_sha256 == artifact_sha
        assert st.legacy_cutover_mode == "BRIDGE"
        assert st.grace_seconds == 86400
        assert st.prepared_consumer_sha == "c" * 64
        assert st.row_version == ver + 1
        assert st.updated_by_admin_user_id == admin.id
        assert st.prepared_at is not None
        # activation 경계: active/deadline/activated_at 은 여전히 NULL.
        assert st.active_key_id is None
        assert st.activated_at is None
        assert st.legacy_flask_not_after is None
        assert st.legacy_wam_not_after is None
        assert st.previous_not_after is None
        # approval CONSUMED.
        assert s.query(OpsApprovalRequest).filter_by(id=approval_id).one().state == "CONSUMED"
    finally:
        s.rollback()  # singleton 을 seed(EMPTY) 로 복원
        s.close()


def test_cutover_prepare_rejects_non_empty_mode(pg_engine):
    s = _session(pg_engine)
    try:
        s.execute(text("UPDATE security_signing_state SET mode='ACTIVE' WHERE id=1"))
        with pytest.raises(prepare_ops.SigningPrepareError):
            prepare_ops.prepare_cutover(
                s, pending_key_id="kid", prepared_key_artifact_sha256="e" * 64,
                legacy_cutover_mode="BRIDGE", grace_seconds=10, prepared_consumer_sha="c" * 64,
                expected_version=1, updated_by_admin_user_id=None,
            )
    finally:
        s.rollback()
        s.close()


def test_cutover_prepare_force_reauth_requires_zero_grace(pg_engine):
    s = _session(pg_engine)
    try:
        with pytest.raises(prepare_ops.SigningPrepareError):
            prepare_ops.prepare_cutover(
                s, pending_key_id="kid", prepared_key_artifact_sha256="e" * 64,
                legacy_cutover_mode="FORCE_REAUTH", grace_seconds=10, prepared_consumer_sha="c" * 64,
                expected_version=1, updated_by_admin_user_id=None,
            )
    finally:
        s.rollback()
        s.close()


# --------------------------------------------------------------------------- #
# 5. rotation prepare: CURRENT_ONLY→ROTATION_READY + generation+1 (deadline-null)
# --------------------------------------------------------------------------- #
def test_rotation_prepare_current_only_to_rotation_ready(pg_engine):
    s = _session(pg_engine)
    try:
        # 정상 rotation 진입 조건: CURRENT_ONLY + previous/pending 비어 있음.
        s.execute(text("UPDATE security_signing_state SET mode='CURRENT_ONLY', generation=5 "
                       "WHERE id=1"))
        s.flush()
        ver = prepare_ops.read_state(s).row_version
        prepare_ops.prepare_rotation(
            s, pending_key_id="nextkid", prepared_key_artifact_sha256="f" * 64,
            prepared_consumer_sha="d" * 64, expected_version=ver, updated_by_admin_user_id=None,
        )
        st = prepare_ops.read_state(s)
        assert st.mode == "ROTATION_READY"
        assert st.pending_key_id == "nextkid"
        assert st.generation == 6              # +1
        assert st.activated_at is None         # activation 없음
    finally:
        s.rollback()
        s.close()
