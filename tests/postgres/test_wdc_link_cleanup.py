"""WDC-LINK-CLEANUP-01 — legacy retirement 준비 cleanup audit 계약 테스트.

네 층을 검증한다:

* **순수 분류**(PG/DPAPI 불필요): V1 SAFE pair·Order meta 링크를 canonical V2 멤버십으로
  VERIFIED/AMBIGUOUS 분류, 무결성 위반 meta→ambiguous, coverage 100%, manifest/mapping sha 결정성.
* **정적 가드**(marker/deploy static guard): cleanup 실행 코드에 V1 drop·domain DELETE·V2
  mutation·route/blueprint 부재, run 이 게이트를 ensure_run 전에 강제, separate phase(≠V2),
  V1 drop 마이그레이션 부재.
* **암호화 artifact**(DPAPI — Windows 전용): separate phase(LEGACY_CLEANUP) round-trip, V2
  backfill artifact 로 재사용(복호화) 거부, 변조 감지.
* **PG 통합**(``FOMS_TEST_DATABASE_URL`` 필요·conftest 가 미설정이면 skip): marker/CANONICAL
  effective 전 거부, V2 checkpoint 부재 거부, effective 뒤 verify only(실 삭제 0·V1/V2/Order
  불변)·old generation nonzero·ambiguous 보류·separate run(V2 run_id 재사용 0).

DSN 은 env 로만 주입한다(비밀번호 커밋 0).
"""
from __future__ import annotations

import ast
import datetime
import inspect
import os
import pathlib
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker
from werkzeug.security import generate_password_hash

from foms.services.orders import audit_wdc_link_cleanup as cleanup
from foms.services.orders.audit_wdc_link_cleanup import (
    AMBIGUOUS,
    INVALID_META_ESTIMATE_ID,
    NO_CANONICAL_V2,
    PACKET_ID,
    PHASE,
    SOURCE_ORDER_META,
    SOURCE_V1,
    TOPOLOGY_SAME,
    VERIFIED,
    V2_BACKFILL_PACKET_ID,
    WDCLinkCleanupError,
    WDCLinkCleanupGateError,
    audit_wdc_link_cleanup,
    build_cleanup_report,
    run_cleanup_verify,
)

NOW = datetime.datetime(2026, 7, 26, 12, 0, 0)
_WINDOWS_ONLY = pytest.mark.skipif(os.name != "nt", reason="DPAPI artifact is Windows-only")


# --------------------------------------------------------------------------- #
# 1. 순수 분류
# --------------------------------------------------------------------------- #
def test_v1_and_order_meta_verified_when_in_v2():
    v1 = [(10, 100, 1), (11, 101, 2)]              # SAFE pair (estimate, order, match_id)
    meta = [(100, "10")]                            # order 100 meta → estimate 10
    v2 = {(10, 100), (11, 101)}
    report = build_cleanup_report(v1, meta, v2)
    assert report.counts[VERIFIED] == 3            # 2 V1 + 1 Order meta
    assert report.counts[AMBIGUOUS] == 0
    assert report.old_generation_rows == 3
    assert report.unclassified == 0
    sources = {(i.source, i.estimate_id, i.order_id) for i in report.verified}
    assert (SOURCE_V1, 10, 100) in sources and (SOURCE_ORDER_META, 10, 100) in sources


def test_missing_v2_is_ambiguous_not_removed():
    v1 = [(10, 100, 1)]
    meta = [(200, "99")]                            # (99,200) 은 V2 에 없음 → 보류
    v2 = {(10, 100)}
    report = build_cleanup_report(v1, meta, v2)
    assert report.counts[VERIFIED] == 1
    assert report.counts[AMBIGUOUS] == 1
    amb = report.ambiguous[0]
    assert amb.source == SOURCE_ORDER_META and amb.reason == NO_CANONICAL_V2


def test_invalid_order_meta_estimate_is_ambiguous():
    for bad in ("notanumber", "0", "-3", ""):
        report = build_cleanup_report([], [(300, bad)], set())
        assert report.counts[AMBIGUOUS] == 1
        assert report.ambiguous[0].reason == INVALID_META_ESTIMATE_ID
        assert report.ambiguous[0].estimate_id is None


def test_coverage_total_equals_verified_plus_ambiguous():
    v1 = [(10, 100, 1), (11, 101, 2)]
    meta = [(100, "10"), (200, "99"), (300, "bad")]
    v2 = {(10, 100)}
    report = build_cleanup_report(v1, meta, v2)
    assert report.old_generation_rows == 5
    assert len(report.verified) + len(report.ambiguous) == 5
    assert report.unclassified == 0


def test_manifest_mapping_sha_deterministic_and_order_insensitive():
    r1 = build_cleanup_report([(10, 100, 1), (11, 101, 2)], [(100, "10")], {(10, 100), (11, 101)})
    r2 = build_cleanup_report([(11, 101, 2), (10, 100, 1)], [(100, "10")], {(11, 101), (10, 100)})
    assert r1.manifest_sha256() == r2.manifest_sha256()
    assert r1.mapping_sha256() == r2.mapping_sha256()
    assert r1.source_composite_sha256() == r2.source_composite_sha256()
    # composite 는 verified 구성 변화에 민감(drift 감지).
    r3 = build_cleanup_report([(10, 100, 1)], [], {(10, 100)})
    assert r3.source_composite_sha256() != r1.source_composite_sha256()


# --------------------------------------------------------------------------- #
# 2. 정적 가드 (marker/deploy static guard)
# --------------------------------------------------------------------------- #
def _code_without_docstrings(module) -> str:
    """모듈 소스에서 docstring 을 지운 실행 코드만 반환(정적 불변식 검사용)."""
    tree = ast.parse(inspect.getsource(module))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                body[0].value.value = ""
    return ast.unparse(tree)


def test_static_guard_verify_only_no_drop_no_domain_delete():
    """verify only — 실행 코드에 DROP·domain DELETE·V2 mutation·minting 부재."""
    code = _code_without_docstrings(cleanup)
    low = code.lower()
    assert "drop" not in low                                   # V1 drop 마이그레이션/DDL 0
    assert ".delete(" not in code                              # ORM delete 0
    assert "delete from estimate_order_matches" not in low     # V1 삭제 0
    assert "delete from orders" not in low                     # Order meta 삭제 0
    assert "delete from estimate_order_links_v2" not in low    # V2 삭제 0
    assert "insert into estimate_order_links_v2" not in low    # V2 minting 0
    assert "update estimate_order_links_v2" not in low         # V2 update 0
    assert "EstimateOrderLinkV2(" not in code                  # V2 row 생성 0
    assert "flag_modified" not in code                         # structured_data mutation 0


def test_static_guard_run_enforces_gate_before_run():
    """run_cleanup_verify 는 ensure_run 전에 assert_cleanup_gate 를 강제한다."""
    src = inspect.getsource(cleanup.run_cleanup_verify)
    gate_at = src.index("assert_cleanup_gate(")
    ensure_at = src.index("runs.ensure_run(")
    assert gate_at < ensure_at


def test_static_guard_no_route_or_blueprint():
    code = _code_without_docstrings(cleanup)
    assert "route(" not in code
    assert "blueprint" not in code.lower()
    assert "Blueprint(" not in code


def test_static_guard_separate_phase_and_packet_from_v2():
    """separate run/artifact — phase/packet 이 V2 backfill 과 다르다(재사용 구조적 0)."""
    from foms.services.orders.backfill_estimate_order_links import (
        PACKET_ID as V2_PACKET,
        PHASE_SAME,
        PHASE_SEPARATE,
    )

    assert PHASE not in (PHASE_SAME, PHASE_SEPARATE)
    assert PACKET_ID != V2_PACKET
    assert V2_BACKFILL_PACKET_ID == V2_PACKET


def test_static_guard_no_v1_drop_migration_exists():
    """어떤 마이그레이션도 legacy V1(estimate_order_matches)을 drop 하지 않는다(verify only)."""
    versions = pathlib.Path(__file__).resolve().parents[2] / "migrations" / "versions"
    offenders = []
    for path in versions.glob("*.py"):
        low = path.read_text(encoding="utf-8", errors="ignore").lower()
        if "drop_table('estimate_order_matches'" in low or "drop_table(\"estimate_order_matches\"" in low:
            offenders.append(path.name)
        if "drop table estimate_order_matches" in low:
            offenders.append(path.name)
    assert offenders == []


# --------------------------------------------------------------------------- #
# 3. 암호화 artifact (DPAPI — Windows 전용)
# --------------------------------------------------------------------------- #
def _sample_report():
    return build_cleanup_report([(10, 100, 1), (11, 101, 2)], [(200, "99")], {(10, 100), (11, 101)})


@_WINDOWS_ONLY
def test_artifact_roundtrip_recovers_verified(tmp_path):
    import json

    meta = cleanup.write_cleanup_artifact(tmp_path, _sample_report(), db_instance_id="test-db", now=NOW)
    assert meta["phase"] == PHASE
    enc = json.loads((tmp_path / "verified.csv.enc").read_text(encoding="utf-8"))
    assert enc["alg"] == "AES-256-GCM" and "ciphertext_b64url" in enc

    loaded = cleanup.load_cleanup_artifact(tmp_path, db_instance_id="test-db")
    assert loaded.masked_counts["verified_rows"] == 2
    assert loaded.masked_counts["ambiguous_rows"] == 1
    assert "estimate_id" in loaded.verified_csv_text


@_WINDOWS_ONLY
def test_artifact_not_loadable_as_v2_backfill(tmp_path):
    """separate — cleanup artifact 를 V2 backfill loader 로 소비하면 거부(phase conflation 0)."""
    from foms.services.orders import backfill_estimate_order_links as v2
    from foms.services.security.backfill import crypto

    cleanup.write_cleanup_artifact(tmp_path, _sample_report(), db_instance_id="test-db", now=NOW)
    with pytest.raises((v2.LinkArtifactError, crypto.BackfillCryptoError, KeyError)):
        v2.load_link_artifact(tmp_path, topology=TOPOLOGY_SAME, db_instance_id="test-db")


@_WINDOWS_ONLY
def test_artifact_manifest_tamper_detected(tmp_path):
    cleanup.write_cleanup_artifact(tmp_path, _sample_report(), db_instance_id="test-db", now=NOW)
    m = tmp_path / "manifest.json"
    m.write_bytes(m.read_bytes() + b" ")
    with pytest.raises(cleanup.CleanupArtifactError):
        cleanup.load_cleanup_artifact(tmp_path, db_instance_id="test-db")


@_WINDOWS_ONLY
def test_artifact_ciphertext_tamper_detected(tmp_path):
    import json

    from foms.services.security.backfill import crypto

    cleanup.write_cleanup_artifact(tmp_path, _sample_report(), db_instance_id="test-db", now=NOW)
    enc_path = tmp_path / "verified.csv.enc"
    env = json.loads(enc_path.read_text(encoding="utf-8"))
    env["ciphertext_b64url"] = env["ciphertext_b64url"][:-4] + "AAAA"
    enc_path.write_text(json.dumps(env), encoding="utf-8")
    with pytest.raises(crypto.BackfillCryptoError):
        cleanup.load_cleanup_artifact(tmp_path, db_instance_id="test-db")


# --------------------------------------------------------------------------- #
# 4. PG 통합
# --------------------------------------------------------------------------- #
_MARKER_TRIGGER = "trg_feature_cutover_marker_immutable"


def _wd_tables(pg_engine):
    from wdcalculator_db import WDCalculatorBase

    WDCalculatorBase.metadata.create_all(bind=pg_engine)


def _reset(pg_engine):
    with pg_engine.begin() as conn:
        conn.execute(text("DELETE FROM estimate_order_links_v2"))
        conn.execute(text("DELETE FROM maintenance_backfill_checkpoints"))
        conn.execute(text("DELETE FROM maintenance_backfill_approvals"))
        conn.execute(text("DELETE FROM maintenance_backfill_runs"))
        conn.execute(text("DELETE FROM wdc_link_runtime_state"))
        conn.execute(text(f"ALTER TABLE feature_cutover_markers DISABLE TRIGGER {_MARKER_TRIGGER}"))
        conn.execute(text("DELETE FROM feature_cutover_markers WHERE family = 'WDC_LINK'"))
        conn.execute(text(f"ALTER TABLE feature_cutover_markers ENABLE TRIGGER {_MARKER_TRIGGER}"))
        conn.execute(text("DELETE FROM orders WHERE customer_name = 'WDCLINK_TEST'"))
        for tbl in ("estimate_order_matches", "estimate_histories", "estimates"):
            conn.execute(text(f"DELETE FROM {tbl}"))


@pytest.fixture
def link_db(pg_engine):
    _wd_tables(pg_engine)
    _reset(pg_engine)
    yield pg_engine
    _reset(pg_engine)


_UNAME_SEQ = [0]


def _make_admin(session) -> int:
    from models import User

    _UNAME_SEQ[0] += 1
    u = User(
        username=f"wdcclean_{_UNAME_SEQ[0]}_{uuid.uuid4().hex[:8]}",
        password=generate_password_hash("pw-not-committed"),
        name="승인자", role="ADMIN", team=None, is_active=True,
    )
    session.add(u)
    session.commit()
    return u.id


def _make_estimate(session, customer="고객") -> int:
    from wdcalculator_models import Estimate

    e = Estimate(customer_name=customer, estimate_data={"items": []})
    session.add(e)
    session.flush()
    return e.id


def _add_v1(session, estimate_id, order_id) -> int:
    from wdcalculator_models import EstimateOrderMatch

    m = EstimateOrderMatch(estimate_id=estimate_id, order_id=order_id)
    session.add(m)
    session.flush()
    return m.id


def _make_order(session, order_id, sd):
    from models import Order

    o = Order(
        id=order_id, received_date="2026-07-26", customer_name="WDCLINK_TEST",
        phone="010-0000-0000", address="서울", product="침대", structured_data=sd,
    )
    session.add(o)
    session.commit()


def _seed_marker(session):
    uid = _make_admin(session)
    session.execute(
        text(
            "INSERT INTO feature_cutover_markers (family, cutover_sha, cutover_generation, "
            "minimum_compatibility_generation, readiness_artifact_sha256, ops_approval_id, "
            "approved_by_admin_user_id) VALUES (:f, :sha, 1, 1, :art, :oid, :uid)"
        ),
        {"f": "WDC_LINK", "sha": "0" * 64, "art": "0" * 64, "oid": str(uuid.uuid4()), "uid": uid},
    )
    session.commit()


def _activate(s, run):
    """OPS approval 대체(테스트) — apply lease 가 요구하는 seq≥1 을 활성화."""
    run.current_approval_seq = 1


def _run_v2_backfill(session):
    """V2 backfill(SAME) 를 돌려 canonical V2 를 채우고 DONE run/checkpoint 를 만든다."""
    from foms.services.orders.backfill_estimate_order_links import run_backfill

    return run_backfill(session, topology=TOPOLOGY_SAME, db_instance_id="test-db",
                        owner_identity="tester", now=NOW, activate_approval=_activate)


def _counts(session):
    v1 = session.execute(text("SELECT count(*) FROM estimate_order_matches")).scalar()
    v2 = session.execute(text("SELECT count(*) FROM estimate_order_links_v2")).scalar()
    meta = session.execute(
        text("SELECT count(*) FROM orders WHERE (structured_data #>> '{meta,wdc_estimate_id}') IS NOT NULL "
             "AND customer_name = 'WDCLINK_TEST'")
    ).scalar()
    return v1, v2, meta


def test_pg_gate_refuses_before_marker(link_db):
    """canonical 미effective(marker 전) → cleanup 거부(변화 0)."""
    session = sessionmaker(bind=link_db)()
    try:
        e1 = _make_estimate(session, "고객1")
        _add_v1(session, e1, 100)
        session.commit()
        _run_v2_backfill(session)  # V2 checkpoint 는 있지만 marker 는 아직 없음
        with pytest.raises(WDCLinkCleanupGateError):
            run_cleanup_verify(session, topology=TOPOLOGY_SAME, db_instance_id="test-db",
                               owner_identity="tester", now=NOW, activate_approval=_activate)
        session.rollback()
    finally:
        session.close()


def test_pg_gate_refuses_without_v2_checkpoint(link_db):
    """marker 는 있지만 V2 backfill DONE(checkpoint) 부재 → 거부."""
    session = sessionmaker(bind=link_db)()
    try:
        e1 = _make_estimate(session, "고객1")
        _add_v1(session, e1, 100)
        session.commit()
        _seed_marker(session)  # canonical effective, 그러나 V2 backfill 미실행
        with pytest.raises(WDCLinkCleanupGateError):
            run_cleanup_verify(session, topology=TOPOLOGY_SAME, db_instance_id="test-db",
                               owner_identity="tester", now=NOW, activate_approval=_activate)
        session.rollback()
    finally:
        session.close()


def test_pg_effective_verify_only_immutable(link_db):
    """effective 뒤 → verify only(실 삭제 0·V1/V2/Order 불변)·old generation nonzero·separate run."""
    session = sessionmaker(bind=link_db)()
    try:
        e1 = _make_estimate(session, "고객1")
        _add_v1(session, e1, 100)
        _add_v1(session, e1, 101)
        _make_order(session, 100, {"meta": {"wdc_estimate_id": e1}})
        session.commit()

        v2_report = _run_v2_backfill(session)  # canonical V2 채움 + DONE run
        _seed_marker(session)                  # canonical effective

        before = _counts(session)
        run = run_cleanup_verify(session, topology=TOPOLOGY_SAME, db_instance_id="test-db",
                                 owner_identity="tester", now=NOW, activate_approval=_activate)
        after = _counts(session)

        assert run.state == "DONE"
        assert run.deletions == 0
        assert run.old_generation_rows == 3           # 2 V1 pair + 1 Order meta
        assert run.verified_rows == 3 and run.ambiguous_rows == 0
        assert run.verified_batches == 1
        assert not run.stopped_drift
        # verify only — V1/V2/Order 모두 불변(실 삭제 0).
        assert after == before
        # separate run — V2 backfill run_id 재사용 0.
        assert run.run_id != v2_report.run_id
        assert run.phase == PHASE
        row = session.execute(
            text("SELECT packet_id, phase FROM maintenance_backfill_runs WHERE run_id = :r"),
            {"r": run.run_id},
        ).first()
        assert row == (PACKET_ID, PHASE)
    finally:
        session.close()


def test_pg_ambiguous_held_not_removed(link_db):
    """대응 V2 없는 Order meta 링크·무결성 위반 meta 는 보류(제거 0)·V2 불변."""
    session = sessionmaker(bind=link_db)()
    try:
        e1 = _make_estimate(session, "고객1")
        _add_v1(session, e1, 100)
        _make_order(session, 100, {"meta": {"wdc_estimate_id": e1}})     # verified
        _make_order(session, 200, {"meta": {"wdc_estimate_id": 999999}})  # ghost → ambiguous
        _make_order(session, 300, {"meta": {"wdc_estimate_id": "bad"}})   # invalid → ambiguous
        session.commit()

        _run_v2_backfill(session)
        _seed_marker(session)

        before = _counts(session)
        run = run_cleanup_verify(session, topology=TOPOLOGY_SAME, db_instance_id="test-db",
                                 owner_identity="tester", now=NOW, activate_approval=_activate)
        after = _counts(session)

        assert run.state == "DONE"
        assert run.ambiguous_rows == 2               # ghost + invalid
        assert run.verified_rows == 2                # V1 (e1,100) + Order meta (e1,100)
        assert run.deletions == 0
        assert after == before                       # 보류 대상도 제거 0
        # ambiguous order row 는 그대로(meta 링크 보존).
        meta200 = session.execute(
            text("SELECT structured_data #>> '{meta,wdc_estimate_id}' FROM orders WHERE id=200")
        ).scalar()
        assert meta200 == "999999"
    finally:
        session.close()


def test_pg_audit_read_only_classifies(link_db):
    """audit_wdc_link_cleanup 은 read-only 로 VERIFIED/AMBIGUOUS 를 분류(mutation 0)."""
    session = sessionmaker(bind=link_db)()
    try:
        e1 = _make_estimate(session, "고객1")
        _add_v1(session, e1, 100)
        _make_order(session, 200, {"meta": {"wdc_estimate_id": 42}})
        session.commit()
        _run_v2_backfill(session)

        before = _counts(session)
        report = audit_wdc_link_cleanup(session)
        after = _counts(session)
        assert after == before                       # read-only
        assert any(i.source == SOURCE_V1 and (i.estimate_id, i.order_id) == (e1, 100)
                   for i in report.verified)
        assert any(a.source == SOURCE_ORDER_META and a.order_id == 200 for a in report.ambiguous)
    finally:
        session.close()


def test_pg_old_generation_zero_refused(link_db):
    """old generation 0(은퇴 대상 없음) → run 거부(잘못된 DB/topology 신호)."""
    session = sessionmaker(bind=link_db)()
    try:
        # V1·Order meta 를 만들지 않되, V2 backfill DONE run 은 필요하므로 하나 심고 marker.
        e1 = _make_estimate(session, "고객1")
        _add_v1(session, e1, 100)
        session.commit()
        _run_v2_backfill(session)
        _seed_marker(session)
        # old generation 을 0 으로 만들기 위해 V1 을 제거(Order meta 도 없음).
        session.execute(text("DELETE FROM estimate_order_matches"))
        session.commit()

        with pytest.raises(WDCLinkCleanupError):
            run_cleanup_verify(session, topology=TOPOLOGY_SAME, db_instance_id="test-db",
                               owner_identity="tester", now=NOW, activate_approval=_activate)
        session.rollback()
    finally:
        session.close()
