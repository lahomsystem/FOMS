"""CHANNEL-INBOUND-ORDER-01 채널 수신 주문 파이프라인 PostgreSQL 계약 테스트 (PGTEST-00 lane).

실 PostgreSQL 다중 커밋 세션으로 다음을 검증한다:

* channel key rotation prepare/activate(dual accept)/finalize(old-reference 0 전 제거 0)·rewrap·
  version/generation·plaintext 0(AES-256-GCM envelope)·변조 fail-closed.
* OPS-APPROVAL 게이트: 승인 없이/재소비(one-time) 시 mutation 0(default Admin 0).
* 전역 create flag ENABLE/DISABLE: cutoff→PAUSED_ACCEPTED(job PAUSED)·enable resume(유실 0).
* dedicated worker: exact conservation(receipt 1=주문 1·중복 0)·재실행/크래시 후에도 1회 생성·
  max attempts→RECOVERY_REQUIRED·owner absence pause·global flag 우회 0·two commit 0.
* receipt recovery(approved CREATE→create_order 1회·IGNORE·legal hold)·retention(EXTEND·
  deadline→RETENTION_EXPIRED incident·unapproved indefinite 0·7d/24h/6h alerts).

``FOMS_TEST_DATABASE_URL`` 미설정이면 lane 자체가 skip 된다(conftest). 커밋 파일에는 비밀번호/
master key 를 넣지 않는다(dev DSN·master key 모두 env 로 주입).
"""
from __future__ import annotations

import base64
import datetime
import json
import os
import time
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker
from werkzeug.security import generate_password_hash

from foms.services.datetime_kst import now_utc_naive
from foms.services.security import ops_control_root as root_store
from foms.services.security.ops_approval import (
    ApprovalConsumeError,
    compute_scope_sha256,
    consume_same_db,
    nonce_hash_from_secret,
)
from foms.services.security.channel_order import (
    create_flag,
    creation,
    crypto,
    key_state,
    receipt_ops,
    state_ops,
    worker,
)
from models import (
    ChannelCreateFlag,
    ChannelInboundEventLog,
    ChannelInboundKeyState,
    Order,
    OpsApprovalRequest,
    SecurityPrincipalVersion,
    User,
)

# dev master key(env-only, 커밋 비밀 0).
_MASTER = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode("ascii")
os.environ[crypto.ENV_MASTER] = _MASTER
_MASTER_BYTES = crypto.resolve_master_key()

_VALID_TEXT = "고객명: 홍길동\n연락처: 010-1234-5678\n주소: 서울시 강남구\n수주제품: 소파"
_BAD_TEXT = "고객명: 김철수\n수주제품: 침대"  # 연락처/주소 누락 → parse 실패

_SEQ = [0]


def _session(pg_engine):
    return sessionmaker(bind=pg_engine)()


@pytest.fixture(autouse=True)
def _reset_state(pg_engine):
    """각 테스트 뒤 공유 singleton·receipt 를 초기화(session-scoped 공유 DB)."""
    yield
    s = _session(pg_engine)
    try:
        s.execute(text("DELETE FROM channel_inbound_event_logs"))
        s.execute(text(
            "UPDATE channel_inbound_key_state SET mode='EMPTY', version=1, generation=0, "
            "active_key_id=NULL, previous_key_id=NULL, pending_key_id=NULL, "
            "active_key_ciphertext=NULL, previous_key_ciphertext=NULL, pending_key_ciphertext=NULL, "
            "previous_not_after=NULL, prepared_key_artifact_sha256=NULL, "
            "prepared_rollout_artifact_sha256=NULL, prepared_at=NULL, activated_at=NULL, "
            "updated_by_admin_user_id=NULL WHERE id=1"
        ))
        s.execute(text(
            "UPDATE channel_create_flag SET state='DISABLED', version=1, "
            "updated_by_admin_user_id=NULL WHERE id=1"
        ))
        s.execute(text("DELETE FROM channel_inbound_worker_heartbeats"))
        s.commit()
    finally:
        s.close()


@pytest.fixture(autouse=True)
def _clear_owner_env(monkeypatch):
    """기본은 owner env 미설정(owner absence). 필요한 테스트만 명시 설정."""
    monkeypatch.delenv(creation.ENV_DEFAULT_OWNER, raising=False)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _make_admin(session, *, role="ADMIN", active=True):
    _SEQ[0] += 1
    user = User(
        username=f"chan_admin_{_SEQ[0]}_{int(time.time() * 1000) % 100000}",
        password=generate_password_hash("pw-not-committed"),
        name="승인자", role=role, team=None, is_active=active,
    )
    session.add(user)
    session.commit()
    return user


def _make_sales(session, *, active=True):
    _SEQ[0] += 1
    user = User(
        username=f"chan_sales_{_SEQ[0]}_{int(time.time() * 1000) % 100000}",
        password=generate_password_hash("pw-not-committed"),
        name="영업", role="STAFF", team="SALES", is_active=active,
    )
    session.add(user)
    session.commit()
    return user


def _pv(session, user_id):
    return (
        session.query(SecurityPrincipalVersion)
        .filter(SecurityPrincipalVersion.user_id == user_id).one().version
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


def _consume(session, approver, operation_id, scope, mutation_fn):
    """approval 토큰 소비로 mutation 을 한 tx 에 적용(approver 복사)."""
    raw = _approved(session, approver, operation_id, scope)
    nonce = nonce_hash_from_secret(raw)

    def _mut(s):
        appr = s.query(OpsApprovalRequest).filter_by(nonce_hash=nonce).one()
        return mutation_fn(s, appr.approved_by_user_id)

    sha = consume_same_db(
        session, operation_id=operation_id, scope_obj=scope,
        artifact_sha256=scope["artifact_sha256"], expected_version=scope["expected_version"],
        expected_generation=scope["expected_generation"], raw_secret=raw, target_mutation=_mut,
    )
    session.commit()
    return sha


def _mint_key():
    """새 channel key material + fingerprint + at-rest envelope + artifact sha."""
    material = crypto.new_key_material()
    kid = crypto.fingerprint(material)
    envelope = crypto.encrypt_key_material(material, _MASTER_BYTES, key_id=kid)
    ct_json = json.dumps(envelope, sort_keys=True, separators=(",", ":"))
    art_sha = crypto.sha256_hex(ct_json.encode("utf-8"))
    return material, kid, ct_json, art_sha


def _key_state(session):
    return session.query(ChannelInboundKeyState).filter_by(id=1).one()


def _prepare(session, approver, kid, ct_json, art_sha):
    st = _key_state(session)
    scope = state_ops.build_scope(
        "CHANNEL_KEY_ROTATION_PREPARE", "prepare", art_sha, st.version, st.generation)
    return _consume(
        session, approver, "CHANNEL_KEY_ROTATION_PREPARE", scope,
        lambda s, aid: state_ops.key_rotation_prepare(
            s, pending_key_id=kid, pending_key_ciphertext=ct_json,
            prepared_key_artifact_sha256=art_sha, expected_version=_key_state(s).version,
            updated_by_admin_user_id=aid),
    )


def _activate(session, approver, *, grace_seconds):
    st = _key_state(session)
    scope = state_ops.build_scope(
        "CHANNEL_KEY_ROTATION_ACTIVATE", "activate", "a" * 64, st.version, st.generation)
    return _consume(
        session, approver, "CHANNEL_KEY_ROTATION_ACTIVATE", scope,
        lambda s, aid: state_ops.key_rotation_activate(
            s, grace_seconds=grace_seconds, prepared_rollout_artifact_sha256="a" * 64,
            expected_version=_key_state(s).version, updated_by_admin_user_id=aid),
    )


def _finalize(session, approver, *, old_reference_count):
    st = _key_state(session)
    scope = state_ops.build_scope(
        "CHANNEL_KEY_ROTATION_FINALIZE", "finalize", "b" * 64, st.version, st.generation)
    return _consume(
        session, approver, "CHANNEL_KEY_ROTATION_FINALIZE", scope,
        lambda s, aid: state_ops.key_rotation_finalize(
            s, old_reference_count=old_reference_count,
            prepared_rollout_artifact_sha256="b" * 64,
            expected_version=_key_state(s).version, updated_by_admin_user_id=aid),
    )


def _bootstrap_active(session, approver):
    """EMPTY→READY→ACTIVE 로 첫 채널 키를 활성화하고 (material, kid) 반환."""
    material, kid, ct_json, art_sha = _mint_key()
    _prepare(session, approver, kid, ct_json, art_sha)
    _activate(session, approver, grace_seconds=0)
    return material, kid


def _receipt(session, *, dedupe, text_body=_VALID_TEXT, state="ACCEPTED", key_generation=None,
             sealed_secret=None):
    log = ChannelInboundEventLog(
        dedupe_key=dedupe, creation_key=f"crt_{dedupe}", payload_hash="h",
        status="accepted", raw_payload={"entity": {"plainText": text_body}},
        receipt_state=state, key_generation=key_generation, sealed_secret=sealed_secret,
    )
    session.add(log)
    session.commit()
    return log


def _enable_flag_direct(session):
    """flag 를 직접 ENABLED 로(worker 전용 테스트 — OPS 게이트는 별도 검증)."""
    session.execute(text("UPDATE channel_create_flag SET state='ENABLED' WHERE id=1"))
    session.commit()


# --------------------------------------------------------------------------- #
# 1. key rotation prepare/activate(dual accept)/finalize + rewrap + old-reference guard
# --------------------------------------------------------------------------- #
def test_key_rotation_dual_accept_finalize_and_rewrap(pg_engine):
    s = _session(pg_engine)
    try:
        approver = _make_admin(s)
        old_mat, old_kid = _bootstrap_active(s, approver)
        st = _key_state(s)
        assert st.mode == "ACTIVE" and st.generation == 1 and st.active_key_id == old_kid
        # plaintext 0: 활성 키가 실제 복호화되어 원본과 일치.
        env = json.loads(st.active_key_ciphertext)
        assert crypto.decrypt_key_material(env, _MASTER_BYTES, key_id=old_kid) == old_mat

        # 구 키로 봉인된 receipt(generation 1) — rewrap 대상.
        sealed = crypto.seal_secret(b"receipt-secret", old_mat, key_id=old_kid)
        _receipt(s, dedupe="rw-1", key_generation=1,
                 sealed_secret=json.dumps(sealed, sort_keys=True, separators=(",", ":")))

        # rotation: prepare(gen++) → activate(dual accept, grace).
        new_mat, new_kid, new_ct, new_art = _mint_key()
        _prepare(s, approver, new_kid, new_ct, new_art)
        st = _key_state(s)
        assert st.mode == "ROTATION_READY" and st.generation == 2
        assert st.pending_key_id == new_kid and st.active_key_id == old_kid

        _activate(s, approver, grace_seconds=60)
        st = _key_state(s)
        assert st.mode == "ROTATING"
        assert st.active_key_id == new_kid and st.previous_key_id == old_kid
        # dual accept: 신·구 키 둘 다 복호화 가능.
        accepted = key_state.accepted_keys(st, _MASTER_BYTES)
        assert {kid for _m, kid in accepted} == {new_kid, old_kid}

        # old-reference 0 전 제거 0: rewrap 전 finalize 는 거부(참조 1).
        assert key_state.count_previous_key_references(s, st) == 1
        st2 = _key_state(s)
        st2.previous_not_after = now_utc_naive() - datetime.timedelta(seconds=1)  # grace 경과
        s.commit()
        with pytest.raises(state_ops.ChannelKeyStateError):
            _finalize(s, approver, old_reference_count=1)
        s.rollback()

        # rewrap → 구 키 참조 0.
        st = _key_state(s)
        remaining = key_state.rewrap_previous_key_references(s, st, _MASTER_BYTES)
        s.commit()
        assert remaining == 0
        receipt = s.query(ChannelInboundEventLog).filter_by(dedupe_key="rw-1").one()
        assert receipt.key_generation == 2
        # rewrap 된 secret 은 새 키로만 열린다.
        assert crypto.unseal_secret(json.loads(receipt.sealed_secret), new_mat, key_id=new_kid) == b"receipt-secret"

        # 이제 finalize 허용 → 구 키 폐기.
        st = _key_state(s)
        st.previous_not_after = now_utc_naive() - datetime.timedelta(seconds=1)
        s.commit()
        _finalize(s, approver, old_reference_count=0)
        st = _key_state(s)
        assert st.mode == "ACTIVE"
        assert st.previous_key_id is None and st.active_key_id == new_kid and st.generation == 2
    finally:
        s.close()


def test_key_ciphertext_no_plaintext_and_tamper_fails(pg_engine):
    s = _session(pg_engine)
    try:
        approver = _make_admin(s)
        material, kid = _bootstrap_active(s, approver)
        st = _key_state(s)
        blob = st.active_key_ciphertext
        assert isinstance(blob, str)
        assert material.hex() not in blob
        assert base64.urlsafe_b64encode(material).decode("ascii").rstrip("=") not in blob
        env = json.loads(blob)
        assert env["alg"] == "AES-256-GCM"
        tampered = dict(env)
        ct = base64.urlsafe_b64decode(tampered["ciphertext_b64url"] + "==")
        tampered["ciphertext_b64url"] = base64.urlsafe_b64encode(
            bytes([ct[0] ^ 0x01]) + ct[1:]).rstrip(b"=").decode("ascii")
        with pytest.raises(crypto.ChannelCryptoError):
            crypto.decrypt_key_material(tampered, _MASTER_BYTES, key_id=kid)
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 2. OPS-APPROVAL 게이트: 승인 없이/재소비 시 mutation 0
# --------------------------------------------------------------------------- #
def test_no_approval_means_no_mutation(pg_engine):
    s = _session(pg_engine)
    try:
        _material, kid, ct_json, art_sha = _mint_key()
        st = _key_state(s)
        scope = state_ops.build_scope(
            "CHANNEL_KEY_ROTATION_PREPARE", "prepare", art_sha, st.version, st.generation)
        _b64, bogus = root_store.new_one_time_secret()
        with pytest.raises(ApprovalConsumeError):
            consume_same_db(
                s, operation_id="CHANNEL_KEY_ROTATION_PREPARE", scope_obj=scope,
                artifact_sha256=art_sha, expected_version=st.version,
                expected_generation=st.generation, raw_secret=bogus,
                target_mutation=lambda ses: state_ops.key_rotation_prepare(
                    ses, pending_key_id=kid, pending_key_ciphertext=ct_json,
                    prepared_key_artifact_sha256=art_sha, expected_version=st.version,
                    updated_by_admin_user_id=None),
            )
        s.rollback()
        assert _key_state(s).mode == "EMPTY" and _key_state(s).pending_key_id is None
    finally:
        s.close()


def test_approval_is_one_time(pg_engine):
    s = _session(pg_engine)
    try:
        approver = _make_admin(s)
        _material, kid, ct_json, art_sha = _mint_key()
        st = _key_state(s)
        scope = state_ops.build_scope(
            "CHANNEL_KEY_ROTATION_PREPARE", "prepare", art_sha, st.version, st.generation)
        raw = _approved(s, approver, "CHANNEL_KEY_ROTATION_PREPARE", scope)

        def _do():
            return consume_same_db(
                s, operation_id="CHANNEL_KEY_ROTATION_PREPARE", scope_obj=scope,
                artifact_sha256=art_sha, expected_version=scope["expected_version"],
                expected_generation=scope["expected_generation"], raw_secret=raw,
                target_mutation=lambda ses: state_ops.key_rotation_prepare(
                    ses, pending_key_id=kid, pending_key_ciphertext=ct_json,
                    prepared_key_artifact_sha256=art_sha,
                    expected_version=_key_state(ses).version, updated_by_admin_user_id=None),
            )

        _do()
        s.commit()
        with pytest.raises(ApprovalConsumeError):
            _do()
        s.rollback()
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 3. 전역 create flag ENABLE/DISABLE + cutoff pause/resume
# --------------------------------------------------------------------------- #
def test_create_flag_cutoff_pauses_and_resumes(pg_engine):
    s = _session(pg_engine)
    try:
        approver = _make_admin(s)
        _receipt(s, dedupe="flag-1", state="ACCEPTED")
        _receipt(s, dedupe="flag-2", state="ACCEPTED")

        # enable (DISABLED→ENABLED).
        flag = s.query(ChannelCreateFlag).filter_by(id=1).one()
        scope = create_flag.build_scope("CHANNEL_CREATE_ENABLE", "enable", "e" * 64, flag.version)
        _consume(s, approver, "CHANNEL_CREATE_ENABLE", scope,
                 lambda ses, aid: create_flag.enable(
                     ses, expected_version=ses.query(ChannelCreateFlag).filter_by(id=1).one().version,
                     updated_by_admin_user_id=aid))
        assert s.query(ChannelCreateFlag).filter_by(id=1).one().state == "ENABLED"

        # disable (cutoff) → ACCEPTED receipt 는 PAUSED_ACCEPTED 로 보존(유실 0).
        flag = s.query(ChannelCreateFlag).filter_by(id=1).one()
        scope = create_flag.build_scope("CHANNEL_CREATE_DISABLE", "disable", "d" * 64, flag.version)
        _consume(s, approver, "CHANNEL_CREATE_DISABLE", scope,
                 lambda ses, aid: create_flag.disable(
                     ses, expected_version=ses.query(ChannelCreateFlag).filter_by(id=1).one().version,
                     updated_by_admin_user_id=aid))
        assert s.query(ChannelCreateFlag).filter_by(id=1).one().state == "DISABLED"
        states = {r.dedupe_key: r.receipt_state
                  for r in s.query(ChannelInboundEventLog).all()}
        assert states == {"flag-1": "PAUSED_ACCEPTED", "flag-2": "PAUSED_ACCEPTED"}

        # re-enable → PAUSED_ACCEPTED 되살아남(ACCEPTED).
        flag = s.query(ChannelCreateFlag).filter_by(id=1).one()
        scope = create_flag.build_scope("CHANNEL_CREATE_ENABLE", "enable", "e2" + "0" * 62, flag.version)
        _consume(s, approver, "CHANNEL_CREATE_ENABLE", scope,
                 lambda ses, aid: create_flag.enable(
                     ses, expected_version=ses.query(ChannelCreateFlag).filter_by(id=1).one().version,
                     updated_by_admin_user_id=aid))
        states = {r.dedupe_key: r.receipt_state
                  for r in s.query(ChannelInboundEventLog).all()}
        assert states == {"flag-1": "ACCEPTED", "flag-2": "ACCEPTED"}
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 4. dedicated worker: exact conservation·idempotent·global flag 우회 0
# --------------------------------------------------------------------------- #
def test_worker_exact_conservation_and_idempotent(pg_engine, monkeypatch):
    s = _session(pg_engine)
    try:
        owner = _make_sales(s)
        monkeypatch.setenv(creation.ENV_DEFAULT_OWNER, str(owner.id))
        _enable_flag_direct(s)
        for i in range(3):
            _receipt(s, dedupe=f"conv-{i}", state="ACCEPTED")

        r1 = worker.run_create_once(
            pg_engine, owner_hash="w1", lease_token_fn=lambda: str(uuid.uuid4()))
        assert r1["claimed"] == 3 and r1["created"] == 3

        rows = s.query(ChannelInboundEventLog).order_by(ChannelInboundEventLog.dedupe_key).all()
        order_ids = [r.created_order_id for r in rows]
        assert all(oid is not None for oid in order_ids)
        assert len(set(order_ids)) == 3  # receipt 1 = 주문 1, 중복 0
        assert all(r.receipt_state == "CREATED" for r in rows)

        # 재실행(day0 rotate/crash→day29 create1): 이미 CREATED → 새 주문 0.
        r2 = worker.run_create_once(
            pg_engine, owner_hash="w1", lease_token_fn=lambda: str(uuid.uuid4()))
        assert r2["created"] == 0 and r2["claimed"] == 0
        rows2 = s.query(ChannelInboundEventLog).order_by(ChannelInboundEventLog.dedupe_key).all()
        assert [r.created_order_id for r in rows2] == order_ids  # 동일 주문(중복 생성 0)

        # 실제 Order 필드 검증.
        order = s.query(Order).get(order_ids[0])
        assert order.customer_name == "홍길동" and order.is_erp_order is True
    finally:
        s.close()


def test_worker_respects_disable_flag(pg_engine, monkeypatch):
    s = _session(pg_engine)
    try:
        owner = _make_sales(s)
        monkeypatch.setenv(creation.ENV_DEFAULT_OWNER, str(owner.id))
        # flag DISABLED(기본) — worker 가 우회하지 않는다.
        _receipt(s, dedupe="dis-1", state="ACCEPTED")
        r = worker.run_create_once(
            pg_engine, owner_hash="w1", lease_token_fn=lambda: str(uuid.uuid4()))
        assert r["claimed"] == 0 and r["created"] == 0
        row = s.query(ChannelInboundEventLog).filter_by(dedupe_key="dis-1").one()
        assert row.created_order_id is None and row.receipt_state == "ACCEPTED"
    finally:
        s.close()


def test_worker_owner_absence_pauses(pg_engine, monkeypatch):
    s = _session(pg_engine)
    try:
        monkeypatch.delenv(creation.ENV_DEFAULT_OWNER, raising=False)  # owner 부재
        _enable_flag_direct(s)
        _receipt(s, dedupe="own-1", state="ACCEPTED")
        r = worker.run_create_once(
            pg_engine, owner_hash="w1", lease_token_fn=lambda: str(uuid.uuid4()))
        assert r["paused"] == 1 and r["created"] == 0
        row = s.query(ChannelInboundEventLog).filter_by(dedupe_key="own-1").one()
        assert row.receipt_state == "PAUSED_ACCEPTED" and row.created_order_id is None
    finally:
        s.close()


def test_worker_max_attempts_to_recovery_required(pg_engine, monkeypatch):
    s = _session(pg_engine)
    try:
        owner = _make_sales(s)
        monkeypatch.setenv(creation.ENV_DEFAULT_OWNER, str(owner.id))
        _enable_flag_direct(s)
        _receipt(s, dedupe="max-1", text_body=_BAD_TEXT, state="ACCEPTED")  # parse 실패

        base = now_utc_naive()
        clock = {"t": base}
        for i in range(worker.DEFAULT_MAX_ATTEMPTS):
            clock["t"] = base + datetime.timedelta(hours=2 * i)  # backoff gate 통과
            worker.run_create_once(
                pg_engine, owner_hash="w1", lease_token_fn=lambda: str(uuid.uuid4()),
                now_fn=lambda: clock["t"])
        row = s.query(ChannelInboundEventLog).filter_by(dedupe_key="max-1").one()
        assert row.create_attempts == worker.DEFAULT_MAX_ATTEMPTS
        assert row.receipt_state == "RECOVERY_REQUIRED"  # 무한 재시도 0
        assert row.retention_deadline is not None  # retention 시계 시작
        assert row.created_order_id is None
    finally:
        s.close()


def test_worker_two_commit_zero_atomic_rollback(pg_engine, monkeypatch):
    """receipt CREATED 전이와 order 생성이 한 tx — rollback 시 둘 다 사라진다(two commit 0)."""
    s = _session(pg_engine)
    try:
        owner = _make_sales(s)
        receipt = _receipt(s, dedupe="atomic-1", state="ACCEPTED")
        s2 = _session(pg_engine)
        try:
            r = s2.query(ChannelInboundEventLog).filter_by(id=receipt.id).one()
            order = creation.create_order_from_receipt(s2, r, owner_user_id=owner.id)
            oid = order.id
            assert r.receipt_state == "CREATED" and r.created_order_id == oid
            s2.rollback()  # 원자성: 롤백 시 order·receipt 전이 모두 폐기
        finally:
            s2.close()
        # 별 세션에서 확인: order 없음, receipt 는 여전히 ACCEPTED.
        assert s.query(Order).get(oid) is None
        s.expire_all()
        assert s.query(ChannelInboundEventLog).filter_by(id=receipt.id).one().receipt_state == "ACCEPTED"
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 5. receipt recovery(CREATE/IGNORE·legal hold) + retention(EXTEND·expire·alerts)
# --------------------------------------------------------------------------- #
def test_recovery_create_and_ignore_and_legal_hold(pg_engine, monkeypatch):
    s = _session(pg_engine)
    try:
        approver = _make_admin(s)
        owner = _make_sales(s)

        # recovery CREATE: RECOVERY_REQUIRED → 승인 후 create_order 1회.
        r1 = _receipt(s, dedupe="rec-1", state="RECOVERY_REQUIRED")
        scope = receipt_ops.build_scope("CHANNEL_RECOVERY_CREATE", "create", "c" * 64, r1.id)
        _consume(s, approver, "CHANNEL_RECOVERY_CREATE", scope,
                 lambda ses, aid: receipt_ops.recovery_create(
                     ses, receipt_id=r1.id, owner_user_id=owner.id, actor_user_id=aid))
        r1 = s.query(ChannelInboundEventLog).filter_by(id=r1.id).one()
        assert r1.receipt_state == "CREATED" and r1.created_order_id is not None

        # recovery IGNORE: RECOVERY_REQUIRED → IGNORED.
        r2 = _receipt(s, dedupe="rec-2", state="RECOVERY_REQUIRED")
        scope = receipt_ops.build_scope("CHANNEL_RECOVERY_IGNORE", "ignore", "i" * 64, r2.id)
        _consume(s, approver, "CHANNEL_RECOVERY_IGNORE", scope,
                 lambda ses, aid: receipt_ops.recovery_ignore(ses, receipt_id=r2.id, actor_user_id=aid))
        assert s.query(ChannelInboundEventLog).filter_by(id=r2.id).one().receipt_state == "IGNORED"

        # legal hold → ignore 거부(accepted silent clear 0).
        r3 = _receipt(s, dedupe="rec-3", state="RECOVERY_REQUIRED")
        r3.legal_hold = True
        s.commit()
        with pytest.raises(receipt_ops.ChannelReceiptOpError):
            receipt_ops.recovery_ignore(s, receipt_id=r3.id)
        s.rollback()
        assert s.query(ChannelInboundEventLog).filter_by(id=r3.id).one().receipt_state == "RECOVERY_REQUIRED"
    finally:
        s.close()


def test_retention_extend_expire_and_alerts(pg_engine):
    s = _session(pg_engine)
    try:
        now = now_utc_naive()
        # unapproved indefinite retention 0: None deadline 거부.
        r0 = _receipt(s, dedupe="ret-0", state="RECOVERY_REQUIRED")
        with pytest.raises(receipt_ops.ChannelReceiptOpError):
            receipt_ops.retention_extend(s, receipt_id=r0.id, new_deadline=None, now=now)
        s.rollback()

        # EXTEND: 명시 유계 미래로 연장.
        r1 = _receipt(s, dedupe="ret-1", state="RECOVERY_REQUIRED")
        new_dl = now + datetime.timedelta(days=10)
        receipt_ops.retention_extend(s, receipt_id=r1.id, new_deadline=new_dl, now=now)
        s.commit()
        assert s.query(ChannelInboundEventLog).filter_by(id=r1.id).one().retention_deadline == new_dl

        # 7d/24h/6h alerts: deadline 5h 앞 → '6h' 단계 경고 후보(중복 방지).
        r2 = _receipt(s, dedupe="ret-2", state="RECOVERY_REQUIRED")
        r2.retention_deadline = now + datetime.timedelta(hours=5)
        s.commit()
        alerts = receipt_ops.retention_alerts(s, now=now)
        s.commit()
        stages = {a["receipt_id"]: a["stage"] for a in alerts}
        assert stages.get(r2.id) == "6h"
        # 재호출 → 같은 단계는 다시 알리지 않는다.
        assert all(a["receipt_id"] != r2.id for a in receipt_ops.retention_alerts(s, now=now))

        # deadline 경과·비 legal_hold → RETENTION_EXPIRED visible incident(조용한 삭제 0).
        r3 = _receipt(s, dedupe="ret-3", state="RECOVERY_REQUIRED")
        r3.retention_deadline = now - datetime.timedelta(seconds=1)
        s.commit()
        n = receipt_ops.scan_retention_expired(s, now=now)
        s.commit()
        assert n >= 1
        assert s.query(ChannelInboundEventLog).filter_by(id=r3.id).one().receipt_state == "RETENTION_EXPIRED"

        # legal_hold receipt 는 만료하지 않는다(승인된 보존).
        r4 = _receipt(s, dedupe="ret-4", state="RECOVERY_REQUIRED")
        r4.retention_deadline = now - datetime.timedelta(seconds=1)
        r4.legal_hold = True
        s.commit()
        receipt_ops.scan_retention_expired(s, now=now)
        s.commit()
        assert s.query(ChannelInboundEventLog).filter_by(id=r4.id).one().receipt_state == "RECOVERY_REQUIRED"
    finally:
        s.close()
