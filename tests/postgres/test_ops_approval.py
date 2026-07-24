"""OPS-APPROVAL-00 PostgreSQL 계약 테스트 (PGTEST-00 lane).

principal-version trigger, approval 생명주기, same-DB one-time consume 동시성,
cross-DB RESERVED snapshot/crash-finalize, manifest↔CLI 양방향, control-root 안전가드를
실 PostgreSQL 다중 커밋 세션으로 검증한다. ``FOMS_TEST_DATABASE_URL`` 미설정이면 lane
자체가 skip 된다(conftest). 커밋 파일에는 비밀번호를 넣지 않는다(env 로 주입).

manifest/append/control-root 안전가드 일부는 순수(비 PG) 테스트이지만 같은 파일에서
함께 검증한다.
"""
from __future__ import annotations

import datetime
import threading
import time

import pytest
from sqlalchemy.orm import sessionmaker
from werkzeug.security import generate_password_hash

from foms.services.datetime_kst import now_utc_naive

from models import (
    OpsApprovalRequest,
    OpsApprovalTargetAudit,
    SecurityPrincipalVersion,
    User,
)
from foms.services.security import ops_control_root as root_store
from foms.services.security.ops_approval import (
    ApprovalConsumeError,
    approve_request,
    commit_target,
    compute_operation_scope_sha256,
    compute_scope_sha256,
    consume_same_db,
    finalize_primary,
    nonce_hash_from_secret,
    read_secret_from_token_file,
    reconcile_reservations,
    reserve_primary,
)
from foms.services.security.ops_approval_manifest import (
    OpsManifestError,
    assert_append_only,
    assert_seed_integrity,
    load_operations_manifest,
    manifest_vs_cli_bidirectional,
)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _session(pg_engine):
    """pg_engine 기반의 독립 연결/세션(동시성 테스트용 다중 커밋)."""
    return sessionmaker(bind=pg_engine)()


_UNAME_SEQ = [0]


def _make_admin(session, *, role="ADMIN", active=True, password="pw-not-committed"):
    """admin User 생성(insert trigger 가 principal version 1 seed). 반환: user."""
    _UNAME_SEQ[0] += 1
    user = User(
        username=f"admin_{_UNAME_SEQ[0]}_{int(time.time() * 1000) % 100000}",
        password=generate_password_hash(password),
        name="승인자",
        role=role,
        team=None,
        is_active=active,
    )
    session.add(user)
    session.commit()
    return user


def _principal_version(session, user_id):
    pv = (
        session.query(SecurityPrincipalVersion)
        .filter(SecurityPrincipalVersion.user_id == user_id)
        .one()
    )
    return pv.version


def _scope(operation_id="DELETE_RETENTION_APPLY", version=7, generation=None, artifact="a" * 64):
    return {
        "schema_version": 1,
        "operation_id": operation_id,
        "packet_id": "DELETE-RETENTION-01",
        "target_ids_or_family": [101, 102, 103],
        "phase": "apply",
        "artifact_sha256": artifact,
        "expected_version": version,
        "expected_generation": generation,
    }


def _new_approved(session, approver, *, operation_id="DELETE_RETENTION_APPLY", scope=None,
                  now=None, expires_delta=600, state="APPROVED"):
    """APPROVED(또는 지정 state) approval row + raw secret 생성."""
    now = now or now_utc_naive()
    scope = scope or _scope(operation_id=operation_id)
    secret_b64, raw = root_store.new_one_time_secret()
    import uuid as _uuid

    row = OpsApprovalRequest(
        id=str(_uuid.uuid4()),
        operation_type=operation_id,
        scope_sha256=compute_scope_sha256(scope),
        artifact_sha256=scope.get("artifact_sha256"),
        expected_version=scope.get("expected_version"),
        expected_generation=scope.get("expected_generation"),
        nonce_hash=nonce_hash_from_secret(raw),
        expires_at=now + datetime.timedelta(seconds=expires_delta),
        state=state,
        approved_by_user_id=approver.id if state in ("APPROVED", "RESERVED") else None,
        approved_principal_version=(
            _principal_version(session, approver.id) if state in ("APPROVED", "RESERVED") else None
        ),
        approved_at=now if state in ("APPROVED", "RESERVED") else None,
        operator_identity_hash="0" * 64,
        created_at=now,
    )
    session.add(row)
    session.commit()
    return row, raw, scope


def _noop_mutation_factory(calls):
    def _mut(_session):
        calls.append(1)
        return b"result-bytes"
    return _mut


# --------------------------------------------------------------------------- #
# 1. principal-version trigger
# --------------------------------------------------------------------------- #
def test_principal_version_seeded_on_insert(pg_engine):
    s = _session(pg_engine)
    try:
        u = _make_admin(s)
        assert _principal_version(s, u.id) == 1
    finally:
        s.close()


@pytest.mark.parametrize("field,value", [
    ("password", generate_password_hash("changed-not-committed")),
    ("role", "MANAGER"),
    ("team", "CS"),
    ("is_active", False),
])
def test_principal_version_bumps_on_tracked_change(pg_engine, field, value):
    s = _session(pg_engine)
    try:
        u = _make_admin(s)
        assert _principal_version(s, u.id) == 1
        setattr(u, field, value)
        s.commit()
        assert _principal_version(s, u.id) == 2, f"{field} 변경 시 +1 이어야 함"
    finally:
        s.close()


def test_principal_version_unchanged_on_untracked_change(pg_engine):
    s = _session(pg_engine)
    try:
        u = _make_admin(s)
        base = _principal_version(s, u.id)
        u.name = "다른이름"
        u.last_login = now_utc_naive()
        s.commit()
        assert _principal_version(s, u.id) == base, "비추적 컬럼 변경엔 불변이어야 함"
    finally:
        s.close()


def test_principal_version_bumps_exactly_one_per_multi_field_update(pg_engine):
    s = _session(pg_engine)
    try:
        u = _make_admin(s)
        u.role = "MANAGER"
        u.team = "CS"
        u.is_active = False
        s.commit()  # 한 UPDATE 문 = +1
        assert _principal_version(s, u.id) == 2
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 2. approval 생명주기 (PENDING→APPROVED→CONSUMED, one-time)
# --------------------------------------------------------------------------- #
def test_lifecycle_pending_approve_consume_once(pg_engine):
    s = _session(pg_engine)
    try:
        admin = _make_admin(s)
        row, raw, scope = _new_approved(s, admin, state="PENDING")
        assert row.state == "PENDING"

        approve_request(s, approval_id=row.id, approver_user_id=admin.id)
        s.commit()
        s.refresh(row)
        assert row.state == "APPROVED"
        assert row.approved_by_user_id == admin.id
        assert row.approved_principal_version == 1

        calls = []
        result_sha = consume_same_db(
            s,
            operation_id=scope["operation_id"],
            scope_obj=scope,
            artifact_sha256=scope["artifact_sha256"],
            expected_version=scope["expected_version"],
            expected_generation=scope["expected_generation"],
            raw_secret=raw,
            target_mutation=_noop_mutation_factory(calls),
        )
        s.commit()
        s.refresh(row)
        assert row.state == "CONSUMED"
        assert row.result_sha256 == result_sha
        assert calls == [1]

        # 재소비 거부(one-time): state != APPROVED → mutation 0.
        recalls = []
        with pytest.raises(ApprovalConsumeError):
            consume_same_db(
                s, operation_id=scope["operation_id"], scope_obj=scope,
                artifact_sha256=scope["artifact_sha256"],
                expected_version=scope["expected_version"],
                expected_generation=scope["expected_generation"],
                raw_secret=raw, target_mutation=_noop_mutation_factory(recalls),
            )
        s.rollback()
        assert recalls == []
    finally:
        s.close()


def test_approve_rejects_expired_and_non_admin(pg_engine):
    s = _session(pg_engine)
    try:
        admin = _make_admin(s)
        # 만료된 PENDING
        row, _raw, _scope = _new_approved(s, admin, state="PENDING", expires_delta=-10)
        with pytest.raises(ApprovalConsumeError):
            approve_request(s, approval_id=row.id, approver_user_id=admin.id)
        s.rollback()

        # 비 ADMIN approver
        staff = _make_admin(s, role="STAFF")
        row2, _r2, _s2 = _new_approved(s, admin, state="PENDING")
        with pytest.raises(ApprovalConsumeError):
            approve_request(s, approval_id=row2.id, approver_user_id=staff.id)
        s.rollback()
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 3. same-DB consume 가드 → mutation 0
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("mutate", ["expire", "deactivate", "version_change"])
def test_consume_guards_yield_zero_mutation(pg_engine, mutate):
    s = _session(pg_engine)
    try:
        admin = _make_admin(s)
        row, raw, scope = _new_approved(s, admin)

        if mutate == "expire":
            row.expires_at = now_utc_naive() - datetime.timedelta(seconds=1)
            s.commit()
        elif mutate == "deactivate":
            admin.is_active = False
            s.commit()  # version 도 오르지만 핵심은 비활성 → reject
        elif mutate == "version_change":
            admin.password = generate_password_hash("rotated-not-committed")
            s.commit()  # principal version 1→2, snapshot 1 과 불일치

        calls = []
        with pytest.raises(ApprovalConsumeError):
            consume_same_db(
                s, operation_id=scope["operation_id"], scope_obj=scope,
                artifact_sha256=scope["artifact_sha256"],
                expected_version=scope["expected_version"],
                expected_generation=scope["expected_generation"],
                raw_secret=raw, target_mutation=_noop_mutation_factory(calls),
            )
        s.rollback()
        assert calls == []
        s.refresh(row)
        assert row.state == "APPROVED"  # 소비되지 않음
    finally:
        s.close()


@pytest.mark.parametrize("mismatch", ["operation", "scope", "artifact", "version", "generation", "nonce"])
def test_consume_rejects_exact_recomputation_mismatch(pg_engine, mismatch):
    s = _session(pg_engine)
    try:
        admin = _make_admin(s)
        row, raw, scope = _new_approved(s, admin)
        calls = []
        kwargs = dict(
            operation_id=scope["operation_id"], scope_obj=dict(scope),
            artifact_sha256=scope["artifact_sha256"],
            expected_version=scope["expected_version"],
            expected_generation=scope["expected_generation"],
            raw_secret=raw, target_mutation=_noop_mutation_factory(calls),
        )
        if mismatch == "operation":
            kwargs["operation_id"] = "CUTOVER_MARK"
        elif mismatch == "scope":
            bad = dict(scope); bad["phase"] = "different"; kwargs["scope_obj"] = bad
        elif mismatch == "artifact":
            kwargs["artifact_sha256"] = "b" * 64
        elif mismatch == "version":
            kwargs["expected_version"] = 999
        elif mismatch == "generation":
            kwargs["expected_generation"] = 42
        elif mismatch == "nonce":
            _b64, other = root_store.new_one_time_secret()
            kwargs["raw_secret"] = other

        with pytest.raises(ApprovalConsumeError):
            consume_same_db(s, **kwargs)
        s.rollback()
        assert calls == []
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 3b. 동시성: 동시 consume 2개 중 1만 성공 (FOR UPDATE)
# --------------------------------------------------------------------------- #
def test_concurrent_consume_only_one_succeeds(pg_engine):
    setup = _session(pg_engine)
    try:
        admin = _make_admin(setup)
        row, raw, scope = _new_approved(setup, admin)
        approval_id = row.id
    finally:
        setup.close()

    calls_a, calls_b = [], []
    outcome = {}
    started = threading.Event()

    def _consume(tag, calls, hold):
        sess = _session(pg_engine)
        try:
            consume_same_db(
                sess, operation_id=scope["operation_id"], scope_obj=scope,
                artifact_sha256=scope["artifact_sha256"],
                expected_version=scope["expected_version"],
                expected_generation=scope["expected_generation"],
                raw_secret=raw, target_mutation=_noop_mutation_factory(calls),
            )
            if hold:
                started.set()
                time.sleep(0.6)  # lock 을 잡은 채 대기 → B 가 FOR UPDATE 에서 블록
            sess.commit()
            outcome[tag] = "ok"
        except ApprovalConsumeError:
            sess.rollback()
            outcome[tag] = "rejected"
        finally:
            sess.close()

    ta = threading.Thread(target=_consume, args=("A", calls_a, True))
    ta.start()
    started.wait(2.0)
    tb = threading.Thread(target=_consume, args=("B", calls_b, False))
    tb.start()
    ta.join(5.0)
    tb.join(5.0)

    assert sorted(outcome.values()) == ["ok", "rejected"], outcome
    assert len(calls_a) + len(calls_b) == 1, "target mutation 은 정확히 1회"

    check = _session(pg_engine)
    try:
        r = check.query(OpsApprovalRequest).filter_by(id=approval_id).one()
        assert r.state == "CONSUMED"
    finally:
        check.close()


# --------------------------------------------------------------------------- #
# 4. cross-DB RESERVED snapshot / crash-finalize idempotent
# --------------------------------------------------------------------------- #
def test_cross_db_reserved_snapshot_is_non_cancelable(pg_engine):
    """RESERVED 뒤 approver version 이 바뀌어도 snapshot 은 유지되고 finalize 된다."""
    primary = _session(pg_engine)
    target = _session(pg_engine)
    try:
        admin = _make_admin(primary)
        row, raw, scope = _new_approved(primary, admin, operation_id="WDC_LINK_CANONICAL")
        approval_id = row.id

        reservation_id = reserve_primary(
            primary, operation_id=scope["operation_id"], scope_obj=scope,
            artifact_sha256=scope["artifact_sha256"],
            expected_version=scope["expected_version"],
            expected_generation=scope["expected_generation"],
            raw_secret=raw,
        )
        primary.commit()  # RESERVED committed = 취소 불가 snapshot
        primary.refresh(row)
        assert row.state == "RESERVED"

        # 사후 approver version 변경 — snapshot 을 취소하지 않아야 한다.
        admin.password = generate_password_hash("rotated-not-committed")
        primary.commit()
        assert _principal_version(primary, admin.id) == 2

        calls = []
        result_sha = commit_target(
            target, approval_id=approval_id, reservation_id=reservation_id,
            operation_id=scope["operation_id"], scope_sha256=compute_scope_sha256(scope),
            target_mutation=_noop_mutation_factory(calls),
        )
        target.commit()
        assert calls == [1]

        finalize_primary(primary, approval_id=approval_id, result_sha256=result_sha)
        primary.commit()
        primary.refresh(row)
        assert row.state == "CONSUMED"
        assert row.result_sha256 == result_sha

        # crash finalize idempotent: 재호출은 no-op.
        finalize_primary(primary, approval_id=approval_id, result_sha256=result_sha)
        primary.commit()
        primary.refresh(row)
        assert row.state == "CONSUMED"
    finally:
        primary.close()
        target.close()


def test_cross_db_target_audit_unique_prevents_double_mutation(pg_engine):
    primary = _session(pg_engine)
    target = _session(pg_engine)
    try:
        admin = _make_admin(primary)
        row, raw, scope = _new_approved(primary, admin, operation_id="WDC_LINK_FREEZE")
        rid = reserve_primary(
            primary, operation_id=scope["operation_id"], scope_obj=scope,
            artifact_sha256=scope["artifact_sha256"],
            expected_version=scope["expected_version"],
            expected_generation=scope["expected_generation"], raw_secret=raw,
        )
        primary.commit()

        calls = []
        r1 = commit_target(
            target, approval_id=row.id, reservation_id=rid,
            operation_id=scope["operation_id"], scope_sha256=compute_scope_sha256(scope),
            target_mutation=_noop_mutation_factory(calls),
        )
        target.commit()
        # crash retry: 같은 (approval,reservation,scope) → 기존 result 반환, 재mutation 0.
        r2 = commit_target(
            target, approval_id=row.id, reservation_id=rid,
            operation_id=scope["operation_id"], scope_sha256=compute_scope_sha256(scope),
            target_mutation=_noop_mutation_factory(calls),
        )
        target.commit()
        assert r1 == r2
        assert calls == [1], "target mutation 은 정확히 1회"

        op_scope = compute_operation_scope_sha256(scope["operation_id"], compute_scope_sha256(scope))
        n = (
            target.query(OpsApprovalTargetAudit)
            .filter_by(approval_id=row.id, reservation_id=rid, operation_scope_sha256=op_scope)
            .count()
        )
        assert n == 1
    finally:
        primary.close()
        target.close()


def test_reconcile_finalizes_committed_and_expires_stale(pg_engine):
    primary = _session(pg_engine)
    target = _session(pg_engine)
    try:
        admin = _make_admin(primary)

        # (a) target 이 이미 커밋된 RESERVED → reconcile 이 finalize.
        row_a, raw_a, scope_a = _new_approved(primary, admin, operation_id="WDC_LINK_ABORT")
        rid_a = reserve_primary(
            primary, operation_id=scope_a["operation_id"], scope_obj=scope_a,
            artifact_sha256=scope_a["artifact_sha256"],
            expected_version=scope_a["expected_version"],
            expected_generation=scope_a["expected_generation"], raw_secret=raw_a,
        )
        primary.commit()
        commit_target(
            target, approval_id=row_a.id, reservation_id=rid_a,
            operation_id=scope_a["operation_id"], scope_sha256=compute_scope_sha256(scope_a),
            target_mutation=lambda _s: b"x",
        )
        target.commit()

        # (b) target 없이 만료된 RESERVED → reconcile 이 EXPIRED (mutation 0).
        row_b, raw_b, scope_b = _new_approved(primary, admin, operation_id="WDC_LINK_FREEZE")
        rid_b = reserve_primary(
            primary, operation_id=scope_b["operation_id"], scope_obj=scope_b,
            artifact_sha256=scope_b["artifact_sha256"],
            expected_version=scope_b["expected_version"],
            expected_generation=scope_b["expected_generation"], raw_secret=raw_b,
            reservation_ttl_seconds=-1,  # 즉시 만료
        )
        primary.commit()

        result = reconcile_reservations(primary, target)
        primary.commit()

        primary.refresh(row_a)
        primary.refresh(row_b)
        assert row_a.state == "CONSUMED" and str(row_a.id) in result["finalized"]
        assert row_b.state == "EXPIRED" and str(row_b.id) in result["expired"]
        # reconcile 은 target 커밋을 rollback 하지 않는다.
        assert target.query(OpsApprovalTargetAudit).filter_by(approval_id=row_a.id).count() == 1
    finally:
        primary.close()
        target.close()


# --------------------------------------------------------------------------- #
# 5. manifest ↔ CLI 양방향 + seed/append
# --------------------------------------------------------------------------- #
def test_manifest_seed_integrity_and_bidirectional_green():
    m = load_operations_manifest()
    assert_seed_integrity(m)  # owner 표와 exact 일치
    # seed+append 규정(§2.1 line 209): 착수한 소비 packet 만 자기 owner operation 의 cli 를
    # 채운다. CUTOVER-MODE-01 이 자기 3 operation 을 owner-only append 했고, 아직 착수하지
    # 않은 다른 consumer operation 은 여전히 cli=null 이어야 한다.
    from foms.services.security.ops_approval_manifest import EXPECTED_OWNER_OPERATIONS
    _landed = set(EXPECTED_OWNER_OPERATIONS["CUTOVER-MODE-01"])
    for opid, meta in m["operations"].items():
        if opid in _landed:
            assert meta["cli"] is not None, f"{opid} should be filled by CUTOVER-MODE-01"
        else:
            assert meta["cli"] is None, f"{opid} should still be cli=null (consumer not landed)"
    diff = manifest_vs_cli_bidirectional(m)
    assert diff == {"unregistered_cli": [], "unimplemented_operation": [], "cli_path_mismatch": []}


def test_manifest_bidirectional_flags_unimplemented_and_unregistered():
    m = load_operations_manifest()
    # 미구현 operation: cli 는 있으나 실제 CLI 부재 → red.
    m2 = {"operations": {k: dict(v) for k, v in m["operations"].items()}}
    any_op = next(iter(m2["operations"]))
    m2["operations"][any_op]["cli"] = "tools/ops/does_not_exist.py"
    diff = manifest_vs_cli_bidirectional(m2)
    assert any_op in diff["unimplemented_operation"]


def test_manifest_append_only_rules():
    m = load_operations_manifest()
    base = {"operations": {k: dict(v) for k, v in m["operations"].items()}}

    # 허용: 자기 operation 의 null 필드 채우기.
    ok = {"operations": {k: dict(v) for k, v in base["operations"].items()}}
    opid = "DELETE_RETENTION_APPLY"
    ok["operations"][opid]["cli"] = "tools/ops/delete_retention_apply.py"
    assert_append_only(base, ok)  # no raise

    # 금지: owner_packet 변경.
    bad_owner = {"operations": {k: dict(v) for k, v in base["operations"].items()}}
    bad_owner["operations"][opid]["owner_packet"] = "HACKED"
    with pytest.raises(OpsManifestError):
        assert_append_only(base, bad_owner)

    # 금지: operation 추가.
    bad_add = {"operations": {k: dict(v) for k, v in base["operations"].items()}}
    bad_add["operations"]["BRAND_NEW_OP"] = dict(base["operations"][opid])
    with pytest.raises(OpsManifestError):
        assert_append_only(base, bad_add)


# --------------------------------------------------------------------------- #
# 6. 안전가드: control-root / token / no raw-secret
# --------------------------------------------------------------------------- #
def test_token_outside_control_root_is_refused(tmp_path):
    root = tmp_path / "control_root"
    root.mkdir()
    b64, raw = root_store.new_one_time_secret()
    token = root_store.build_token("aid", b64, "DELETE_RETENTION_APPLY", "s" * 64, "2026-01-01T00:00:00Z")

    inside = root_store.atomic_write_token(root, token)
    assert inside.parent == root
    # root 아래면 읽힘.
    assert root_store.read_token(inside, root)["approval_id"] == "aid"

    # root 밖 경로는 거부.
    outside = tmp_path / "elsewhere.json"
    outside.write_text("{}", encoding="utf-8")
    with pytest.raises(root_store.OpsControlRootError):
        root_store.read_token(outside, root)


def test_read_secret_from_token_file_roundtrip_and_guards(tmp_path):
    root = tmp_path / "control_root"
    root.mkdir()
    b64, raw = root_store.new_one_time_secret()
    token = root_store.build_token(
        "aid", b64, "DELETE_RETENTION_APPLY", "s" * 64, "2026-01-01T00:00:00Z"
    )
    path = root_store.atomic_write_token(root, token)

    # 정상: 디코드된 secret 의 sha256 == nonce_hash.
    got = read_secret_from_token_file(path, root, expected_operation_id="DELETE_RETENTION_APPLY")
    assert nonce_hash_from_secret(got) == nonce_hash_from_secret(raw)

    # operation 불일치 거부.
    with pytest.raises(ApprovalConsumeError):
        read_secret_from_token_file(path, root, expected_operation_id="CUTOVER_MARK")

    # root 밖 토큰 거부.
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    with pytest.raises(root_store.OpsControlRootError):
        read_secret_from_token_file(outside, root)


def test_control_root_fail_closed_on_non_windows(monkeypatch):
    monkeypatch.setenv("FOMS_OPS_CONTROL_ROOT", "/tmp/whatever")
    monkeypatch.setattr(root_store.os, "name", "posix")
    with pytest.raises(root_store.OpsControlRootError):
        root_store.resolve_control_root()


def test_control_root_rejects_repo_internal_path(monkeypatch, tmp_path):
    # repo 내부 경로는 거부(값이 repo 트리 안).
    repo_internal = root_store._repo_root() / "docs"
    monkeypatch.setenv("FOMS_OPS_CONTROL_ROOT", str(repo_internal))
    if root_store.os.name != "nt":
        with pytest.raises(root_store.OpsControlRootError):
            root_store.resolve_control_root()
    else:
        with pytest.raises(root_store.OpsControlRootError):
            root_store.resolve_control_root(require_acl=False)


def test_no_raw_secret_persisted(pg_engine):
    """DB 에는 nonce_hash(해시)만 저장되고 raw secret/PII 는 없다."""
    s = _session(pg_engine)
    try:
        admin = _make_admin(s)
        row, raw, _scope = _new_approved(s, admin)
        b64 = root_store.new_one_time_secret()  # 형식 확인용
        # nonce_hash 는 secret 의 sha256 이며 raw 와 다르다.
        assert row.nonce_hash == nonce_hash_from_secret(raw)
        assert row.nonce_hash != raw.hex()
        # operator_identity_hash 는 사용자명 원문이 아니라 64-hex 해시.
        assert len(row.operator_identity_hash) == 64
        # OpsApprovalRequest 에 raw secret 컬럼이 존재하지 않는다.
        cols = {c.name for c in OpsApprovalRequest.__table__.columns}
        assert "one_time_secret" not in cols and "secret" not in cols
    finally:
        s.close()
