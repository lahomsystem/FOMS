"""WDC-LINK-FENCE-00 계약 테스트 (PGTEST-00 lane + 순수 closed-set).

CUTOVER-MODE-01 fence 체계 위에 additive 로 얹은 WDC link cutover fence 를 검증한다:

* fence 3종(``WDC_LINK_FREEZE|ABORT|CANONICAL``)이 WDC-LINK-FENCE-00 이 소유하는 ops-approval
  operation 과 exact 일치(§4.4 closed-set, 양방향).
* SEPARATE topology 만 ``db_mode=TARGET_RESERVED``(SAME 은 SAME) — ops manifest seed 대조.
* generic ``WDC_LINK`` family 가 CUTOVER 15-family closed set 에 그대로 남아 있음(회귀 가드).
* SEPARATE singleton ``wdc_link_runtime_state`` 의 ``LEGACY → FROZEN → CANONICAL`` /
  ``FROZEN → LEGACY(generation+1)`` 전이, fingerprint / rollout 기록, state version / generation,
  primary marker gate, freeze ``FOR UPDATE`` 가 legacy ``FOR KEY SHARE`` 를 drain 하는 원자성.

``FOMS_TEST_DATABASE_URL`` 미설정이면 PG 테스트는 skip 된다(conftest). 순수 closed-set /
topology 테스트는 DB 불필요다. 커밋 파일에 비밀번호를 넣지 않는다(dev DSN 은 env 로 주입).

격리 메모: pg_engine 은 session-scoped(파일 내 테스트가 DB 공유)다. singleton 은 trigger 가
없어 ``DELETE`` 로 매 테스트 초기화한다. primary ``WDC_LINK`` marker 는 irreversible trigger 로
DELETE 불가이므로 marker 를 쓰는 흐름은 **commit 하지 않고 rollback** 한다(committed WDC_LINK
marker 를 이 파일은 절대 남기지 않는다).
"""
from __future__ import annotations

import threading
import time
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker
from werkzeug.security import generate_password_hash

from models import User
from foms.services.security.cutover.families import FEATURE_CUTOVER_FAMILIES
from foms.services.security.ops_approval_manifest import (
    EXPECTED_OWNER_OPERATIONS,
    load_operations_manifest,
)
from foms.services.security.cutover.mode_manifest import (
    assert_row_shape,
    load_manifest,
    manifest_vs_inventory_bidirectional,
)
from foms.services.security.cutover.wdc_link_fence import (
    DB_MODE_SAME,
    DB_MODE_TARGET_RESERVED,
    TOPOLOGY_SAME,
    TOPOLOGY_SEPARATE,
    WDC_LINK_FAMILY,
    WDC_LINK_FENCES,
    WDCLinkFenceError,
    abort_wdc_link,
    begin_wdc_link_legacy_write,
    canonicalize_wdc_link,
    db_mode_for_topology,
    freeze_wdc_link,
    seed_wdc_link_runtime_state,
)

_FP = "f" * 64          # freeze source fingerprint
_FP_DRIFT = "9" * 64
_ROLLOUT = "a" * 64     # consumer rollout artifact sha256


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _session(pg_engine):
    return sessionmaker(bind=pg_engine)()


_UNAME_SEQ = [0]


def _make_admin(session):
    _UNAME_SEQ[0] += 1
    u = User(
        username=f"wdcadmin_{_UNAME_SEQ[0]}_{int(time.time() * 1000) % 100000}",
        password=generate_password_hash("pw-not-committed"),
        name="승인자", role="ADMIN", team=None, is_active=True,
    )
    session.add(u)
    session.commit()
    return u


def _fresh_singleton(session):
    """singleton 을 DELETE 후 LEGACY / generation=0 으로 재seed(미commit — 호출자 commit)."""
    session.execute(text("DELETE FROM wdc_link_runtime_state"))
    inserted = seed_wdc_link_runtime_state(session)
    assert inserted is True
    return inserted


def _state(session, col):
    return session.execute(
        text(f"SELECT {col} FROM wdc_link_runtime_state WHERE id = 1")
    ).scalar()


def _insert_wdc_marker(session, admin_id):
    """primary WDC_LINK feature-cutover marker insert(미commit — irreversible 이라 rollback 전용)."""
    session.execute(
        text(
            "INSERT INTO feature_cutover_markers "
            "(family, cutover_sha, cutover_generation, minimum_compatibility_generation, "
            " readiness_artifact_sha256, ops_approval_id, approved_by_admin_user_id) "
            "VALUES (:f, 'sha', 1, 1, :art, :aid, :u)"
        ),
        {"f": WDC_LINK_FAMILY, "art": _ROLLOUT, "aid": str(uuid.uuid4()), "u": admin_id},
    )


# --------------------------------------------------------------------------- #
# 1. fence 3종 == ops-approval owner closed set + SEPARATE TARGET_RESERVED (순수)
# --------------------------------------------------------------------------- #
def test_wdc_link_fences_match_ops_owner_closed_set():
    owner_ops = EXPECTED_OWNER_OPERATIONS["WDC-LINK-FENCE-00"]
    # code fence enum ↔ ops owner 표 exact 일치(양방향).
    assert set(WDC_LINK_FENCES) == set(owner_ops)
    assert len(WDC_LINK_FENCES) == 3

    manifest = load_operations_manifest()["operations"]
    owned_in_manifest = sorted(
        op for op, meta in manifest.items() if meta.get("owner_packet") == "WDC-LINK-FENCE-00"
    )
    assert owned_in_manifest == sorted(WDC_LINK_FENCES)

    # SEPARATE topology 만 TARGET_RESERVED(seed 대조), SAME 은 SAME.
    assert db_mode_for_topology(TOPOLOGY_SEPARATE) == DB_MODE_TARGET_RESERVED
    assert db_mode_for_topology(TOPOLOGY_SAME) == DB_MODE_SAME
    for op in WDC_LINK_FENCES:
        assert manifest[op]["db_mode"] == DB_MODE_TARGET_RESERVED == db_mode_for_topology(TOPOLOGY_SEPARATE)

    with pytest.raises(ValueError):
        db_mode_for_topology("NOT_A_TOPOLOGY")


# --------------------------------------------------------------------------- #
# 2. CUTOVER 15-family closed set 에 WDC_LINK 유지(회귀 가드, 순수)
# --------------------------------------------------------------------------- #
def test_feature_cutover_closed_set_still_15_with_wdc_link():
    assert WDC_LINK_FAMILY in FEATURE_CUTOVER_FAMILIES
    assert len(FEATURE_CUTOVER_FAMILIES) == 15
    m = load_manifest()
    assert_row_shape(m)
    assert len(m["families"]) == 15
    diff = manifest_vs_inventory_bidirectional(m)
    assert diff == {"missing_families": [], "extra_families": [], "field_mismatch": []}, diff


# --------------------------------------------------------------------------- #
# 3. seed idempotent + legacy writer 가 LEGACY 를 읽는다(unseeded 는 예외)
# --------------------------------------------------------------------------- #
def test_seed_idempotent_and_legacy_writer_reads_legacy(pg_engine):
    s = _session(pg_engine)
    try:
        s.execute(text("DELETE FROM wdc_link_runtime_state"))
        assert seed_wdc_link_runtime_state(s) is True   # 최초 insert
        assert seed_wdc_link_runtime_state(s) is False  # idempotent no-op
        s.commit()

        st = begin_wdc_link_legacy_write(s)
        assert st.mode == "LEGACY"
        assert st.accepts_new_legacy is True
        assert st.generation == 0 and st.row_version == 1
        s.rollback()

        # unseeded → 예외(SAME topology 오용 / 미seed 방어).
        s.execute(text("DELETE FROM wdc_link_runtime_state"))
        s.commit()
        with pytest.raises(WDCLinkFenceError):
            begin_wdc_link_legacy_write(s)
        s.rollback()
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 4. freeze: LEGACY→FROZEN, fingerprint / rollout / prepared_gen 기록, version bump
# --------------------------------------------------------------------------- #
def test_freeze_records_fingerprint_rollout_and_bumps_version(pg_engine):
    s = _session(pg_engine)
    try:
        _fresh_singleton(s)
        s.commit()

        ver = _state(s, "row_version")
        freeze_wdc_link(
            s, ver, freeze_source_fingerprint=_FP,
            freeze_rollout_artifact_sha256=_ROLLOUT, prepared_consumer_generation=2,
        )
        s.commit()

        assert _state(s, "mode") == "FROZEN"
        assert _state(s, "row_version") == ver + 1          # state version bump
        assert _state(s, "generation") == 0                 # freeze 는 generation 불변
        assert _state(s, "prepared_consumer_generation") == 2
        assert _state(s, "freeze_source_fingerprint") == _FP
        assert _state(s, "freeze_rollout_artifact_sha256") == _ROLLOUT
        assert _state(s, "frozen_at") is not None

        # FROZEN 상태의 legacy writer 는 새 legacy 를 받지 않는다.
        st = begin_wdc_link_legacy_write(s)
        assert st.is_frozen and st.accepts_new_legacy is False
        s.rollback()
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 5. freeze 거부: 비 LEGACY / row_version 불일치
# --------------------------------------------------------------------------- #
def test_freeze_rejects_non_legacy_and_version_mismatch(pg_engine):
    s = _session(pg_engine)
    try:
        _fresh_singleton(s)
        s.commit()

        # row_version 불일치 → 거부.
        with pytest.raises(WDCLinkFenceError):
            freeze_wdc_link(
                s, 999, freeze_source_fingerprint=_FP,
                freeze_rollout_artifact_sha256=_ROLLOUT, prepared_consumer_generation=1,
            )
        s.rollback()

        # 정상 freeze → FROZEN.
        ver = _state(s, "row_version")
        freeze_wdc_link(
            s, ver, freeze_source_fingerprint=_FP,
            freeze_rollout_artifact_sha256=_ROLLOUT, prepared_consumer_generation=1,
        )
        s.commit()

        # 두 번째 freeze → mode!=LEGACY 로 거부.
        ver = _state(s, "row_version")
        with pytest.raises(WDCLinkFenceError):
            freeze_wdc_link(
                s, ver, freeze_source_fingerprint=_FP,
                freeze_rollout_artifact_sha256=_ROLLOUT, prepared_consumer_generation=1,
            )
        s.rollback()
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 6. canonical: FROZEN→CANONICAL, primary marker gate(marker 前 거부)
# --------------------------------------------------------------------------- #
def test_canonical_requires_frozen_and_primary_marker(pg_engine):
    s = _session(pg_engine)
    try:
        _fresh_singleton(s)
        s.commit()

        # LEGACY 에서 canonical → FROZEN 아님으로 거부.
        with pytest.raises(WDCLinkFenceError):
            canonicalize_wdc_link(s, _state(s, "row_version"))
        s.rollback()

        # freeze → FROZEN(commit).
        ver = _state(s, "row_version")
        freeze_wdc_link(
            s, ver, freeze_source_fingerprint=_FP,
            freeze_rollout_artifact_sha256=_ROLLOUT, prepared_consumer_generation=1,
        )
        s.commit()

        # marker 前 canonical → 거부.
        with pytest.raises(WDCLinkFenceError):
            canonicalize_wdc_link(s, _state(s, "row_version"))
        s.rollback()

        # primary WDC_LINK marker insert(미commit) 후 canonical → CANONICAL. 전체 rollback.
        admin_id = _make_admin(s).id
        _insert_wdc_marker(s, admin_id)
        ver = _state(s, "row_version")
        canonicalize_wdc_link(s, ver)
        assert _state(s, "mode") == "CANONICAL"
        assert _state(s, "row_version") == ver + 1
        s.rollback()  # marker(irreversible) + CANONICAL 폐기 — committed marker 0.
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 7. abort: FROZEN→LEGACY, generation+1, fingerprint drift STOP
# --------------------------------------------------------------------------- #
def test_abort_frozen_to_legacy_generation_bump_and_fingerprint_drift(pg_engine):
    s = _session(pg_engine)
    try:
        _fresh_singleton(s)
        s.commit()

        ver = _state(s, "row_version")
        freeze_wdc_link(
            s, ver, freeze_source_fingerprint=_FP,
            freeze_rollout_artifact_sha256=_ROLLOUT, prepared_consumer_generation=3,
        )
        s.commit()
        assert _state(s, "mode") == "FROZEN" and _state(s, "generation") == 0

        # fingerprint drift → STOP.
        with pytest.raises(WDCLinkFenceError):
            abort_wdc_link(
                s, _state(s, "row_version"),
                expected_generation=0, expected_freeze_fingerprint=_FP_DRIFT,
            )
        s.rollback()

        # generation 불일치 → 거부.
        with pytest.raises(WDCLinkFenceError):
            abort_wdc_link(
                s, _state(s, "row_version"),
                expected_generation=99, expected_freeze_fingerprint=_FP,
            )
        s.rollback()

        # 정상 abort → LEGACY, generation 0→1, fingerprint / rollout / prepared_gen clear.
        ver = _state(s, "row_version")
        abort_wdc_link(s, ver, expected_generation=0, expected_freeze_fingerprint=_FP)
        s.commit()
        assert _state(s, "mode") == "LEGACY"
        assert _state(s, "generation") == 1
        assert _state(s, "row_version") == ver + 1
        assert _state(s, "freeze_source_fingerprint") is None
        assert _state(s, "freeze_rollout_artifact_sha256") is None
        assert _state(s, "prepared_consumer_generation") is None
        assert _state(s, "frozen_at") is None
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 8. marker 뒤 abort 금지(roll-forward only)
# --------------------------------------------------------------------------- #
def test_abort_forbidden_after_primary_marker(pg_engine):
    s = _session(pg_engine)
    try:
        _fresh_singleton(s)
        s.commit()
        ver = _state(s, "row_version")
        freeze_wdc_link(
            s, ver, freeze_source_fingerprint=_FP,
            freeze_rollout_artifact_sha256=_ROLLOUT, prepared_consumer_generation=1,
        )
        s.commit()

        admin_id = _make_admin(s).id
        _insert_wdc_marker(s, admin_id)  # 미commit
        with pytest.raises(WDCLinkFenceError):
            abort_wdc_link(
                s, _state(s, "row_version"),
                expected_generation=0, expected_freeze_fingerprint=_FP,
            )
        s.rollback()  # marker 폐기.
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 9. 원자성: legacy FOR KEY SHARE → freeze FOR UPDATE 가 drain 후에만 성공
# --------------------------------------------------------------------------- #
def test_freeze_for_update_drains_legacy_key_share(pg_engine):
    setup = _session(pg_engine)
    try:
        _fresh_singleton(setup)
        setup.commit()
        expected_version = _state(setup, "row_version")
    finally:
        setup.close()

    barrier = threading.Event()
    a_committed = threading.Event()
    events = []
    outcome = {}

    def hold_legacy():
        a = _session(pg_engine)
        try:
            st = begin_wdc_link_legacy_write(a)  # FOR KEY SHARE
            events.append(st.mode)
            barrier.set()
            time.sleep(0.8)  # lock 보유 → freeze 의 FOR UPDATE 블록
            a.commit()
            a_committed.set()
        finally:
            a.close()

    def do_freeze():
        barrier.wait(2.0)
        b = _session(pg_engine)
        t0 = time.time()
        try:
            freeze_wdc_link(
                b, expected_version, freeze_source_fingerprint=_FP,
                freeze_rollout_artifact_sha256=_ROLLOUT, prepared_consumer_generation=1,
            )
            b.commit()
            outcome["waited"] = time.time() - t0
            outcome["freeze"] = "ok"
        except Exception as exc:  # noqa: BLE001
            b.rollback()
            outcome["freeze"] = f"fail:{exc}"
        finally:
            b.close()

    ta = threading.Thread(target=hold_legacy)
    tb = threading.Thread(target=do_freeze)
    ta.start(); tb.start(); ta.join(5.0); tb.join(5.0)

    assert events == ["LEGACY"], events
    assert outcome.get("freeze") == "ok", outcome
    assert a_committed.is_set()
    assert outcome["waited"] > 0.4, f"freeze must block on FOR KEY SHARE until legacy commits: {outcome}"

    # 이후 상태는 FROZEN(원자 전이 반영).
    c = _session(pg_engine)
    try:
        assert _state(c, "mode") == "FROZEN"
    finally:
        c.close()
