"""AUTH-ACCOUNT-01 auth-rate key bootstrap/rotation PostgreSQL 계약 테스트 (PGTEST-00 lane).

실 PostgreSQL 다중 커밋 세션으로 SESSION-SIGNING-STATE-00 동형 상태기계를 검증한다:

* BOOTSTRAP prepare(EMPTY→READY)/activate(READY→ACTIVE): state ``version`` 증가·키 활성.
* ROTATION prepare(pending·``generation`` 증가)/activate(dual accept·grace)/finalize(구 키 폐기).
* OPS-APPROVAL 게이트: 승인 없이/재소비(one-time) 시 mutation 0.
* encrypted artifact: DB 컬럼에 plaintext 키 0(AES-256-GCM envelope), 변조 시 fail-closed.
* rate limiter BRIDGE: 미engage 시 bucket 키 byte-identical, ROTATING 중 dual accept.

``FOMS_TEST_DATABASE_URL`` 미설정이면 lane 자체가 skip 된다(conftest). 커밋 파일에는 비밀번호를
넣지 않는다(dev DSN·master key 모두 env 로 주입).
"""
from __future__ import annotations

import base64
import datetime
import json
import os
import time
import uuid

from sqlalchemy import text
from sqlalchemy.orm import sessionmaker
from werkzeug.security import generate_password_hash

import pytest

from foms.services.datetime_kst import now_utc_naive
from models import AuthRateKeyState, OpsApprovalRequest, SecurityPrincipalVersion, User
from foms.services.security import ops_control_root as root_store
from foms.services.security.ops_approval import (
    ApprovalConsumeError,
    compute_scope_sha256,
    consume_same_db,
    nonce_hash_from_secret,
)
from foms.services.security.auth_rate import crypto, key_state, state_ops


# --------------------------------------------------------------------------- #
# env: dev master key(env-only, 커밋 비밀 0). engage 플래그는 bridge 테스트에서만.
# --------------------------------------------------------------------------- #
_MASTER = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode("ascii")
os.environ[crypto.ENV_MASTER] = _MASTER
_MASTER_BYTES = crypto.resolve_master_key()


def _session(pg_engine):
    return sessionmaker(bind=pg_engine)()


@pytest.fixture(autouse=True)
def _restore_singleton(pg_engine):
    """각 테스트 뒤 공유 singleton(id=1)을 EMPTY seed 로 복원(session-scoped 공유 DB)."""
    yield
    s = _session(pg_engine)
    try:
        s.execute(text(
            "UPDATE auth_rate_key_state SET mode='EMPTY', version=1, generation=0, "
            "active_key_id=NULL, previous_key_id=NULL, pending_key_id=NULL, "
            "active_key_ciphertext=NULL, previous_key_ciphertext=NULL, pending_key_ciphertext=NULL, "
            "previous_not_after=NULL, prepared_key_artifact_sha256=NULL, "
            "prepared_rollout_artifact_sha256=NULL, prepared_at=NULL, activated_at=NULL, "
            "updated_by_admin_user_id=NULL WHERE id=1"
        ))
        s.commit()
    finally:
        s.close()


@pytest.fixture(autouse=True)
def _clear_engage(monkeypatch):
    """기본은 미engage(BRIDGE byte-identical). bridge 테스트만 명시적으로 engage 한다."""
    monkeypatch.delenv(key_state.ENV_ENGAGED, raising=False)


_SEQ = [0]


def _make_admin(session, *, role="ADMIN", active=True):
    _SEQ[0] += 1
    user = User(
        username=f"authrate_admin_{_SEQ[0]}_{int(time.time() * 1000) % 100000}",
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


def _approved(session, approver, operation_id, scope):
    """APPROVED approval row + raw one-time secret 생성."""
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


def _consume(session, approver, operation_id, phase, artifact_sha, mutation_fn):
    """transition mutation 을 approval 토큰 소비로 한 tx 에 적용(approver 복사 검증 포함)."""
    st = session.query(AuthRateKeyState).filter_by(id=1).one()
    ver, gen = st.version, st.generation
    scope = state_ops.build_scope(operation_id, phase, artifact_sha, ver, gen)
    raw = _approved(session, approver, operation_id, scope)
    nonce = nonce_hash_from_secret(raw)

    def _mut(s):
        appr = s.query(OpsApprovalRequest).filter_by(nonce_hash=nonce).one()
        return mutation_fn(s, ver, appr.approved_by_user_id)

    sha = consume_same_db(
        session, operation_id=operation_id, scope_obj=scope,
        artifact_sha256=artifact_sha, expected_version=ver, expected_generation=gen,
        raw_secret=raw, target_mutation=_mut,
    )
    session.commit()
    return sha


def _mint_key():
    """새 rate key material + fingerprint + encrypted envelope + artifact sha 반환."""
    material = crypto.new_key_material()
    kid = crypto.fingerprint(material)
    envelope = crypto.encrypt_key_material(material, _MASTER_BYTES, key_id=kid)
    ct_json = json.dumps(envelope, sort_keys=True, separators=(",", ":"))
    art_sha = crypto.sha256_hex(ct_json.encode("utf-8"))
    return material, kid, ct_json, art_sha


def _bootstrap_to_active(session, approver):
    """EMPTY→READY→ACTIVE 로 첫 키를 활성화하고 (material, kid) 반환."""
    material, kid, ct_json, art_sha = _mint_key()
    _consume(
        session, approver, "AUTH_RATE_BOOTSTRAP_PREPARE", "bootstrap_prepare", art_sha,
        lambda s, ver, aid: state_ops.bootstrap_prepare(
            s, pending_key_id=kid, pending_key_ciphertext=ct_json,
            prepared_key_artifact_sha256=art_sha, expected_version=ver,
            updated_by_admin_user_id=aid,
        ),
    )
    _consume(
        session, approver, "AUTH_RATE_BOOTSTRAP_ACTIVATE", "bootstrap_activate", "a" * 64,
        lambda s, ver, aid: state_ops.bootstrap_activate(
            s, prepared_rollout_artifact_sha256="a" * 64, expected_version=ver,
            updated_by_admin_user_id=aid,
        ),
    )
    return material, kid


# --------------------------------------------------------------------------- #
# 1. BOOTSTRAP prepare/activate
# --------------------------------------------------------------------------- #
def test_bootstrap_prepare_and_activate(pg_engine):
    s = _session(pg_engine)
    try:
        approver = _make_admin(s)
        material, kid, ct_json, art_sha = _mint_key()

        st = s.query(AuthRateKeyState).filter_by(id=1).one()
        assert st.mode == "EMPTY" and st.version == 1 and st.generation == 0
        v0 = st.version

        _consume(
            s, approver, "AUTH_RATE_BOOTSTRAP_PREPARE", "bootstrap_prepare", art_sha,
            lambda ses, ver, aid: state_ops.bootstrap_prepare(
                ses, pending_key_id=kid, pending_key_ciphertext=ct_json,
                prepared_key_artifact_sha256=art_sha, expected_version=ver,
                updated_by_admin_user_id=aid,
            ),
        )
        st = s.query(AuthRateKeyState).filter_by(id=1).one()
        assert st.mode == "READY"
        assert st.version == v0 + 1          # state version++
        assert st.generation == 1            # 첫 키 generation
        assert st.pending_key_id == kid
        assert st.pending_key_ciphertext == ct_json
        assert st.active_key_id is None
        assert st.updated_by_admin_user_id == approver.id  # approver 복사

        _consume(
            s, approver, "AUTH_RATE_BOOTSTRAP_ACTIVATE", "bootstrap_activate", "a" * 64,
            lambda ses, ver, aid: state_ops.bootstrap_activate(
                ses, prepared_rollout_artifact_sha256="a" * 64, expected_version=ver,
                updated_by_admin_user_id=aid,
            ),
        )
        st = s.query(AuthRateKeyState).filter_by(id=1).one()
        assert st.mode == "ACTIVE"
        assert st.version == v0 + 2
        assert st.active_key_id == kid
        assert st.pending_key_id is None and st.pending_key_ciphertext is None
        assert st.activated_at is not None
        # 활성 키가 실제로 복호화되어 원본 material 과 일치.
        env = json.loads(st.active_key_ciphertext)
        assert crypto.decrypt_key_material(env, _MASTER_BYTES, key_id=kid) == material
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 2. ROTATION prepare/activate(dual accept)/finalize
# --------------------------------------------------------------------------- #
def test_rotation_dual_accept_then_finalize(pg_engine):
    s = _session(pg_engine)
    try:
        approver = _make_admin(s)
        old_mat, old_kid = _bootstrap_to_active(s, approver)
        st = s.query(AuthRateKeyState).filter_by(id=1).one()
        assert st.generation == 1
        gen_after_bootstrap = st.generation

        new_mat, new_kid, new_ct, new_art = _mint_key()
        _consume(
            s, approver, "AUTH_RATE_ROTATION_PREPARE", "rotation_prepare", new_art,
            lambda ses, ver, aid: state_ops.rotation_prepare(
                ses, pending_key_id=new_kid, pending_key_ciphertext=new_ct,
                prepared_key_artifact_sha256=new_art, expected_version=ver,
                updated_by_admin_user_id=aid,
            ),
        )
        st = s.query(AuthRateKeyState).filter_by(id=1).one()
        assert st.mode == "ROTATION_READY"
        assert st.generation == gen_after_bootstrap + 1   # generation++
        assert st.pending_key_id == new_kid and st.active_key_id == old_kid

        # activate with a real grace window → dual accept.
        _consume(
            s, approver, "AUTH_RATE_ROTATION_ACTIVATE", "rotation_activate", "b" * 64,
            lambda ses, ver, aid: state_ops.rotation_activate(
                ses, grace_seconds=60, prepared_rollout_artifact_sha256="b" * 64,
                expected_version=ver, updated_by_admin_user_id=aid,
            ),
        )
        st = s.query(AuthRateKeyState).filter_by(id=1).one()
        assert st.mode == "ROTATING"
        assert st.active_key_id == new_kid and st.previous_key_id == old_kid
        assert st.pending_key_id is None
        assert st.previous_not_after is not None and st.previous_not_after > now_utc_naive()

        # dual accept: 활성 + 이전 키 둘 다 복호화되어 accepted 집합에 존재.
        accepted = key_state.accepted_key_material(row=st, master=_MASTER_BYTES, engaged=True)
        assert set(accepted) == {new_mat, old_mat}
        assert accepted[0] == new_mat  # 서명은 활성 키(리스트 첫번째)

        # grace 만료 전 finalize 는 거부(deadline 미경과).
        with pytest.raises(state_ops.AuthRateStateError):
            state_ops.rotation_finalize(
                s, prepared_rollout_artifact_sha256="c" * 64,
                expected_version=st.version, updated_by_admin_user_id=None,
            )
        s.rollback()

        # deadline 을 과거로 밀고 finalize → 구 키 폐기.
        s.execute(text(
            "UPDATE auth_rate_key_state SET previous_not_after = :past WHERE id=1"
        ), {"past": now_utc_naive() - datetime.timedelta(seconds=1)})
        s.commit()
        _consume(
            s, approver, "AUTH_RATE_ROTATION_FINALIZE", "rotation_finalize", "d" * 64,
            lambda ses, ver, aid: state_ops.rotation_finalize(
                ses, prepared_rollout_artifact_sha256="d" * 64, expected_version=ver,
                updated_by_admin_user_id=aid,
            ),
        )
        st = s.query(AuthRateKeyState).filter_by(id=1).one()
        assert st.mode == "ACTIVE"
        assert st.previous_key_id is None and st.previous_key_ciphertext is None
        assert st.previous_not_after is None
        assert st.active_key_id == new_kid
        assert st.generation == gen_after_bootstrap + 1  # generation 유지
        # finalize 뒤 accepted 는 활성 키 1개.
        accepted = key_state.accepted_key_material(row=st, master=_MASTER_BYTES, engaged=True)
        assert accepted == [new_mat]
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 3. OPS-APPROVAL 게이트: 승인 없이/재소비 시 mutation 0
# --------------------------------------------------------------------------- #
def test_no_approval_means_no_mutation(pg_engine):
    s = _session(pg_engine)
    try:
        _make_admin(s)
        _material, kid, ct_json, art_sha = _mint_key()
        st = s.query(AuthRateKeyState).filter_by(id=1).one()
        ver, gen = st.version, st.generation
        scope = state_ops.build_scope(
            "AUTH_RATE_BOOTSTRAP_PREPARE", "bootstrap_prepare", art_sha, ver, gen
        )
        # 승인 row 가 없는(unknown/replayed) 임의 secret → consume 거부, mutation 0.
        _b64, bogus = root_store.new_one_time_secret()
        with pytest.raises(ApprovalConsumeError):
            consume_same_db(
                s, operation_id="AUTH_RATE_BOOTSTRAP_PREPARE", scope_obj=scope,
                artifact_sha256=art_sha, expected_version=ver, expected_generation=gen,
                raw_secret=bogus,
                target_mutation=lambda ses: state_ops.bootstrap_prepare(
                    ses, pending_key_id=kid, pending_key_ciphertext=ct_json,
                    prepared_key_artifact_sha256=art_sha, expected_version=ver,
                    updated_by_admin_user_id=None,
                ),
            )
        s.rollback()
        st = s.query(AuthRateKeyState).filter_by(id=1).one()
        assert st.mode == "EMPTY" and st.pending_key_id is None  # 변화 없음
    finally:
        s.close()


def test_approval_is_one_time(pg_engine):
    s = _session(pg_engine)
    try:
        approver = _make_admin(s)
        _material, kid, ct_json, art_sha = _mint_key()
        st = s.query(AuthRateKeyState).filter_by(id=1).one()
        ver, gen = st.version, st.generation
        scope = state_ops.build_scope(
            "AUTH_RATE_BOOTSTRAP_PREPARE", "bootstrap_prepare", art_sha, ver, gen
        )
        raw = _approved(s, approver, "AUTH_RATE_BOOTSTRAP_PREPARE", scope)

        def _do():
            return consume_same_db(
                s, operation_id="AUTH_RATE_BOOTSTRAP_PREPARE", scope_obj=scope,
                artifact_sha256=art_sha, expected_version=ver, expected_generation=gen,
                raw_secret=raw,
                target_mutation=lambda ses: state_ops.bootstrap_prepare(
                    ses, pending_key_id=kid, pending_key_ciphertext=ct_json,
                    prepared_key_artifact_sha256=art_sha,
                    expected_version=ses.query(AuthRateKeyState).filter_by(id=1).one().version,
                    updated_by_admin_user_id=None,
                ),
            )

        _do()
        s.commit()
        # 같은 토큰 재소비 → CONSUMED 라 거부(one-time).
        with pytest.raises(ApprovalConsumeError):
            _do()
        s.rollback()
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 4. encrypted artifact: plaintext 키 0 + 변조 fail-closed
# --------------------------------------------------------------------------- #
def test_encrypted_artifact_no_plaintext_and_tamper_fails(pg_engine):
    s = _session(pg_engine)
    try:
        approver = _make_admin(s)
        material, kid = _bootstrap_to_active(s, approver)
        st = s.query(AuthRateKeyState).filter_by(id=1).one()

        # DB 컬럼(ciphertext)에 raw 키 바이트가 존재하지 않는다.
        blob = st.active_key_ciphertext
        assert isinstance(blob, str)
        assert material.hex() not in blob
        assert base64.urlsafe_b64encode(material).decode("ascii").rstrip("=") not in blob

        env = json.loads(blob)
        assert env["alg"] == "AES-256-GCM"
        # round-trip 복호화 정상.
        assert crypto.decrypt_key_material(env, _MASTER_BYTES, key_id=kid) == material
        # ciphertext 변조 → AES-GCM 인증 실패(fail-closed).
        tampered = dict(env)
        ct = base64.urlsafe_b64decode(tampered["ciphertext_b64url"] + "==")
        ct = bytes([ct[0] ^ 0x01]) + ct[1:]
        tampered["ciphertext_b64url"] = base64.urlsafe_b64encode(ct).rstrip(b"=").decode("ascii")
        with pytest.raises(crypto.AuthRateCryptoError):
            crypto.decrypt_key_material(tampered, _MASTER_BYTES, key_id=kid)
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 5. wrong-mode / version-mismatch STOP
# --------------------------------------------------------------------------- #
def test_wrong_mode_transitions_stop(pg_engine):
    s = _session(pg_engine)
    try:
        st = s.query(AuthRateKeyState).filter_by(id=1).one()
        ver = st.version
        # bootstrap activate 는 READY 에서만.
        with pytest.raises(state_ops.AuthRateStateError):
            state_ops.bootstrap_activate(
                s, prepared_rollout_artifact_sha256="a" * 64,
                expected_version=ver, updated_by_admin_user_id=None,
            )
        s.rollback()
        # rotation prepare 는 ACTIVE 에서만.
        with pytest.raises(state_ops.AuthRateStateError):
            state_ops.rotation_prepare(
                s, pending_key_id="k" * 64, pending_key_ciphertext="{}",
                prepared_key_artifact_sha256="a" * 64, expected_version=ver,
                updated_by_admin_user_id=None,
            )
        s.rollback()
        # rotation finalize 는 ROTATING 에서만.
        with pytest.raises(state_ops.AuthRateStateError):
            state_ops.rotation_finalize(
                s, prepared_rollout_artifact_sha256="a" * 64,
                expected_version=ver, updated_by_admin_user_id=None,
            )
        s.rollback()
    finally:
        s.close()


def test_version_mismatch_rejected(pg_engine):
    s = _session(pg_engine)
    try:
        ver = s.query(AuthRateKeyState).filter_by(id=1).one().version
        with pytest.raises(state_ops.AuthRateStateError):
            state_ops.bootstrap_prepare(
                s, pending_key_id="k" * 64, pending_key_ciphertext="{}",
                prepared_key_artifact_sha256="a" * 64, expected_version=ver + 999,
                updated_by_admin_user_id=None,
            )
        s.rollback()
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 6. rate limiter BRIDGE: 미engage 시 byte-identical / engage 시 서명
# --------------------------------------------------------------------------- #
def test_bridge_byte_identical_when_not_engaged(pg_engine):
    s = _session(pg_engine)
    try:
        approver = _make_admin(s)
        _bootstrap_to_active(s, approver)
        st = s.query(AuthRateKeyState).filter_by(id=1).one()
        base = "user:42"
        # 미engage: state 가 ACTIVE 여도 bucket 키는 오늘과 byte-identical(강제 무효화 0).
        assert key_state.sign_rate_bucket(base, row=st, master=_MASTER_BYTES, engaged=False) == base
        # engage: 활성 키로 서명된 generation-namespaced bucket 키.
        signed = key_state.sign_rate_bucket(base, row=st, master=_MASTER_BYTES, engaged=True)
        assert signed != base
        assert signed.startswith(f"g{st.generation}:")
        # 결정적(같은 입력 → 같은 bucket, 매 요청마다 흔들리지 않음).
        assert signed == key_state.sign_rate_bucket(base, row=st, master=_MASTER_BYTES, engaged=True)
    finally:
        s.close()
