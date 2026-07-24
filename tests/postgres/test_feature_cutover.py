"""CUTOVER-MODE-01 PostgreSQL 계약 테스트 (PGTEST-00 lane).

fence 15 pre-seed · marker irreversibility · fence KEY SHARE↔mark FOR UPDATE 동시성
(drain) · DRAIN begin/abort · mark crash atomic · approval 소비로 마킹 시
approved_by_admin_user_id 복사를 실 PostgreSQL 다중 커밋 세션으로 검증한다.
``FOMS_TEST_DATABASE_URL`` 미설정이면 PG 의존 테스트는 skip 된다(conftest). mode manifest
15-row 양방향과 build_compatibility generation 규칙은 순수(비 PG) 테스트다.

커밋 파일에는 비밀번호를 넣지 않는다(dev DSN 은 env 로 주입).
"""
from __future__ import annotations

import datetime
import threading
import time
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker
from werkzeug.security import generate_password_hash

from foms.services.datetime_kst import now_utc_naive

from models import OpsApprovalRequest, SecurityPrincipalVersion, User
from foms.services.security import ops_control_root as root_store
from foms.services.security.ops_approval import (
    compute_scope_sha256,
    consume_same_db,
    nonce_hash_from_secret,
)

from foms.services.security.cutover.families import FEATURE_CUTOVER_FAMILIES
from foms.services.security.cutover.transactional import (
    CutoverModeError,
    begin_transactional_mode,
)
from foms.services.security.cutover.mark_ops import (
    CutoverMarkError,
    abort_drain,
    begin_drain,
    mark_cutover,
)
from foms.services.security.cutover.mode_manifest import (
    assert_row_shape,
    load_manifest,
    manifest_vs_inventory_bidirectional,
)
from tools.harness.verify_build_compatibility import (
    BuildCompatibilityError,
    load_build_compatibility,
    validate_structure,
    verify_against_merge_base,
)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _session(pg_engine):
    return sessionmaker(bind=pg_engine)()


_UNAME_SEQ = [0]


def _make_admin(session):
    _UNAME_SEQ[0] += 1
    u = User(
        username=f"cutadmin_{_UNAME_SEQ[0]}_{int(time.time() * 1000) % 100000}",
        password=generate_password_hash("pw-not-committed"),
        name="승인자", role="ADMIN", team=None, is_active=True,
    )
    session.add(u)
    session.commit()
    return u


def _fence_version(session, family):
    return session.execute(
        text("SELECT row_version FROM feature_cutover_fences WHERE family = :f"),
        {"f": family},
    ).scalar()


def _fence_mode(session, family):
    return session.execute(
        text("SELECT mode FROM feature_cutover_fences WHERE family = :f"),
        {"f": family},
    ).scalar()


# --------------------------------------------------------------------------- #
# 1. fence 15 pre-seed (create_all lane)
# --------------------------------------------------------------------------- #
def test_fence_15_family_pre_seeded_open(pg_engine):
    s = _session(pg_engine)
    try:
        rows = s.execute(text("SELECT family, mode FROM feature_cutover_fences")).all()
        families = {r[0] for r in rows}
        assert families == set(FEATURE_CUTOVER_FAMILIES)
        assert len(rows) == 15
        assert {r[1] for r in rows} == {"OPEN"}
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 2. marker irreversibility (UPDATE/DELETE 거부)
# --------------------------------------------------------------------------- #
def test_marker_is_irreversible(pg_engine):
    family = "PRODUCTION_RUN"
    s = _session(pg_engine)
    try:
        admin = _make_admin(s)
        s.execute(
            text(
                "INSERT INTO feature_cutover_markers "
                "(family,cutover_sha,cutover_generation,minimum_compatibility_generation,"
                " readiness_artifact_sha256,ops_approval_id,approved_by_admin_user_id) "
                "VALUES (:f,'sha',1,1,:art,:aid,:u)"
            ),
            {"f": family, "art": "a" * 64, "aid": str(uuid.uuid4()), "u": admin.id},
        )
        s.commit()

        with pytest.raises(Exception):
            s.execute(text("UPDATE feature_cutover_markers SET cutover_generation=2 WHERE family=:f"),
                      {"f": family})
            s.commit()
        s.rollback()
        with pytest.raises(Exception):
            s.execute(text("DELETE FROM feature_cutover_markers WHERE family=:f"), {"f": family})
            s.commit()
        s.rollback()
        # 여전히 존재하고 값 불변.
        gen = s.execute(text("SELECT cutover_generation FROM feature_cutover_markers WHERE family=:f"),
                        {"f": family}).scalar()
        assert gen == 1
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 3. 동시성: A fence KEY SHARE → B mark blocked → A commit → mark → new legacy 0
# --------------------------------------------------------------------------- #
def test_key_share_blocks_mark_then_new_legacy_zero(pg_engine):
    family = "ASSIGNMENT"  # COMPATIBLE: OPEN 에서 mark.
    setup = _session(pg_engine)
    try:
        admin_id = _make_admin(setup).id
        expected_version = _fence_version(setup, family)
    finally:
        setup.close()

    barrier = threading.Event()
    a_committed = threading.Event()
    events = []
    outcome = {}

    def hold_business():
        a = _session(pg_engine)
        try:
            state = begin_transactional_mode(a, family)  # FOR KEY SHARE
            events.append(state.effective_mode)
            barrier.set()
            time.sleep(0.8)  # lock 보유 → B 의 FOR UPDATE 블록
            a.commit()
            a_committed.set()
        finally:
            a.close()

    def do_mark():
        barrier.wait(2.0)
        b = _session(pg_engine)
        t0 = time.time()
        try:
            mark_cutover(
                b, family, expected_version, cutover_sha="deadbeef",
                cutover_generation=1, minimum_compatibility_generation=1,
                readiness_artifact_sha256="a" * 64, ops_approval_id=str(uuid.uuid4()),
                approved_by_admin_user_id=admin_id,
            )
            b.commit()
            outcome["waited"] = time.time() - t0
            outcome["mark"] = "ok"
        except Exception as exc:  # noqa: BLE001
            b.rollback()
            outcome["mark"] = f"fail:{exc}"
        finally:
            b.close()

    ta = threading.Thread(target=hold_business)
    tb = threading.Thread(target=do_mark)
    ta.start(); tb.start(); ta.join(5.0); tb.join(5.0)

    assert events == ["OPEN"], events
    assert outcome.get("mark") == "ok", outcome
    assert a_committed.is_set()
    assert outcome["waited"] > 0.4, f"mark should block on KEY SHARE until A commits: {outcome}"

    # new business tx 는 CUTOVER 를 보고 새 legacy 를 받지 않는다(new legacy 0).
    c = _session(pg_engine)
    try:
        state = begin_transactional_mode(c, family)
        assert state.is_cutover
        assert not state.accepts_new_business
        assert _fence_mode(c, family) == "CUTOVER"
    finally:
        c.close()


# --------------------------------------------------------------------------- #
# 4. COMPATIBLE mark + re-mark 거부(irreversible) + mark crash atomic
# --------------------------------------------------------------------------- #
def test_compatible_mark_atomic_and_rejects_remark(pg_engine):
    family = "STATE_COMMAND"
    s = _session(pg_engine)
    try:
        admin_id = _make_admin(s).id
        ver = _fence_version(s, family)
        mark_cutover(
            s, family, ver, cutover_sha="c0ffee", cutover_generation=1,
            minimum_compatibility_generation=1, readiness_artifact_sha256="b" * 64,
            ops_approval_id=str(uuid.uuid4()), approved_by_admin_user_id=admin_id,
        )
        s.commit()
        # marker insert + fence CUTOVER 가 같은 tx (atomic): 둘 다 반영.
        assert _fence_mode(s, family) == "CUTOVER"
        n = s.execute(text("SELECT count(*) FROM feature_cutover_markers WHERE family=:f"),
                      {"f": family}).scalar()
        assert n == 1

        # re-mark 거부: marker 이미 존재.
        ver2 = _fence_version(s, family)
        with pytest.raises(CutoverMarkError):
            mark_cutover(
                s, family, ver2, cutover_sha="c0ffee", cutover_generation=1,
                minimum_compatibility_generation=1, readiness_artifact_sha256="b" * 64,
                ops_approval_id=str(uuid.uuid4()), approved_by_admin_user_id=admin_id,
            )
        s.rollback()
    finally:
        s.close()


def test_compatible_family_cannot_begin_drain(pg_engine):
    s = _session(pg_engine)
    try:
        ver = _fence_version(s, "QUEST")
        with pytest.raises(CutoverMarkError):
            begin_drain(s, "QUEST", ver)  # QUEST 는 COMPATIBLE.
        s.rollback()
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 5. DRAIN family: begin(OPEN→DRAINING)→mark(DRAINING→CUTOVER); abort(DRAINING→OPEN)
# --------------------------------------------------------------------------- #
def test_drain_begin_then_mark(pg_engine):
    family = "UPLOAD"  # DRAIN.
    s = _session(pg_engine)
    try:
        admin_id = _make_admin(s).id
        ver = _fence_version(s, family)

        # COMPATIBLE 경로(OPEN 에서 바로 mark)는 DRAIN family 에서 거부돼야 한다.
        with pytest.raises(CutoverMarkError):
            mark_cutover(
                s, family, ver, cutover_sha="x", cutover_generation=1,
                minimum_compatibility_generation=1, readiness_artifact_sha256="c" * 64,
                ops_approval_id=str(uuid.uuid4()), approved_by_admin_user_id=admin_id,
            )
        s.rollback()

        ver = _fence_version(s, family)
        begin_drain(s, family, ver)
        s.commit()
        assert _fence_mode(s, family) == "DRAINING"

        ver = _fence_version(s, family)
        mark_cutover(
            s, family, ver, cutover_sha="x", cutover_generation=1,
            minimum_compatibility_generation=1, readiness_artifact_sha256="c" * 64,
            ops_approval_id=str(uuid.uuid4()), approved_by_admin_user_id=admin_id,
        )
        s.commit()
        assert _fence_mode(s, family) == "CUTOVER"
    finally:
        s.close()


def test_drain_abort_restores_open_marker_zero(pg_engine):
    family = "NOTIFICATION_DELIVERY"  # DRAIN.
    s = _session(pg_engine)
    try:
        ver = _fence_version(s, family)
        begin_drain(s, family, ver)
        s.commit()
        assert _fence_mode(s, family) == "DRAINING"

        ver = _fence_version(s, family)
        abort_drain(s, family, ver)
        s.commit()
        assert _fence_mode(s, family) == "OPEN"
        # marker 0.
        n = s.execute(text("SELECT count(*) FROM feature_cutover_markers WHERE family=:f"),
                      {"f": family}).scalar()
        assert n == 0
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 6. approval 소비로 mark → approved_by_admin_user_id 는 approval row 에서 복사
# --------------------------------------------------------------------------- #
def test_mark_via_approval_consume_copies_approver(pg_engine):
    family = "TASK"
    primary = _session(pg_engine)
    try:
        admin = _make_admin(primary)
        pv = (primary.query(SecurityPrincipalVersion)
              .filter_by(user_id=admin.id).one().version)
        ver = _fence_version(primary, family)

        scope = {
            "schema_version": 1, "operation_id": "CUTOVER_MARK",
            "packet_id": "CUTOVER-MODE-01", "target_ids_or_family": family,
            "phase": "mark", "artifact_sha256": "d" * 64,
            "expected_version": ver, "expected_generation": 1,
        }
        secret_b64, raw = root_store.new_one_time_secret()
        now = now_utc_naive()
        approval = OpsApprovalRequest(
            id=str(uuid.uuid4()), operation_type="CUTOVER_MARK",
            scope_sha256=compute_scope_sha256(scope), artifact_sha256="d" * 64,
            expected_version=ver, expected_generation=1,
            nonce_hash=nonce_hash_from_secret(raw),
            expires_at=now + datetime.timedelta(seconds=600), state="APPROVED",
            approved_by_user_id=admin.id, approved_principal_version=pv, approved_at=now,
            operator_identity_hash="0" * 64, created_at=now,
        )
        primary.add(approval)
        primary.commit()
        approval_id = approval.id

        def _mut(session):
            row = (session.query(OpsApprovalRequest)
                   .filter_by(nonce_hash=nonce_hash_from_secret(raw)).one())
            return mark_cutover(
                session, family, ver, cutover_sha="feed", cutover_generation=1,
                minimum_compatibility_generation=1, readiness_artifact_sha256="d" * 64,
                ops_approval_id=row.id, approved_by_admin_user_id=row.approved_by_user_id,
            )

        consume_same_db(
            primary, operation_id="CUTOVER_MARK", scope_obj=scope,
            artifact_sha256="d" * 64, expected_version=ver, expected_generation=1,
            raw_secret=raw, target_mutation=_mut,
        )
        primary.commit()

        # marker 의 approved_by_admin_user_id + ops_approval_id 가 approval row 에서 복사됨.
        marker = primary.execute(
            text("SELECT approved_by_admin_user_id, ops_approval_id FROM "
                 "feature_cutover_markers WHERE family=:f"),
            {"f": family},
        ).first()
        assert marker[0] == admin.id
        assert str(marker[1]) == str(approval_id)
        # approval 은 CONSUMED.
        assert primary.query(OpsApprovalRequest).filter_by(id=approval_id).one().state == "CONSUMED"
    finally:
        primary.close()


# --------------------------------------------------------------------------- #
# 7. transactional helper: unknown family → error (DB fault 전 503/변화 0)
# --------------------------------------------------------------------------- #
def test_begin_transactional_mode_unknown_family_raises(pg_engine):
    s = _session(pg_engine)
    try:
        with pytest.raises(CutoverModeError):
            begin_transactional_mode(s, "NOT_A_FAMILY")
        s.rollback()
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 8. mode manifest 15-row 양방향 (순수, DB 불필요)
# --------------------------------------------------------------------------- #
def test_mode_manifest_shape_and_bidirectional_green():
    m = load_manifest()
    assert_row_shape(m)
    assert len(m["families"]) == 15
    diff = manifest_vs_inventory_bidirectional(m)
    assert diff == {"missing_families": [], "extra_families": [], "field_mismatch": []}, diff


def test_mode_manifest_bidirectional_flags_mismatch():
    m = load_manifest()
    # 개수 불일치 → red.
    m2 = {"schema_version": m["schema_version"],
          "families": {k: v for k, v in m["families"].items() if k != "UPLOAD"}}
    diff = manifest_vs_inventory_bidirectional(m2)
    assert "UPLOAD" in diff["missing_families"]

    # 필드 변조 → field_mismatch.
    import copy
    m3 = copy.deepcopy(m)
    m3["families"]["ASSIGNMENT"]["stability_seconds"] = 999
    diff3 = manifest_vs_inventory_bidirectional(m3)
    assert "ASSIGNMENT.stability_seconds" in diff3["field_mismatch"]


# --------------------------------------------------------------------------- #
# 9. build_compatibility generation 규칙 (순수, DB 불필요)
# --------------------------------------------------------------------------- #
def test_build_compatibility_structure_valid():
    obj = load_build_compatibility()
    validate_structure(obj)  # no raise
    assert obj["generation"] == obj["supersedes_generation"] + 1
    assert set(obj["state_aware_families"]) <= set(FEATURE_CUTOVER_FAMILIES)


@pytest.mark.parametrize("mutate", ["gen_not_positive", "chain_broken", "unknown_family", "extra_field"])
def test_build_compatibility_rejects_violations(mutate):
    base = {"schema_version": 1, "generation": 2, "supersedes_generation": 1,
            "state_aware_families": ["ASSIGNMENT"]}
    if mutate == "gen_not_positive":
        base["generation"] = 0; base["supersedes_generation"] = -1
    elif mutate == "chain_broken":
        base["supersedes_generation"] = 0  # gen 2 != 0+1
    elif mutate == "unknown_family":
        base["state_aware_families"] = ["NOPE"]
    elif mutate == "extra_field":
        base["surprise"] = 1
    with pytest.raises(BuildCompatibilityError):
        validate_structure(base)


def test_build_compatibility_merge_base_chain():
    base = {"schema_version": 1, "generation": 1, "supersedes_generation": 0,
            "state_aware_families": ["ASSIGNMENT"]}
    good = {"schema_version": 1, "generation": 2, "supersedes_generation": 1,
            "state_aware_families": ["ASSIGNMENT"]}
    verify_against_merge_base(good, base, incompatible_change=True)  # +1 bump OK

    # supersedes 가 merge-base generation 과 불연속 → red.
    bad = {"schema_version": 1, "generation": 3, "supersedes_generation": 2,
           "state_aware_families": ["ASSIGNMENT"]}
    with pytest.raises(BuildCompatibilityError):
        verify_against_merge_base(bad, base, incompatible_change=False)
