"""OFFLINE-01 도메인 계약: 승인 기반 offline local recovery apply.

브라우저/기기에 큐잉된 미전송 order 변경(offline local queue)을, OPS-APPROVAL 승인 하에서,
그리고 inventory hash·schema·order-ID hash 검증이 전부 통과한 뒤에만, all-or-none 으로
적용한다. dry-run 이 기본이고 승인 없이는 적용 0, offline 자동 재생은 없다(명시 apply 만).

OPS-APPROVAL consume 경로는 순수 ORM(``FOR UPDATE`` 는 SQLite 에서 무해한 no-op)이라
domains(SQLite) 레인에서 그대로 검증된다. PG lane(``FOMS_TEST_DATABASE_URL``)에서도 동일히
green 이다. 비밀번호/토큰은 커밋 파일에 남기지 않는다(런타임 생성).

SQLite 는 User insert 시 principal-version trigger 가 없으므로(운영 PG 는 trigger 가 seed)
:func:`_admin` 이 ``security_principal_versions`` row 를 수동 seed 한다.
"""
from __future__ import annotations

import copy
import datetime
import uuid

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.datetime_kst import now_utc_naive
from models import Order, OpsApprovalRequest, SecurityPrincipalVersion, User
from foms.services.security import ops_control_root as root_store
from foms.services.security.ops_approval import (
    ApprovalConsumeError,
    compute_scope_sha256,
    nonce_hash_from_secret,
)
from foms.services.orders.offline_recovery import (
    OPERATION_ID,
    OfflineRecoveryDriftError,
    OfflineRecoverySchemaError,
    _ops_scope,
    apply_offline_recovery,
    build_recovery_plan,
)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
_SEQ = [0]


def _admin(*, role="ADMIN", active=True) -> User:
    """admin User + principal version 1 seed(SQLite 는 trigger 부재라 수동)."""
    _SEQ[0] += 1
    u = User(
        username=f"ofr_admin_{_SEQ[0]}",
        password=generate_password_hash("pw-not-committed"),
        name="승인자",
        role=role,
        team=None,
        is_active=active,
    )
    db_session.add(u)
    db_session.flush()
    db_session.add(SecurityPrincipalVersion(user_id=u.id, version=1))
    db_session.commit()
    return u


def _pv(user_id: int) -> int:
    return (
        db_session.query(SecurityPrincipalVersion)
        .filter(SecurityPrincipalVersion.user_id == user_id)
        .one()
    ).version


def _order(*, structured_data=None, customer="홍길동") -> int:
    o = Order(
        received_date="2026-01-01",
        customer_name=customer,
        phone="010-1234-5678",
        address="서울시",
        product="붙박이장",
        status="RECEIVED",
        structured_data=structured_data,
    )
    db_session.add(o)
    db_session.commit()
    return int(o.id)


def _approve(approver, plan, *, now=None, state="APPROVED", expires=600):
    """plan 에 바인딩된 OPS-APPROVAL row(+raw secret). artifact_sha256=inventory_sha256."""
    now = now or now_utc_naive()
    scope = _ops_scope(plan)
    _b64, raw = root_store.new_one_time_secret()
    approved = state in ("APPROVED", "RESERVED")
    row = OpsApprovalRequest(
        id=str(uuid.uuid4()),
        operation_type=OPERATION_ID,
        scope_sha256=compute_scope_sha256(scope),
        artifact_sha256=plan["inventory_sha256"],
        expected_version=plan["entry_count"],
        expected_generation=None,
        nonce_hash=nonce_hash_from_secret(raw),
        expires_at=now + datetime.timedelta(seconds=expires),
        state=state,
        approved_by_user_id=approver.id if approved else None,
        approved_principal_version=_pv(approver.id) if approved else None,
        approved_at=now if approved else None,
        operator_identity_hash="0" * 64,
        created_at=now,
    )
    db_session.add(row)
    db_session.commit()
    return row, raw


def _sd(order_id: int):
    o = db_session.get(Order, order_id)
    db_session.refresh(o)
    return o.structured_data


def _state(approval_id: str) -> str:
    return db_session.get(OpsApprovalRequest, approval_id).state


def _entry(order_id: int, patch: dict):
    return {"order_id": order_id, "op": "structured_data_merge", "patch": patch}


# --------------------------------------------------------------------------- #
# 0. plan 조립 + schema 검증(순수 로직, DB 불필요)
# --------------------------------------------------------------------------- #
def test_build_plan_computes_hashes_and_is_deterministic():
    entries = [_entry(2, {"b": 2}), _entry(1, {"a": 1})]
    plan = build_recovery_plan(entries)
    assert plan["entry_count"] == 2
    assert plan["order_ids"] == [1, 2]                 # 정렬·중복 제거
    assert len(plan["inventory_sha256"]) == 64
    assert len(plan["order_ids_sha256"]) == 64
    # 결정성: 같은 entries → 같은 무결성 해시.
    assert build_recovery_plan(entries)["inventory_sha256"] == plan["inventory_sha256"]


def test_build_plan_rejects_unknown_op_and_malformed_entry():
    with pytest.raises(OfflineRecoverySchemaError):
        build_recovery_plan([{"order_id": 1, "op": "delete_all", "patch": {}}])  # 미지 op
    with pytest.raises(OfflineRecoverySchemaError):
        build_recovery_plan([{"order_id": 1, "op": "structured_data_merge"}])     # patch 결손
    with pytest.raises(OfflineRecoverySchemaError):
        build_recovery_plan([_entry(1, {}), {"order_id": 2, "op": "structured_data_merge",
                                             "patch": {}, "extra": 1}])            # 여분 필드
    with pytest.raises(OfflineRecoverySchemaError):
        build_recovery_plan([{"order_id": True, "op": "structured_data_merge", "patch": {}}])  # bool id


# --------------------------------------------------------------------------- #
# 1. dry-run 기본: 승인 미소비·적용 0 (= 자동 재생 없음, 명시 apply 만)
# --------------------------------------------------------------------------- #
def test_dry_run_default_consumes_nothing_and_applies_nothing(app):
    admin = _admin()
    oid = _order(structured_data={"a": 1})
    plan = build_recovery_plan([_entry(oid, {"b": 2})])
    row, raw = _approve(admin, plan)

    res = apply_offline_recovery(db_session, approved_plan=plan, raw_secret=raw, apply=False)
    db_session.commit()

    assert res.applied is False and res.consumed is False and res.applied_count == 0
    assert _sd(oid) == {"a": 1}          # 미적용
    assert _state(row.id) == "APPROVED"  # 토큰 미소비


# --------------------------------------------------------------------------- #
# 2. apply: 승인 소비 후 모든 entry 적용(structured_data 상위 병합)
# --------------------------------------------------------------------------- #
def test_apply_consumes_token_and_applies_all_entries(app):
    admin = _admin()
    o1 = _order(structured_data={"a": 1})
    o2 = _order(structured_data=None)
    plan = build_recovery_plan([_entry(o1, {"b": 2}), _entry(o2, {"x": 9})])
    row, raw = _approve(admin, plan)

    res = apply_offline_recovery(db_session, approved_plan=plan, raw_secret=raw, apply=True)
    db_session.commit()

    assert res.applied and res.consumed and res.applied_count == 2
    assert _sd(o1) == {"a": 1, "b": 2}   # 상위 병합(기존 키 보존)
    assert _sd(o2) == {"x": 9}
    assert _state(row.id) == "CONSUMED"
    assert db_session.get(OpsApprovalRequest, row.id).result_sha256 == res.result_sha256


# --------------------------------------------------------------------------- #
# 3. 승인 없이 적용 0 (PENDING 토큰은 소비 불가)
# --------------------------------------------------------------------------- #
def test_unapproved_pending_token_cannot_apply(app):
    admin = _admin()
    oid = _order(structured_data={"a": 1})
    plan = build_recovery_plan([_entry(oid, {"b": 2})])
    _row, raw = _approve(admin, plan, state="PENDING")

    with pytest.raises(ApprovalConsumeError):
        apply_offline_recovery(db_session, approved_plan=plan, raw_secret=raw, apply=True)
    db_session.rollback()

    assert _sd(oid) == {"a": 1}          # 적용 0


# --------------------------------------------------------------------------- #
# 4. one-time: 소비된 토큰 재사용 거부
# --------------------------------------------------------------------------- #
def test_token_is_one_time(app):
    admin = _admin()
    oid = _order(structured_data={})
    plan = build_recovery_plan([_entry(oid, {"b": 2})])
    _row, raw = _approve(admin, plan)

    apply_offline_recovery(db_session, approved_plan=plan, raw_secret=raw, apply=True)
    db_session.commit()                  # CONSUMED

    with pytest.raises(ApprovalConsumeError):
        apply_offline_recovery(db_session, approved_plan=plan, raw_secret=raw, apply=True)
    db_session.rollback()


# --------------------------------------------------------------------------- #
# 5. inventory hash 검증: 승인 후 plan hand-edit(자기모순) → 중단·적용 0
# --------------------------------------------------------------------------- #
def test_inventory_hash_mismatch_aborts(app):
    admin = _admin()
    oid = _order(structured_data={"a": 1})
    plan = build_recovery_plan([_entry(oid, {"b": 2})])
    _row, raw = _approve(admin, plan)

    tampered = copy.deepcopy(plan)
    tampered["entries"][0]["patch"] = {"b": 999}   # entries 변조, inventory_sha256 은 그대로
    with pytest.raises(OfflineRecoveryDriftError):
        apply_offline_recovery(db_session, approved_plan=tampered, raw_secret=raw, apply=True)
    db_session.rollback()

    assert _sd(oid) == {"a": 1}
    assert _state(_row.id) == "APPROVED"           # 토큰 미소비


# --------------------------------------------------------------------------- #
# 6. 내부 정합하지만 미승인 큐 → consume 이 artifact 불일치로 거부(승인된 큐만 적용)
# --------------------------------------------------------------------------- #
def test_consistent_but_unapproved_queue_rejected(app):
    admin = _admin()
    oid = _order(structured_data={"a": 1})
    plan = build_recovery_plan([_entry(oid, {"b": 2})])
    _row, raw = _approve(admin, plan)              # 토큰은 이 plan 의 inventory 에 바인딩.

    other = build_recovery_plan([_entry(oid, {"b": 999})])
    assert other["inventory_sha256"] != plan["inventory_sha256"]
    with pytest.raises(ApprovalConsumeError):
        apply_offline_recovery(db_session, approved_plan=other, raw_secret=raw, apply=True)
    db_session.rollback()

    assert _sd(oid) == {"a": 1}


# --------------------------------------------------------------------------- #
# 7. order-ID hash 검증: 대상 집합 해시 변조 → 중단·적용 0
# --------------------------------------------------------------------------- #
def test_order_id_hash_mismatch_aborts(app):
    admin = _admin()
    oid = _order(structured_data={"a": 1})
    plan = build_recovery_plan([_entry(oid, {"b": 2})])
    _row, raw = _approve(admin, plan)

    tampered = copy.deepcopy(plan)
    tampered["order_ids_sha256"] = "0" * 64
    with pytest.raises(OfflineRecoveryDriftError):
        apply_offline_recovery(db_session, approved_plan=tampered, raw_secret=raw, apply=True)
    db_session.rollback()

    assert _sd(oid) == {"a": 1}


# --------------------------------------------------------------------------- #
# 8. schema 버전 불일치 → 중단·적용 0
# --------------------------------------------------------------------------- #
def test_schema_version_mismatch_aborts(app):
    admin = _admin()
    oid = _order(structured_data={"a": 1})
    plan = build_recovery_plan([_entry(oid, {"b": 2})])
    _row, raw = _approve(admin, plan)

    tampered = copy.deepcopy(plan)
    tampered["schema_version"] = 99
    with pytest.raises(OfflineRecoverySchemaError):
        apply_offline_recovery(db_session, approved_plan=tampered, raw_secret=raw, apply=True)
    db_session.rollback()

    assert _sd(oid) == {"a": 1}


# --------------------------------------------------------------------------- #
# 9. all-or-none: 대상 하나라도 부재면 전체 중단(부분 적용 0)
# --------------------------------------------------------------------------- #
def test_all_or_none_missing_target_aborts(app):
    admin = _admin()
    o1 = _order(structured_data={"a": 1})
    missing = o1 + 999_999                          # 존재하지 않는 order id
    plan = build_recovery_plan([_entry(o1, {"b": 2}), _entry(missing, {"c": 3})])
    row, raw = _approve(admin, plan)

    with pytest.raises(OfflineRecoveryDriftError):
        apply_offline_recovery(db_session, approved_plan=plan, raw_secret=raw, apply=True)
    db_session.rollback()

    assert _sd(o1) == {"a": 1}                       # 부분 적용 0(o1 도 미적용)
    assert _state(row.id) == "APPROVED"              # 토큰 미소비 → resume 가능


# --------------------------------------------------------------------------- #
# 10. 자동 재생 없음: 공개 API 는 명시 plan 조립 + 명시 apply 뿐(백그라운드/at-import 실행 0)
# --------------------------------------------------------------------------- #
def test_no_auto_replay_entrypoint():
    import foms.services.orders.offline_recovery as ofr

    assert set(ofr.__all__) >= {"build_recovery_plan", "apply_offline_recovery"}
    # 스케줄러/CLI/at-import 자동 실행 진입점이 없다(명시 승인 apply 만).
    assert not hasattr(ofr, "main")
    assert not hasattr(ofr, "run")
