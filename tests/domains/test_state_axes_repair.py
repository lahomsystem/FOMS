"""다축 상태 축 safe repair — dry-run/apply/verify + manual CSV 게이트 (STATE-AXES-REPAIR-00).

repair 는 audit safe bucket 만 적용하고 overlay ambiguity 는 자동 교정하지 않는다(§7.2).
순수 데이터 정합화라 DB 없이 SimpleNamespace order 로 계약을 고정한다(state_axes_audit 계약 위에 얹음).
"""
from __future__ import annotations

import copy
from types import SimpleNamespace
from typing import Any, Dict

import pytest

from foms.services.orders.state_axes_audit import audit_order_state_axes, to_manual_csv
from foms.services.orders.repair_order_state_axes import (
    MANUAL_CSV_HEADER,
    ManualCsvError,
    apply_safe_repair,
    verify_coverage,
    verify_manual_csv,
)


def _order(**kwargs: Any) -> SimpleNamespace:
    """Order-like fake. audit/repair 가 읽고 쓰는 속성을 모두 채운다."""
    base: Dict[str, Any] = {
        "id": kwargs.pop("id", 1),
        "status": None,
        "deleted_at": None,
        "erp_stage_code": None,
        "is_erp_order": False,
        "structured_data": None,
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


# audit 계약(test_state_axes_model.py)에서 검증된 bucket 모양을 그대로 재사용한다.
def _mirror_safe() -> SimpleNamespace:
    """mirror mismatch, workflow.stage 유효 main → safe (erp_stage_code RECEIVED→MEASURE)."""
    return _order(id=1, status="MEASURE", is_erp_order=True,
                  structured_data={"workflow": {"stage": "MEASURE"}}, erp_stage_code="RECEIVED")


def _projection_safe() -> SimpleNamespace:
    """projection mismatch, 단일 축 → recomputable safe (status ON_HOLD→PRODUCTION)."""
    return _order(id=2, status="ON_HOLD", is_erp_order=True,
                  structured_data={"workflow": {"stage": "PRODUCTION", "hold": {"active": False}}},
                  erp_stage_code="PRODUCTION")


def _ambiguous_unmapped() -> SimpleNamespace:
    """overlay ambiguity UNMAPPED — 절대 자동 교정 금지."""
    return _order(id=10, status="WEIRD_STATUS", is_erp_order=True)


def _mirror_manual() -> SimpleNamespace:
    """mirror mismatch, workflow.stage 비-main → safe_target None (manual, 자동 교정 금지)."""
    return _order(id=20, status="RECEIVED", is_erp_order=True,
                  structured_data={"workflow": {"stage": "BOGUS_STAGE"}}, erp_stage_code="RECEIVED")


def _clean() -> SimpleNamespace:
    return _order(id=3, status="RECEIVED", is_erp_order=True,
                  structured_data={"workflow": {"stage": "RECEIVED"}}, erp_stage_code="RECEIVED")


# --- 1. dry-run: 미적용, safe 제안 카운트만 ------------------------------------
def test_dry_run_writes_nothing() -> None:
    orders = [_mirror_safe(), _projection_safe(), _ambiguous_unmapped(), _clean()]
    before = [(o.status, o.erp_stage_code) for o in orders]
    result = apply_safe_repair(orders, dry_run=True)
    assert result.dry_run is True
    assert result.safe_count == 2  # mirror + projection
    assert len(result.mirror_repaired) == 1
    assert len(result.projection_repaired) == 1
    assert result.ambiguous_skipped == 1
    # 아무 것도 쓰지 않았다
    assert [(o.status, o.erp_stage_code) for o in orders] == before


# --- 2. apply: safe bucket만 교정, ambiguous 불변(enforcement 0) -----------------
def test_apply_repairs_only_safe_bucket() -> None:
    mirror, projection, ambiguous, clean = (
        _mirror_safe(), _projection_safe(), _ambiguous_unmapped(), _clean())
    orders = [mirror, projection, ambiguous, clean]
    result = apply_safe_repair(orders, dry_run=False)
    assert result.dry_run is False
    # mirror: erp_stage_code 가 canonical workflow.stage 원값으로 재동기
    assert mirror.erp_stage_code == "MEASURE"
    # projection: order.status 가 canonical projection 으로 재계산
    assert projection.status == "PRODUCTION"
    # ambiguous 는 절대 손대지 않는다(승인 전 enforcement 0)
    assert ambiguous.status == "WEIRD_STATUS"
    assert ambiguous.erp_stage_code is None
    assert result.ambiguous_skipped == 1
    # clean 은 불변
    assert clean.status == "RECEIVED" and clean.erp_stage_code == "RECEIVED"


def test_apply_skips_non_safe_mirror() -> None:
    """비-main workflow.stage(safe_target None)는 manual — apply 가 건드리지 않는다."""
    manual = _mirror_manual()
    result = apply_safe_repair([manual], dry_run=False)
    assert result.manual_skipped == 1
    assert len(result.mirror_repaired) == 0
    assert manual.erp_stage_code == "RECEIVED"  # 불변
    assert manual.status == "RECEIVED"


# --- 3. verify: 적용 후 coverage 100%·safe 잔여 0 --------------------------------
def test_verify_coverage_100_after_apply() -> None:
    orders = [_mirror_safe(), _projection_safe(), _ambiguous_unmapped(), _clean()]
    apply_safe_repair(orders, dry_run=False)
    report = verify_coverage(orders)
    assert report.coverage_ok is True
    assert report.safe_remaining == 0
    assert report.ambiguous_remaining == 1  # ambiguous 는 정상 잔존(manual CSV 대상)
    assert report.manual_remaining == 0


def test_verify_coverage_fails_before_apply() -> None:
    orders = [_mirror_safe(), _projection_safe()]
    report = verify_coverage(orders)
    assert report.coverage_ok is False
    assert report.safe_remaining == 2


# --- 4. manual CSV verifier: 유효 CSV만 통과, 자동 선택 0 -------------------------
def _ambiguous_audit() -> Any:
    return audit_order_state_axes([
        _order(id=10, status="WEIRD_STATUS", is_erp_order=True),
        _order(id=11, status="HAPPYCALL", is_erp_order=True),
    ])


def test_manual_csv_valid_passes() -> None:
    csv_text = (
        "order_id,status,reason,resolved_axis,resolved_value\n"
        "10,WEIRD_STATUS,UNMAPPED,MAIN,RECEIVED\n"
        "11,HAPPYCALL,DISPLAY_ALIAS,LOGISTICS,SCHEDULED\n"
    )
    res = verify_manual_csv(csv_text, audit=_ambiguous_audit(), require_all=True)
    assert res.resolved == {"10": ("MAIN", "RECEIVED"), "11": ("LOGISTICS", "SCHEDULED")}


def test_manual_csv_blank_resolution_refused() -> None:
    """빈 결정은 자동 선택하지 않고 거부한다(자동 선택 0)."""
    csv_text = (
        "order_id,status,reason,resolved_axis,resolved_value\n"
        "10,WEIRD_STATUS,UNMAPPED,,\n"
    )
    with pytest.raises(ManualCsvError) as exc:
        verify_manual_csv(csv_text, audit=_ambiguous_audit())
    assert any("auto-selection refused" in p for p in exc.value.problems)


def test_manual_csv_invalid_axis_and_value_rejected() -> None:
    bad_axis = (
        "order_id,status,reason,resolved_axis,resolved_value\n"
        "10,WEIRD_STATUS,UNMAPPED,NOT_AN_AXIS,RECEIVED\n"
    )
    with pytest.raises(ManualCsvError):
        verify_manual_csv(bad_axis, audit=_ambiguous_audit())

    bad_value = (
        "order_id,status,reason,resolved_axis,resolved_value\n"
        "10,WEIRD_STATUS,UNMAPPED,MAIN,NOT_A_CODE\n"
    )
    with pytest.raises(ManualCsvError):
        verify_manual_csv(bad_value, audit=_ambiguous_audit())


def test_manual_csv_header_mismatch_rejected() -> None:
    with pytest.raises(ManualCsvError):
        verify_manual_csv("wrong,header\n1,x\n")


def test_manual_csv_unknown_order_id_rejected() -> None:
    csv_text = (
        "order_id,status,reason,resolved_axis,resolved_value\n"
        "999,X,UNMAPPED,MAIN,RECEIVED\n"
    )
    with pytest.raises(ManualCsvError):
        verify_manual_csv(csv_text, audit=_ambiguous_audit())


def test_manual_csv_require_all_flags_missing() -> None:
    csv_text = (
        "order_id,status,reason,resolved_axis,resolved_value\n"
        "10,WEIRD_STATUS,UNMAPPED,MAIN,RECEIVED\n"
    )
    with pytest.raises(ManualCsvError) as exc:
        verify_manual_csv(csv_text, audit=_ambiguous_audit(), require_all=True)
    assert any("unresolved" in p for p in exc.value.problems)


def test_manual_csv_roundtrips_audit_export_header() -> None:
    """to_manual_csv 출력 헤더와 verifier 가 기대하는 헤더가 대칭이다."""
    exported = to_manual_csv(_ambiguous_audit())
    assert exported.splitlines()[0].split(",") == MANUAL_CSV_HEADER


# --- 5. read-only 대조: structured_data·전이 로직 무변경 --------------------------
def test_repair_never_touches_structured_data() -> None:
    """repair 는 status/erp_stage_code 두 flat 컬럼만 쓰고 canonical structured_data 는 불변."""
    orders = [_mirror_safe(), _projection_safe(), _ambiguous_unmapped(), _clean()]
    before_sd = [copy.deepcopy(o.structured_data) for o in orders]
    apply_safe_repair(orders, dry_run=False)
    after_sd = [o.structured_data for o in orders]
    assert after_sd == before_sd
