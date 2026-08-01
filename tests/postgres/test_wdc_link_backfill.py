"""WDC-LINK-BACKFILL-00 — V1 EstimateOrderMatch → V2 EstimateOrderLinkV2 계약 테스트.

세 층을 검증한다:

* **순수 도메인**(PG/DPAPI 불필요): SAFE(unique pair)/MANUAL 분류, 중복 pair dedup(source-target
  equivalence), coverage 100%, manifest/mapping sha 결정성, phase_for_topology conflation 0.
* **암호화 artifact**(DPAPI — Windows 전용, 비-Windows skip): write→load round-trip, 변조 감지
  (manifest/ciphertext), SAME↔SEPARATE phase conflation 시 복호화 거부.
* **PG 통합**(``FOMS_TEST_DATABASE_URL`` 필요·conftest 가 미설정이면 skip): SAME online atomic
  dual-write(unique pair·equivalence·V1 불변·V1 cleanup 0·멱등 resume), SEPARATE FROZEN gate
  (unfrozen apply 거부·FROZEN apply), phase run_id 분리, manual 무발급.

DSN 은 env 로만 주입한다(비밀번호 커밋 0).
"""
from __future__ import annotations

import datetime
import json
import os

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from foms.services.orders.audit_estimate_order_links import (
    INVALID_ESTIMATE_ID,
    INVALID_ORDER_ID,
    MANUAL,
    SAFE,
    AuditReport,
    build_report,
    parse_safe_csv,
    safe_csv,
)
from foms.services.orders.backfill_estimate_order_links import (
    PHASE_SAME,
    PHASE_SEPARATE,
    TOPOLOGY_SAME,
    TOPOLOGY_SEPARATE,
    LinkArtifactError,
    WDCLinkBackfillError,
    load_link_artifact,
    phase_for_topology,
    run_backfill,
    write_link_artifact,
)
from foms.services.security.backfill import crypto, runs

NOW = datetime.datetime(2026, 7, 26, 12, 0, 0)
_WINDOWS_ONLY = pytest.mark.skipif(os.name != "nt", reason="DPAPI artifact is Windows-only")


# --------------------------------------------------------------------------- #
# 1. 분류 (순수)
# --------------------------------------------------------------------------- #
def _rows(*triples):
    """(match_id, estimate_id, order_id) 튜플 목록."""
    return list(triples)


def test_distinct_valid_pairs_are_safe_one_each():
    report = build_report(_rows((1, 10, 100), (2, 11, 101), (3, 10, 101)))
    assert report.counts[SAFE] == 3
    assert report.counts[MANUAL] == 0
    pairs = {(l.estimate_id, l.order_id): l for l in report.safe_links}
    assert set(pairs) == {(10, 100), (11, 101), (10, 101)}
    for link in report.safe_links:
        assert link.duplicate_count == 0
        assert link.source_row_ids == (link.source_match_id,)


def test_duplicate_pair_collapses_to_unique_pair_min_provenance():
    # 같은 (10,100) 이 세 V1 row(id 3,1,7) 로 중복 → canonical 하나, source_match_id=min(=1).
    report = build_report(_rows((3, 10, 100), (1, 10, 100), (7, 10, 100), (2, 11, 200)))
    assert report.counts[SAFE] == 2  # (10,100) 하나 + (11,200) 하나
    dup = next(l for l in report.safe_links if (l.estimate_id, l.order_id) == (10, 100))
    assert dup.source_match_id == 1              # 최소 id
    assert dup.source_row_ids == (1, 3, 7)       # 구성 row 전체(정렬)
    assert dup.duplicate_count == 2              # 3개 중 2개 접힘
    assert report.duplicate_rows == 2
    assert report.safe_rows == 4                 # 3 + 1


def test_invalid_estimate_id_is_manual():
    for bad in (0, -5, None):
        report = build_report(_rows((1, bad, 100)))
        assert report.counts[MANUAL] == 1
        assert report.counts[SAFE] == 0
        assert report.manual_links[0].reason == INVALID_ESTIMATE_ID


def test_invalid_order_id_is_manual():
    for bad in (0, -1, None):
        report = build_report(_rows((1, 10, bad)))
        assert report.counts[MANUAL] == 1
        assert report.manual_links[0].reason == INVALID_ORDER_ID


def test_coverage_total_equals_safe_rows_plus_manual():
    report = build_report(_rows((1, 10, 100), (2, 10, 100), (3, 0, 5), (4, 9, 0)))
    assert report.total_v1_rows == 4
    assert report.unclassified == 0
    assert report.safe_rows + len(report.manual_links) == report.total_v1_rows


def test_manifest_mapping_sha_deterministic_and_pii_free():
    r1 = build_report(_rows((1, 10, 100), (2, 11, 200)))
    r2 = build_report(_rows((2, 11, 200), (1, 10, 100)))  # 순서만 다름
    assert r1.manifest_sha256() == r2.manifest_sha256()
    assert r1.mapping_sha256() == r2.mapping_sha256()
    assert r1.source_composite_sha256() == r2.source_composite_sha256()
    # source_composite 는 pair 구성 변화에 민감(drift 감지).
    r3 = build_report(_rows((1, 10, 100), (2, 11, 200), (3, 11, 200)))
    assert r3.source_composite_sha256() != r1.source_composite_sha256()


def test_phase_for_topology_no_conflation():
    assert phase_for_topology(TOPOLOGY_SAME) == PHASE_SAME
    assert phase_for_topology(TOPOLOGY_SEPARATE) == PHASE_SEPARATE
    assert PHASE_SAME != PHASE_SEPARATE
    with pytest.raises(WDCLinkBackfillError):
        phase_for_topology("NOT_A_TOPOLOGY")


def test_run_id_differs_by_topology_same_audit():
    """같은 audit 라도 위상 phase 가 달라 run_id 가 다르다(phase conflation 구조적 0)."""
    audit = build_report(_rows((1, 10, 100), (2, 11, 200)))
    m, mp = audit.manifest_sha256(), audit.mapping_sha256()
    same_id = runs.compute_run_id("WDC-LINK-BACKFILL-00", PHASE_SAME, m, mp)
    sep_id = runs.compute_run_id("WDC-LINK-BACKFILL-00", PHASE_SEPARATE, m, mp)
    assert same_id != sep_id


def test_safe_csv_roundtrips_to_targets():
    audit = build_report(_rows((3, 10, 100), (1, 10, 100), (2, 11, 200)))
    targets = parse_safe_csv(safe_csv(audit))
    assert {(t.estimate_id, t.order_id) for t in targets} == {(10, 100), (11, 200)}
    dedup = next(t for t in targets if (t.estimate_id, t.order_id) == (10, 100))
    assert dedup.source_match_id == 1


# --------------------------------------------------------------------------- #
# 2. 암호화 artifact (DPAPI — Windows 전용)
# --------------------------------------------------------------------------- #
def _audit_with_manual() -> AuditReport:
    return build_report(_rows((1, 10, 100), (2, 10, 100), (3, 11, 200), (4, 9, 0)))


@_WINDOWS_ONLY
def test_artifact_roundtrip_recovers_safe_targets(tmp_path):
    audit = _audit_with_manual()
    meta = write_link_artifact(
        tmp_path, audit, topology=TOPOLOGY_SAME, db_instance_id="test-db", now=NOW
    )
    assert meta["phase"] == PHASE_SAME
    # 암호화 파일이 실제로 존재(plaintext 아님).
    enc = json.loads((tmp_path / "safe.csv.enc").read_text(encoding="utf-8"))
    assert enc["alg"] == "AES-256-GCM" and "ciphertext_b64url" in enc

    loaded = load_link_artifact(tmp_path, topology=TOPOLOGY_SAME, db_instance_id="test-db")
    assert loaded.topology == TOPOLOGY_SAME
    assert {(t.estimate_id, t.order_id) for t in loaded.safe_targets} == {(10, 100), (11, 200)}
    assert loaded.masked_counts["manual_rows"] == 1
    assert loaded.masked_counts["duplicate_rows"] == 1


@_WINDOWS_ONLY
def test_artifact_manifest_tamper_detected(tmp_path):
    write_link_artifact(tmp_path, _audit_with_manual(), topology=TOPOLOGY_SAME,
                        db_instance_id="test-db", now=NOW)
    m = tmp_path / "manifest.json"
    m.write_bytes(m.read_bytes() + b" ")  # sha.txt 와 불일치
    with pytest.raises(LinkArtifactError):
        load_link_artifact(tmp_path, topology=TOPOLOGY_SAME, db_instance_id="test-db")


@_WINDOWS_ONLY
def test_artifact_ciphertext_tamper_detected(tmp_path):
    write_link_artifact(tmp_path, _audit_with_manual(), topology=TOPOLOGY_SAME,
                        db_instance_id="test-db", now=NOW)
    enc_path = tmp_path / "safe.csv.enc"
    env = json.loads(enc_path.read_text(encoding="utf-8"))
    env["ciphertext_b64url"] = env["ciphertext_b64url"][:-4] + "AAAA"  # GCM tag 파손
    enc_path.write_text(json.dumps(env), encoding="utf-8")
    with pytest.raises(crypto.BackfillCryptoError):
        load_link_artifact(tmp_path, topology=TOPOLOGY_SAME, db_instance_id="test-db")


@_WINDOWS_ONLY
def test_artifact_phase_conflation_rejected(tmp_path):
    """SAME phase 로 쓴 artifact 를 SEPARATE 로 로드하면 거부(phase conflation 0)."""
    write_link_artifact(tmp_path, _audit_with_manual(), topology=TOPOLOGY_SAME,
                        db_instance_id="test-db", now=NOW)
    with pytest.raises((LinkArtifactError, crypto.BackfillCryptoError)):
        load_link_artifact(tmp_path, topology=TOPOLOGY_SEPARATE, db_instance_id="test-db")


# --------------------------------------------------------------------------- #
# 3. PG 통합
# --------------------------------------------------------------------------- #
def _wd_tables(pg_engine):
    """test DB 에 WDCalculator(V1) 테이블을 생성(public schema — test engine 기본 search_path)."""
    from wdcalculator_db import WDCalculatorBase

    WDCalculatorBase.metadata.create_all(bind=pg_engine)


def _reset(pg_engine):
    with pg_engine.begin() as conn:
        conn.execute(text("DELETE FROM estimate_order_links_v2"))
        conn.execute(text("DELETE FROM maintenance_backfill_checkpoints"))
        conn.execute(text("DELETE FROM maintenance_backfill_approvals"))
        conn.execute(text("DELETE FROM maintenance_backfill_runs"))
        conn.execute(text("DELETE FROM wdc_link_runtime_state"))
        # V1(WDC) 테이블은 create 됐을 때만 정리.
        for tbl in ("estimate_order_matches", "estimate_histories", "estimates"):
            conn.execute(text(f"DELETE FROM {tbl}"))


@pytest.fixture
def link_db(pg_engine):
    _wd_tables(pg_engine)
    _reset(pg_engine)
    yield pg_engine
    _reset(pg_engine)


def _make_estimate(session, customer):
    from wdcalculator_models import Estimate

    est = Estimate(customer_name=customer, estimate_data={"items": []})
    session.add(est)
    session.flush()
    return est.id


def _add_match(session, estimate_id, order_id):
    from wdcalculator_models import EstimateOrderMatch

    m = EstimateOrderMatch(estimate_id=estimate_id, order_id=order_id)
    session.add(m)
    session.flush()
    return m.id


def _activate(s, run):
    """OPS approval 대체(테스트) — apply lease 가 요구하는 seq≥1 을 활성화."""
    run.current_approval_seq = 1


def _v2_pairs(session):
    from models import EstimateOrderLinkV2

    return {
        (e, o): (topo, src, rid)
        for e, o, topo, src, rid in session.query(
            EstimateOrderLinkV2.estimate_id,
            EstimateOrderLinkV2.order_id,
            EstimateOrderLinkV2.source_topology,
            EstimateOrderLinkV2.source_match_id,
            EstimateOrderLinkV2.backfill_run_id,
        ).all()
    }


def _v1_count(session):
    from wdcalculator_models import EstimateOrderMatch

    return session.query(EstimateOrderMatch.id).count()


def test_pg_same_dualwrite_unique_pair_equivalence_v1_immutable(link_db):
    session = sessionmaker(bind=link_db)()
    try:
        e1 = _make_estimate(session, "고객1")
        e2 = _make_estimate(session, "고객2")
        # (e1,100) 중복 3회 → V2 하나로 dedup, (e1,101), (e2,100) 각 1.
        d1 = _add_match(session, e1, 100)
        _add_match(session, e1, 100)
        _add_match(session, e1, 100)
        _add_match(session, e1, 101)
        _add_match(session, e2, 100)
        session.commit()
        v1_before = _v1_count(session)

        report = run_backfill(
            session, topology=TOPOLOGY_SAME, db_instance_id="test-db",
            owner_identity="tester", now=NOW, activate_approval=_activate,
        )
        assert report.state == "DONE"
        assert report.total_pairs == 3           # 고유 pair 3
        assert report.completed_rows == 3
        assert report.minted == 3
        assert report.phase == PHASE_SAME

        pairs = _v2_pairs(session)
        # unique pair: 중복 (e1,100) 이 정확히 하나.
        assert set(pairs) == {(e1, 100), (e1, 101), (e2, 100)}
        # source-target equivalence + provenance(min id) + topology + phase run id.
        topo, src, rid = pairs[(e1, 100)]
        assert topo == TOPOLOGY_SAME
        assert src == d1                          # 최소 V1 id
        assert rid == report.run_id               # phase run id 연결
        # V1 불변·cleanup 0.
        assert _v1_count(session) == v1_before
    finally:
        session.close()


def test_pg_mint_skips_existing_pair_resume_safe(link_db):
    """이미 V2 에 있는 pair 는 재발급하지 않는다(resume/멱등 — unique pair 중복 발급 0)."""
    from models import EstimateOrderLinkV2

    session = sessionmaker(bind=link_db)()
    try:
        e1 = _make_estimate(session, "고객1")
        _add_match(session, e1, 100)
        _add_match(session, e1, 101)
        # (e1,100) 은 앞선(중단된) run 이 이미 발급했다고 가정하고 미리 심는다.
        session.add(EstimateOrderLinkV2(
            estimate_id=e1, order_id=100, source_topology=TOPOLOGY_SAME,
            source_match_id=1, backfill_run_id="prior-run", linked_at=NOW,
        ))
        session.commit()

        report = run_backfill(session, topology=TOPOLOGY_SAME, db_instance_id="test-db",
                              owner_identity="tester", now=NOW, activate_approval=_activate)
        assert report.state == "DONE"
        assert report.minted == 1            # (e1,101) 만 신규
        assert report.skipped_existing == 1  # (e1,100) 은 건너뜀
        pairs = _v2_pairs(session)
        assert set(pairs) == {(e1, 100), (e1, 101)}
        # 기존 row 는 그대로(중복 발급/덮어쓰기 0) — prior run id 보존.
        assert pairs[(e1, 100)][2] == "prior-run"
    finally:
        session.close()


def test_pg_separate_requires_frozen_fence(link_db):
    from foms.services.security.cutover.wdc_link_fence import (
        freeze_wdc_link,
        seed_wdc_link_runtime_state,
    )

    # --- LEGACY: unfrozen apply 거부 ---
    session = sessionmaker(bind=link_db)()
    try:
        e1 = _make_estimate(session, "고객1")
        _add_match(session, e1, 100)
        session.commit()
        seed_wdc_link_runtime_state(session)  # mode=LEGACY
        session.commit()

        with pytest.raises(WDCLinkBackfillError):
            run_backfill(session, topology=TOPOLOGY_SEPARATE, db_instance_id="test-db",
                         owner_identity="tester", now=NOW, activate_approval=_activate)
        session.rollback()
        # unfrozen 이므로 V2 발급 0.
        assert _v2_pairs(session) == {}
    finally:
        session.close()

    # --- FROZEN: apply 성공 ---
    session = sessionmaker(bind=link_db)()
    try:
        ver = session.execute(
            text("SELECT row_version FROM wdc_link_runtime_state WHERE id=1")
        ).scalar()
        freeze_wdc_link(
            session, ver, freeze_source_fingerprint="f" * 64,
            freeze_rollout_artifact_sha256="a" * 64, prepared_consumer_generation=1,
        )
        session.commit()

        report = run_backfill(session, topology=TOPOLOGY_SEPARATE, db_instance_id="test-db",
                              owner_identity="tester", now=NOW, activate_approval=_activate)
        assert report.state == "DONE"
        assert report.phase == PHASE_SEPARATE
        pairs = _v2_pairs(session)
        e1 = next(iter(pairs))[0]
        assert pairs == {(e1, 100): (TOPOLOGY_SEPARATE, pairs[(e1, 100)][1], report.run_id)}
    finally:
        session.close()


def test_pg_phase_run_ids_differ_same_vs_separate(link_db):
    """SAME run 과 SEPARATE run 의 run_id 가 다르다(같은 source·phase conflation 0)."""
    session = sessionmaker(bind=link_db)()
    try:
        from foms.services.security.cutover.wdc_link_fence import (
            freeze_wdc_link,
            seed_wdc_link_runtime_state,
        )

        e1 = _make_estimate(session, "고객1")
        _add_match(session, e1, 100)
        session.commit()

        same = run_backfill(session, topology=TOPOLOGY_SAME, db_instance_id="test-db",
                            owner_identity="tester", now=NOW, activate_approval=_activate)

        seed_wdc_link_runtime_state(session)
        session.commit()
        ver = session.execute(
            text("SELECT row_version FROM wdc_link_runtime_state WHERE id=1")
        ).scalar()
        freeze_wdc_link(session, ver, freeze_source_fingerprint="f" * 64,
                        freeze_rollout_artifact_sha256="a" * 64, prepared_consumer_generation=1)
        session.commit()
        sep = run_backfill(session, topology=TOPOLOGY_SEPARATE, db_instance_id="test-db",
                           owner_identity="tester", now=NOW, activate_approval=_activate)

        assert same.run_id != sep.run_id
        assert same.phase == PHASE_SAME and sep.phase == PHASE_SEPARATE
        # SEPARATE 재발급은 이미 있는 pair 라 skip(멱등) — V2 는 여전히 하나.
        assert sep.minted == 0 and sep.skipped_existing == 1
    finally:
        session.close()


def test_pg_v2_unique_pair_constraint_is_live(link_db):
    """DB 레벨 unique pair 제약이 실제로 존재해 같은 (estimate_id, order_id) 중복을 거부한다."""
    from sqlalchemy.exc import IntegrityError

    from models import EstimateOrderLinkV2

    session = sessionmaker(bind=link_db)()
    try:
        session.add(EstimateOrderLinkV2(
            estimate_id=7, order_id=70, source_topology=TOPOLOGY_SAME,
            source_match_id=1, backfill_run_id="r", linked_at=NOW,
        ))
        session.commit()
        session.add(EstimateOrderLinkV2(
            estimate_id=7, order_id=70, source_topology=TOPOLOGY_SEPARATE,
            source_match_id=2, backfill_run_id="r2", linked_at=NOW,
        ))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
    finally:
        session.close()


def test_pg_manual_invalid_order_not_minted(link_db):
    session = sessionmaker(bind=link_db)()
    try:
        e1 = _make_estimate(session, "고객1")
        _add_match(session, e1, 0)     # order_id=0 → MANUAL(무결성 위반)
        _add_match(session, e1, 100)   # 정상 → SAFE
        session.commit()

        audit = run_backfill(session, topology=TOPOLOGY_SAME, db_instance_id="test-db",
                             owner_identity="tester", now=NOW, activate_approval=_activate)
        assert audit.total_pairs == 1  # (e1,100) 만 SAFE
        pairs = _v2_pairs(session)
        assert set(pairs) == {(e1, 100)}  # order_id=0 은 발급 0
    finally:
        session.close()
