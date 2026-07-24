"""SESSION-SIGNING-SECRET-01 PostgreSQL 계약 테스트 (PGTEST-00 lane).

실 PostgreSQL 다중 커밋 세션으로 검증한다:

* WAM entry nonce **PostgreSQL single-use**(P1-33): 동시 2 소비 중 정확히 1건만 성공,
  재사용 거부, process-local fallback 0.
* activation 순서: READY→ACTIVE(cutover) → ACTIVE→CURRENT_ONLY(legacy finalize),
  CURRENT_ONLY→ROTATION_READY→ROTATING→CURRENT_ONLY(rotation). 각 OPS-APPROVAL 토큰 소비 +
  approver 복사 + row_version 낙관 증가.
* non-state-aware rollback STOP: 잘못된 mode 에서의 activation 은 예외로 거부.

``FOMS_TEST_DATABASE_URL`` 미설정이면 lane 자체가 skip 된다(conftest). 커밋 파일에는 비밀번호를
넣지 않는다(env 로 주입).
"""
from __future__ import annotations

import base64
import datetime
import os
import threading
import time
import uuid

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
from foms.services.security.signing import activate_ops
from foms.services.security.signing.prepare_ops import build_scope
from foms.services.security.signing.signing_key_format import key_id_from_root
from foms.services.channel_security import claim_wam_entry_nonce
import pytest


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _session(pg_engine):
    return sessionmaker(bind=pg_engine)()


@pytest.fixture(autouse=True)
def _restore_singleton(pg_engine):
    """각 테스트 뒤 공유 singleton(id=1)을 seed(EMPTY/row_version=1)로 복원하고 nonce 를 비운다.

    STATE-00 schema 테스트는 seed EMPTY 를 전제하므로(session-scoped 공유 DB), commit 하는 이
    activation 테스트가 상태를 남기지 않도록 teardown 에서 복원한다.
    """
    yield
    s = _session(pg_engine)
    try:
        s.execute(text(
            "UPDATE security_signing_state SET mode='EMPTY', maintenance_mode='OFF', "
            "maintenance_started_at=NULL, generation=0, session_epoch=0, wam_not_before=NULL, "
            "active_key_id=NULL, previous_key_id=NULL, pending_key_id=NULL, previous_not_after=NULL, "
            "legacy_cutover_mode=NULL, legacy_flask_not_after=NULL, legacy_wam_not_after=NULL, "
            "grace_seconds=0, row_version=1, prepared_consumer_sha=NULL, "
            "prepared_key_artifact_sha256=NULL, prepared_rollout_artifact_sha256=NULL, "
            "rescue_deployment_sha=NULL, prepared_at=NULL, activated_at=NULL, "
            "updated_by_admin_user_id=NULL WHERE id=1"
        ))
        s.execute(text("DELETE FROM wam_entry_nonces"))
        s.commit()
    finally:
        s.close()


_SEQ = [0]


def _make_admin(session, *, role="ADMIN", active=True):
    _SEQ[0] += 1
    user = User(
        username=f"sig_admin_{_SEQ[0]}_{int(time.time() * 1000) % 100000}",
        password=generate_password_hash("pw-not-committed"),
        name="승인자",
        role=role,
        team=None,
        is_active=active,
    )
    session.add(user)
    session.commit()
    return user


def _pv(session, user_id):
    return (
        session.query(SecurityPrincipalVersion)
        .filter(SecurityPrincipalVersion.user_id == user_id)
        .one()
        .version
    )


def _reset_state(session, **fields):
    """singleton(id=1)을 알려진 baseline 으로 재설정하고 최신 (row_version, generation) 반환."""
    row = session.query(SecuritySigningState).filter_by(id=1).one_or_none()
    if row is None:
        row = SecuritySigningState(id=1)
        session.add(row)
    defaults = dict(
        mode="EMPTY", maintenance_mode="OFF", maintenance_started_at=None,
        generation=0, session_epoch=0, wam_not_before=None,
        active_key_id=None, previous_key_id=None, pending_key_id=None,
        previous_not_after=None, legacy_cutover_mode=None,
        legacy_flask_not_after=None, legacy_wam_not_after=None, grace_seconds=0,
        prepared_consumer_sha=None, prepared_key_artifact_sha256=None,
        prepared_rollout_artifact_sha256=None, rescue_deployment_sha=None,
        prepared_at=None, activated_at=None,
    )
    defaults.update(fields)
    for k, v in defaults.items():
        setattr(row, k, v)
    session.commit()
    session.refresh(row)
    return row.row_version, row.generation


def _approved(session, approver, operation_id, scope):
    """APPROVED approval row + raw one-time secret 생성(파일 소비는 control-root 인프라 소관)."""
    now = now_utc_naive()
    _b64, raw = root_store.new_one_time_secret()
    row = OpsApprovalRequest(
        id=str(uuid.uuid4()),
        operation_type=operation_id,
        scope_sha256=compute_scope_sha256(scope),
        artifact_sha256=scope.get("artifact_sha256"),
        expected_version=scope.get("expected_version"),
        expected_generation=scope.get("expected_generation"),
        nonce_hash=nonce_hash_from_secret(raw),
        expires_at=now + datetime.timedelta(seconds=600),
        state="APPROVED",
        approved_by_user_id=approver.id,
        approved_principal_version=_pv(session, approver.id),
        approved_at=now,
        operator_identity_hash="0" * 64,
        created_at=now,
    )
    session.add(row)
    session.commit()
    return raw


def _activate(session, approver, operation_id, phase, mutation_fn):
    """activation mutation 을 approval 토큰 소비로 한 tx 에 적용(approver 복사 검증 포함)."""
    st = session.query(SecuritySigningState).filter_by(id=1).one()
    ver, gen = st.row_version, st.generation
    scope = build_scope(operation_id, phase, "a" * 64, ver, gen)
    raw = _approved(session, approver, operation_id, scope)
    nonce = nonce_hash_from_secret(raw)

    def _mut(s):
        appr = s.query(OpsApprovalRequest).filter_by(nonce_hash=nonce).one()
        return mutation_fn(s, ver, appr.approved_by_user_id)

    sha = consume_same_db(
        session, operation_id=operation_id, scope_obj=scope,
        artifact_sha256="a" * 64, expected_version=ver, expected_generation=gen,
        raw_secret=raw, target_mutation=_mut,
    )
    session.commit()
    return sha


def _root_b64():
    return base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode("ascii")


# --------------------------------------------------------------------------- #
# 1. WAM entry nonce PostgreSQL single-use (P1-33)
# --------------------------------------------------------------------------- #
def test_wam_entry_nonce_single_use_and_replay_rejected(pg_engine):
    h = "n" * 64
    assert claim_wam_entry_nonce(pg_engine, nonce_hash=h, subject_hash="s" * 64, ttl_seconds=60) is True
    # 재사용(replay)은 거부.
    assert claim_wam_entry_nonce(pg_engine, nonce_hash=h, subject_hash="s" * 64, ttl_seconds=60) is False
    with _session(pg_engine) as s:
        cnt = s.execute(
            text("SELECT count(*) FROM wam_entry_nonces WHERE nonce_hash = :h"), {"h": h}
        ).scalar()
        assert cnt == 1


def test_wam_entry_nonce_concurrent_exactly_one_wins(pg_engine):
    h = "c" * 64
    barrier = threading.Barrier(2)
    results: list[bool] = []
    lock = threading.Lock()

    def _worker():
        barrier.wait()
        ok = claim_wam_entry_nonce(pg_engine, nonce_hash=h, subject_hash="s" * 64, ttl_seconds=60)
        with lock:
            results.append(ok)

    threads = [threading.Thread(target=_worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(results) == [False, True], f"exactly one consume must win: {results}"


def test_wam_entry_nonce_expired_row_rejected(pg_engine):
    h = "e" * 64
    now = now_utc_naive()
    # 이미 만료된 nonce row 를 직접 삽입(consumed_at NULL 이지만 expires_at 과거).
    with pg_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO wam_entry_nonces (nonce_hash, subject_hash, expires_at, consumed_at, created_at) "
                "VALUES (:h, :s, :exp, NULL, :now) ON CONFLICT (nonce_hash) DO NOTHING"
            ),
            {"h": h, "s": "s" * 64, "exp": now - datetime.timedelta(seconds=10), "now": now},
        )
    # 만료 row 는 claim 되지 않는다(WHERE expires_at > now).
    assert claim_wam_entry_nonce(pg_engine, nonce_hash=h, subject_hash="s" * 64, ttl_seconds=60) is False


# --------------------------------------------------------------------------- #
# 2. activation 순서 + 토큰 소비 + approver 복사
# --------------------------------------------------------------------------- #
def test_cutover_and_legacy_finalize_order(pg_engine):
    s = _session(pg_engine)
    try:
        approver = _make_admin(s)
        cur_kid = key_id_from_root(base64.urlsafe_b64decode(_root_b64() + "="))
        # READY(BRIDGE, grace=0 → 즉시 finalize 가능) with pending key.
        _reset_state(
            s, mode="READY", legacy_cutover_mode="BRIDGE", grace_seconds=0,
            pending_key_id=cur_kid,
        )

        _activate(
            s, approver, "SIGNING_CUTOVER_ACTIVATE", "cutover_activate",
            lambda ses, ver, aid: activate_ops.activate_cutover(
                ses, mode="bridge", prepared_rollout_artifact_sha256="a" * 64,
                expected_version=ver, updated_by_admin_user_id=aid,
            ),
        )
        st = s.query(SecuritySigningState).filter_by(id=1).one()
        assert st.mode == "ACTIVE"
        assert st.active_key_id == cur_kid and st.pending_key_id is None
        assert st.legacy_flask_not_after is not None and st.legacy_wam_not_after is not None
        assert st.updated_by_admin_user_id == approver.id  # approver 복사

        # grace=0 이므로 deadline 이 지난 상태 → legacy finalize 가능.
        time.sleep(0.01)
        _activate(
            s, approver, "SIGNING_LEGACY_FINALIZE", "legacy_finalize",
            lambda ses, ver, aid: activate_ops.finalize_legacy(
                ses, prepared_rollout_artifact_sha256="b" * 64,
                expected_version=ver, updated_by_admin_user_id=aid,
            ),
        )
        st = s.query(SecuritySigningState).filter_by(id=1).one()
        assert st.mode == "CURRENT_ONLY"
        assert st.legacy_flask_not_after is None and st.legacy_cutover_mode is None
    finally:
        s.close()


def test_rotation_activate_and_finalize_order(pg_engine):
    s = _session(pg_engine)
    try:
        approver = _make_admin(s)
        old_kid = key_id_from_root(base64.urlsafe_b64decode(_root_b64() + "="))
        new_kid = key_id_from_root(base64.urlsafe_b64decode(_root_b64() + "="))
        # ROTATION_READY: active=old, pending=new, grace=0.
        _reset_state(
            s, mode="ROTATION_READY", grace_seconds=0,
            active_key_id=old_kid, pending_key_id=new_kid, generation=1,
        )

        _activate(
            s, approver, "SIGNING_ROTATION_ACTIVATE", "rotation_activate",
            lambda ses, ver, aid: activate_ops.activate_rotation(
                ses, prepared_rollout_artifact_sha256="a" * 64,
                expected_version=ver, updated_by_admin_user_id=aid,
            ),
        )
        st = s.query(SecuritySigningState).filter_by(id=1).one()
        assert st.mode == "ROTATING"
        assert st.active_key_id == new_kid and st.previous_key_id == old_kid
        assert st.pending_key_id is None and st.previous_not_after is not None

        time.sleep(0.01)
        _activate(
            s, approver, "SIGNING_ROTATION_FINALIZE", "rotation_finalize",
            lambda ses, ver, aid: activate_ops.finalize_rotation(
                ses, prepared_rollout_artifact_sha256="b" * 64,
                expected_version=ver, updated_by_admin_user_id=aid,
            ),
        )
        st = s.query(SecuritySigningState).filter_by(id=1).one()
        assert st.mode == "CURRENT_ONLY"
        assert st.previous_key_id is None and st.previous_not_after is None
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 3. non-state-aware rollback STOP (잘못된 mode 에서 activation 거부)
# --------------------------------------------------------------------------- #
def test_activation_from_wrong_mode_stops(pg_engine):
    s = _session(pg_engine)
    try:
        _reset_state(s, mode="CURRENT_ONLY", active_key_id="k" * 22)
        # rotation finalize 는 ROTATING 에서만.
        with pytest.raises(activate_ops.SigningActivationError):
            activate_ops.finalize_rotation(
                s, prepared_rollout_artifact_sha256="a" * 64,
                expected_version=s.query(SecuritySigningState).filter_by(id=1).one().row_version,
                updated_by_admin_user_id=None,
            )
        s.rollback()
        # cutover activate 는 READY 에서만.
        with pytest.raises(activate_ops.SigningActivationError):
            activate_ops.activate_cutover(
                s, mode="bridge", prepared_rollout_artifact_sha256="a" * 64,
                expected_version=s.query(SecuritySigningState).filter_by(id=1).one().row_version,
                updated_by_admin_user_id=None,
            )
        s.rollback()
    finally:
        s.close()


def test_activation_row_version_mismatch_rejected(pg_engine):
    s = _session(pg_engine)
    try:
        ver, _ = _reset_state(s, mode="READY", legacy_cutover_mode="BRIDGE", pending_key_id="k" * 22)
        with pytest.raises(activate_ops.SigningActivationError):
            activate_ops.activate_cutover(
                s, mode="bridge", prepared_rollout_artifact_sha256="a" * 64,
                expected_version=ver + 999, updated_by_admin_user_id=None,
            )
        s.rollback()
    finally:
        s.close()
