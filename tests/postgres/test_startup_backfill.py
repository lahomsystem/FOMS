"""STARTUP-BACKFILL-01 — ERP flat 컬럼 audit/backfill 계약 테스트.

세 층을 검증한다:

* **순수 도메인**(PG 불필요): CLEAN/SAFE/AMBIGUOUS 분류(payment drift·malformed→ambiguous,
  비-ERP/structured_data None→대상 제외), bare ``--apply`` 거부 게이트, startup fallback 부재.
* **암호화 artifact**(Windows DPAPI 전용, 비-Windows skip): AES-256-GCM + DPAPI envelope
  round-trip, plaintext CSV 0, db_instance/변조 바인딩 거부.
* **PG 통합**(``FOMS_TEST_DATABASE_URL`` 필요, 미설정이면 lane skip): coverage·SAFE 만
  재동기·before/after verify·operation-bound approval 소비·batch·DB checkpoint resume.

DSN·PG 비밀번호는 env 로만 주입한다(커밋 파일에 비번 0).
"""
from __future__ import annotations

import base64
import datetime
import inspect
import json
import os
import uuid

import pytest
from sqlalchemy.orm import sessionmaker
from werkzeug.security import generate_password_hash

from foms.services.datetime_kst import now_utc_naive
from foms.services.erp_sync_columns import sync_erp_flat_columns
from foms.services.orders import erp_flat_audit as fa
from foms.services.orders import erp_flat_backfill as fb
from foms.services.orders.erp_flat_audit import AMBIGUOUS, CLEAN, SAFE, audit_orders, classify_order
from foms.services.orders.erp_flat_artifact import (
    ArtifactError,
    load_audit_artifact,
    write_audit_artifact,
)
from foms.services.orders.erp_flat_backfill import (
    ApplyAuthorizationError,
    count_flat_drift,
    resolve_apply_mode,
    run_backfill,
)

_WINDOWS = os.name == "nt"
_dpapi_only = pytest.mark.skipif(not _WINDOWS, reason="DPAPI is Windows-only (other OS fail-closed)")
NOW = datetime.datetime(2026, 7, 25, 12, 0, 0)


# --------------------------------------------------------------------------- #
# fake order (순수 분류용)
# --------------------------------------------------------------------------- #
class _Order:
    def __init__(self, order_id, *, is_erp_order=True, structured_data=None, phone=None, **flat):
        self.id = order_id
        self.is_erp_order = is_erp_order
        self.structured_data = structured_data
        self.phone = phone
        for column in fa.DERIVED_COLUMNS:
            setattr(self, column, flat.get(column))


# --------------------------------------------------------------------------- #
# 1. 분류 (순수)
# --------------------------------------------------------------------------- #
def test_non_erp_order_excluded():
    assert classify_order(_Order(1, is_erp_order=False, structured_data={"workflow": {"stage": "MEASURE"}})) is None


def test_none_structured_data_excluded():
    assert classify_order(_Order(1, structured_data=None)) is None


def test_malformed_structured_data_is_ambiguous():
    result = classify_order(_Order(1, structured_data=["not", "a", "dict"]))
    assert result.classification == AMBIGUOUS
    assert result.reason == fa.MALFORMED


def test_no_drift_is_clean():
    sd = {"workflow": {"stage": "CONFIRM"}, "parties": {"manager": {"name": "김담당"}}}
    order = _Order(1, structured_data=sd, phone="01011112222")
    for column, value in fa._expected_flat_values(order, sd).items():
        setattr(order, column, value)  # 파생 값으로 미리 맞춘다 → drift 0
    assert classify_order(order).classification == CLEAN


def test_nonfinancial_drift_is_safe():
    sd = {"workflow": {"stage": "MEASURE"}, "parties": {"manager": {"name": "이담당"}}}
    order = _Order(1, structured_data=sd, phone="01000000000", erp_stage_code=None)
    result = classify_order(order)
    assert result.classification == SAFE
    assert "erp_stage_code" in result.drift_columns
    assert "payment_amount" not in result.drift_columns


def test_payment_amount_drift_is_ambiguous():
    sd = {"workflow": {"stage": "MEASURE"}, "payment": {"deposit": 50000}}
    order = _Order(1, structured_data=sd, phone="01000000000", payment_amount=0)
    result = classify_order(order)
    assert result.classification == AMBIGUOUS
    assert result.reason == fa.PAYMENT_DRIFT
    assert "payment_amount" in result.drift_columns


def test_classification_always_in_closed_set():
    for sd in ({}, {"workflow": {"stage": "MEASURE"}}, {"payment": {"deposit": 1}}):
        result = classify_order(_Order(1, structured_data=sd, phone="01000000000"))
        assert result is None or result.classification in fa.CLASSIFICATIONS


# --------------------------------------------------------------------------- #
# 2. bare --apply 거부 게이트 (순수)
# --------------------------------------------------------------------------- #
def test_default_is_dry_run():
    assert resolve_apply_mode(apply=False, dry_run=False, approval_token_file=None) is False
    assert resolve_apply_mode(apply=False, dry_run=True, approval_token_file=None) is False


def test_bare_apply_refused_without_token():
    with pytest.raises(ApplyAuthorizationError):
        resolve_apply_mode(apply=True, dry_run=False, approval_token_file=None)


def test_apply_with_token_and_not_dry_run_ok():
    assert resolve_apply_mode(apply=True, dry_run=False, approval_token_file="tok.json") is True


def test_apply_and_dry_run_mutually_exclusive():
    with pytest.raises(ApplyAuthorizationError):
        resolve_apply_mode(apply=True, dry_run=True, approval_token_file="tok.json")


# --------------------------------------------------------------------------- #
# 3. startup fallback 부재 (순수) — 새 pipeline 은 app startup 이 트리거하지 않는다
# --------------------------------------------------------------------------- #
def test_new_pipeline_not_wired_into_app_startup():
    from foms.services import app_init

    src = inspect.getsource(app_init)
    # 새 operator pipeline 모듈(erp_flat_*)이 app startup 에서 참조되지 않음을 증명한다.
    # (legacy ``_backfill_erp_flat_columns`` bounded startup resync 는 별개 메커니즘 —
    #  P1-17 분할상 STARTUP-PURE-01 소관이며 이 packet 이 제거하지 않는다.)
    for token in ("erp_flat_backfill", "erp_flat_artifact", "erp_flat_audit"):
        assert token not in src, f"app_init must not auto-trigger the new pipeline ({token})."


# --------------------------------------------------------------------------- #
# 4. 암호화 artifact (Windows DPAPI 전용)
# --------------------------------------------------------------------------- #
def _sample_report():
    report = fa.AuditReport(total=2, counts={CLEAN: 0, SAFE: 1, AMBIGUOUS: 1})
    report.safe_audits = [fa.FlatColumnAudit(101, SAFE, ("erp_stage_code",), None, "a" * 64)]
    report.ambiguous_audits = [
        fa.FlatColumnAudit(202, AMBIGUOUS, ("payment_amount",), fa.PAYMENT_DRIFT, "b" * 64)
    ]
    return report


@_dpapi_only
def test_artifact_roundtrip_and_no_plaintext(tmp_path):
    report = _sample_report()
    result = write_audit_artifact(tmp_path, report, db_instance_id="test-db")

    for name in ("key-envelope.json", "safe.csv.enc", "ambiguous.csv.enc",
                 "manifest.json", "sha.txt", "approval-scope.json", "summary.json"):
        assert (tmp_path / name).is_file()
    # plaintext CSV 는 디스크에 없다.
    assert not list(tmp_path.glob("*.csv"))
    # safe.csv.enc 는 암호화 envelope — CSV 원문 문자열이 평문으로 존재하지 않는다.
    enc = (tmp_path / "safe.csv.enc").read_bytes()
    assert b"order_id" not in enc and b"RESYNC_FLAT" not in enc
    env = json.loads(enc)
    assert env["alg"] == "AES-256-GCM" and "ciphertext_b64url" in env
    # summary/approval-scope 는 PII 없이 카운트만.
    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert summary["masked_counts"] == {"total": 2, "safe": 1, "ambiguous": 1, "clean": 0}

    loaded = load_audit_artifact(tmp_path, db_instance_id="test-db")
    assert loaded.safe_targets == [(101, "a" * 64)]
    assert loaded.manifest_sha256 == result["manifest_sha256"]
    assert loaded.mapping_sha256 == result["mapping_sha256"]
    assert loaded.approval_scope["operation_id"] == "BACKFILL_APPLY"


@_dpapi_only
def test_artifact_wrong_db_instance_fails_closed(tmp_path):
    write_audit_artifact(tmp_path, _sample_report(), db_instance_id="test-db")
    from foms.services.security.backfill import crypto

    with pytest.raises(crypto.BackfillCryptoError):
        load_audit_artifact(tmp_path, db_instance_id="OTHER-DB")


@_dpapi_only
def test_artifact_tampered_manifest_rejected(tmp_path):
    write_audit_artifact(tmp_path, _sample_report(), db_instance_id="test-db")
    (tmp_path / "sha.txt").write_text("deadbeef\n", encoding="utf-8")
    with pytest.raises(ArtifactError):
        load_audit_artifact(tmp_path, db_instance_id="test-db")


# --------------------------------------------------------------------------- #
# PG 통합 helpers
# --------------------------------------------------------------------------- #
def _session(pg_engine):
    return sessionmaker(bind=pg_engine)()


_SEQ = [0]


def _erp_order(sd, *, phone="01000000000", **flat):
    from models import Order

    order = Order(
        received_date="2026-07-25",
        customer_name="테스트",
        phone=phone,
        address="서울",
        product="가구",
        is_erp_order=True,
        structured_data=sd,
    )
    for column, value in flat.items():
        setattr(order, column, value)
    return order


def _make_admin(session):
    _SEQ[0] += 1
    from models import User

    user = User(
        username=f"sbf_admin_{_SEQ[0]}_{uuid.uuid4().hex[:6]}",
        password=generate_password_hash("pw-not-committed"),
        name="승인자",
        role="ADMIN",
        is_active=True,
    )
    session.add(user)
    session.commit()
    return user


def _principal_version(session, user_id):
    from models import SecurityPrincipalVersion

    return (
        session.query(SecurityPrincipalVersion)
        .filter(SecurityPrincipalVersion.user_id == user_id)
        .one()
        .version
    )


def _seed_backfill_apply(session, admin, audit, db_instance_id):
    """audit 로부터 BACKFILL_APPLY OPS approval(APPROVED) + raw secret 을 만든다."""
    from foms.services.security import ops_control_root as root_store
    from foms.services.security.ops_approval import compute_scope_sha256, nonce_hash_from_secret
    from foms.services.security.backfill import manifest as bmanifest
    from foms.services.security.backfill import runs
    from models import OpsApprovalRequest

    scope = bmanifest.build_approval_scope(
        packet_id=fa.PACKET_ID,
        phase=fa.PHASE,
        manifest_sha256=audit.manifest_sha256(),
        mapping_sha256=audit.mapping_sha256(),
        db_instance_id=db_instance_id,
        source_composite_sha256=audit.source_composite_sha256(),
        expected_run_row_version=1,
        masked_counts=audit.masked_counts(),
    )
    ops_scope = runs.ops_scope_for_backfill(scope, "BACKFILL_APPLY")
    _b64, raw = root_store.new_one_time_secret()
    now = now_utc_naive()
    row = OpsApprovalRequest(
        id=str(uuid.uuid4()),
        operation_type="BACKFILL_APPLY",
        scope_sha256=compute_scope_sha256(ops_scope),
        artifact_sha256=ops_scope["artifact_sha256"],
        expected_version=ops_scope["expected_version"],
        expected_generation=None,
        nonce_hash=nonce_hash_from_secret(raw),
        expires_at=now + datetime.timedelta(seconds=600),
        state="APPROVED",
        approved_by_user_id=admin.id,
        approved_principal_version=_principal_version(session, admin.id),
        approved_at=now,
        operator_identity_hash="0" * 64,
        created_at=now,
    )
    session.add(row)
    session.commit()
    return scope, row, raw


def _activate(scope, approval_id, raw, admin_pv):
    from foms.services.security.backfill import runs

    def _hook(session, run):
        runs.consume_backfill_apply(
            session,
            run.run_id,
            approval_scope=scope,
            approval_id=approval_id,
            admin_principal_version=admin_pv,
            raw_secret=raw,
        )

    return _hook


def _reset_tables(engine):
    """orders/ops 만 정리한다. maintenance_backfill_* 는 append-only(approvals) + FK 로
    삭제 불가이나, run identity 가 주문 내용마다 고유해 test 간 충돌하지 않는다."""
    from sqlalchemy import text

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM order_schedule_dates"))
        conn.execute(text("DELETE FROM orders"))


@pytest.fixture
def clean_db(pg_engine):
    _reset_tables(pg_engine)
    yield pg_engine
    _reset_tables(pg_engine)


# --------------------------------------------------------------------------- #
# 5. PG: coverage + SAFE 재동기 + before/after verify + approval 소비
# --------------------------------------------------------------------------- #
def test_pg_audit_and_backfill(clean_db):
    engine = clean_db
    session = _session(engine)
    try:
        clean = _erp_order({"workflow": {"stage": "CONFIRM"}, "parties": {"manager": {"name": "김담당"}}})
        sync_erp_flat_columns(clean, clean.structured_data)  # 미리 동기 → CLEAN
        safe1 = _erp_order({"workflow": {"stage": "MEASURE"}, "parties": {"manager": {"name": "이담당"}}})
        safe2 = _erp_order({"workflow": {"stage": "DRAWING"}})
        ambiguous = _erp_order({"workflow": {"stage": "MEASURE"}, "payment": {"deposit": 50000}}, payment_amount=0)
        non_erp = _erp_order({"workflow": {"stage": "MEASURE"}})
        non_erp.is_erp_order = False
        for order in (clean, safe1, safe2, ambiguous, non_erp):
            session.add(order)
        session.commit()
        ids = {"clean": clean.id, "safe1": safe1.id, "safe2": safe2.id, "ambiguous": ambiguous.id}

        audit = audit_orders(session)
        assert audit.total == 4  # non-ERP 는 대상 제외
        assert audit.counts[CLEAN] == 1
        assert audit.counts[SAFE] == 2
        assert audit.counts[AMBIGUOUS] == 1

        safe_ids = [oid for oid, _ in audit.safe_targets()]
        assert count_flat_drift(session, safe_ids) == 2  # before verify

        admin = _make_admin(session)
        scope, row, raw = _seed_backfill_apply(session, admin, audit, "test-db")
        report = run_backfill(
            session,
            db_instance_id="test-db",
            owner_identity="tester",
            safe_targets=audit.safe_targets(),
            manifest_sha256=audit.manifest_sha256(),
            mapping_sha256=audit.mapping_sha256(),
            batch_size=500,
            now=NOW,
            activate_approval=_activate(scope, row.id, raw, _principal_version(session, admin.id)),
        )
        assert report.state == "DONE"
        assert report.completed_rows == 2
        assert report.resynced_orders == 2

        # approval 이 one-time 소비됐다.
        session.refresh(row)
        assert row.state == "CONSUMED"

        session.expire_all()
        after = audit_orders(session)
        assert after.counts[SAFE] == 0
        assert after.counts[CLEAN] == 3  # clean + 재동기 2
        assert after.counts[AMBIGUOUS] == 1
        assert count_flat_drift(session, safe_ids) == 0  # after verify

        # ambiguous 는 손대지 않는다(payment_amount 여전히 0).
        from models import Order

        amb = session.get(Order, ids["ambiguous"])
        assert amb.payment_amount == 0
    finally:
        session.close()


def test_pg_backfill_requires_active_approval(clean_db):
    """approval 활성화 훅이 없으면(seq<1) acquire_lease 가 거부 → apply 0."""
    engine = clean_db
    session = _session(engine)
    try:
        safe = _erp_order({"workflow": {"stage": "MEASURE"}})
        session.add(safe)
        session.commit()
        audit = audit_orders(session)
        with pytest.raises(Exception):
            run_backfill(
                session,
                db_instance_id="test-db",
                owner_identity="tester",
                safe_targets=audit.safe_targets(),
                manifest_sha256=audit.manifest_sha256(),
                mapping_sha256=audit.mapping_sha256(),
                now=NOW,
                activate_approval=None,  # approval 미활성 → seq<1
            )
        session.rollback()
        assert count_flat_drift(session, [safe.id]) == 1  # 재동기 안 됨
    finally:
        session.close()


# --------------------------------------------------------------------------- #
# 6. PG: DB checkpoint resume — 중단 후 이어감
# --------------------------------------------------------------------------- #
def test_pg_checkpoint_resume(clean_db, monkeypatch):
    engine = clean_db
    setup = _session(engine)
    try:
        safe_a = _erp_order({"workflow": {"stage": "MEASURE"}})
        safe_b = _erp_order({"workflow": {"stage": "DRAWING"}})
        setup.add(safe_a)
        setup.add(safe_b)
        setup.commit()
        ids = sorted([safe_a.id, safe_b.id])
        second_id = ids[1]  # order_id 오름차순 2번째(중단 대상)

        audit = audit_orders(setup)
        assert audit.counts[SAFE] == 2
        admin = _make_admin(setup)
        scope, row, raw = _seed_backfill_apply(setup, admin, audit, "test-db")
        admin_pv = _principal_version(setup, admin.id)
        approval_id = row.id  # session close 전에 값으로 포획(detach 방지)
        targets = audit.safe_targets()
        m_sha, p_sha = audit.manifest_sha256(), audit.mapping_sha256()
    finally:
        setup.close()

    # --- 1차: batch_size=1, 2번째 주문 재동기에서 강제 중단 ---
    real_sync = fb.sync_erp_flat_columns
    fail = {"on": True}

    def _flaky(order, structured_data):
        if fail["on"] and order.id == second_id:
            raise RuntimeError("simulated interruption")
        return real_sync(order, structured_data)

    monkeypatch.setattr(fb, "sync_erp_flat_columns", _flaky)

    s1 = _session(engine)
    try:
        with pytest.raises(RuntimeError):
            run_backfill(
                s1, db_instance_id="test-db", owner_identity="tester",
                safe_targets=targets, manifest_sha256=m_sha, mapping_sha256=p_sha,
                batch_size=1, now=NOW,
                activate_approval=_activate(scope, approval_id, raw, admin_pv),
            )
        s1.rollback()
    finally:
        s1.close()

    # 1차에서 첫 batch(1건)만 완료됐다.
    probe = _session(engine)
    try:
        from foms.services.security.backfill import runs
        from models import MaintenanceBackfillRun

        run_id = runs.compute_run_id(fa.PACKET_ID, fa.PHASE, m_sha, p_sha)
        run = probe.query(MaintenanceBackfillRun).filter_by(run_id=run_id).one()
        assert run.completed_rows == 1 and run.state == "RUNNING"
        assert probe.query(MaintenanceBackfillRun).filter_by(run_id=run_id).one().current_approval_seq == 1
    finally:
        probe.close()

    # --- 2차: 중단 해제 + lease 만료(>60s) 후 resume → 남은 1건 완료 ---
    fail["on"] = False
    s2 = _session(engine)
    try:
        report = run_backfill(
            s2, db_instance_id="test-db", owner_identity="tester2",
            safe_targets=targets, manifest_sha256=m_sha, mapping_sha256=p_sha,
            batch_size=1, now=NOW + datetime.timedelta(seconds=120),
            activate_approval=_activate(scope, approval_id, raw, admin_pv),  # seq≥1 → 호출 안 됨
        )
        assert report.state == "DONE"
        assert report.completed_rows == 2
        assert count_flat_drift(s2, ids) == 0  # 전부 재동기됨
    finally:
        s2.close()
