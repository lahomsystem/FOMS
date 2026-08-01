"""다축 상태 read model·legacy alias·projection·audit 분류 (STATE-MODEL-00).

순수 read-only 파생이라 DB가 필요 없다 — SimpleNamespace order로 계약을 고정한다.
"""
from __future__ import annotations

import copy
from types import SimpleNamespace
from typing import Any, Dict

import pytest

from foms.services.orders.state_axes import (
    AXIS_AS,
    AXIS_DELETE,
    AXIS_HOLD,
    AXIS_LOGISTICS,
    AXIS_MAIN,
    OrderStateAxes,
    classify_status_to_axes,
    is_legacy_display_alias,
    legacy_status_projection,
    read_current_production_run,
    read_current_quest,
    read_drawing_revision_registry,
    read_state_axes,
)
from foms.services.orders.state_axes_audit import (
    DISPLAY_ALIAS,
    MULTI_AXIS,
    UNMAPPED,
    audit_order_state_axes,
    to_manual_csv,
)
from tests.fixtures.state_axes_projection import PROJECTION_CASES


def _order(**kwargs: Any) -> SimpleNamespace:
    """Order-like fake. 기본값으로 audit이 읽는 속성을 모두 채운다."""
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


# --- 1. 다축 read + projection fixture 계약 --------------------------------------
@pytest.mark.parametrize("case", PROJECTION_CASES, ids=lambda c: c["id"])
def test_projection_fixture_contract(case: Dict[str, Any]) -> None:
    """fixture의 각 case: read_state_axes 축 값 + legacy projection이 계약과 일치."""
    order = _order(**copy.deepcopy(case["order"]))
    axes = read_state_axes(order)
    expected = case["axes"]
    assert axes.main == expected["main"], case["id"]
    assert axes.logistics == expected["logistics"], case["id"]
    assert axes.hold == expected["hold"], case["id"]
    assert axes.as_status == expected["as_status"], case["id"]
    assert axes.deleted == expected["deleted"], case["id"]
    assert axes.construction == expected["construction"], case["id"]
    assert legacy_status_projection(axes) == case["projection"], case["id"]


def test_projection_priority_delete_over_all() -> None:
    """우선순위 DELETED > ON_HOLD > AS > logistics > main."""
    axes = OrderStateAxes(
        main="PRODUCTION",
        logistics="SCHEDULED",
        hold="HELD",
        as_status="IN_PROGRESS",
        deleted="DELETED",
        construction="NONE",
    )
    assert legacy_status_projection(axes) == "DELETED"


def test_projection_priority_hold_over_as_logistics_main() -> None:
    axes = OrderStateAxes("PRODUCTION", "SCHEDULED", "HELD", "IN_PROGRESS", "NONE", "NONE")
    assert legacy_status_projection(axes) == "ON_HOLD"


def test_projection_priority_as_over_logistics_main() -> None:
    axes = OrderStateAxes("PRODUCTION", "SCHEDULED", "NONE", "COMPLETED", "NONE", "NONE")
    assert legacy_status_projection(axes) == "AS_COMPLETED"


# --- 2. legacy alias → canonical mapping ---------------------------------------
@pytest.mark.parametrize(
    "status,axis,value",
    [
        ("MEASURED", AXIS_LOGISTICS, "MEASURED"),
        ("REGIONAL_MEASURED", AXIS_LOGISTICS, "REGIONAL_MEASURED"),
        ("SCHEDULED", AXIS_LOGISTICS, "SCHEDULED"),
        ("SHIPPED_PENDING", AXIS_LOGISTICS, "SHIPPED_PENDING"),
        ("ON_HOLD", AXIS_HOLD, "HELD"),
        ("AS_RECEIVED", AXIS_AS, "RECEIVED"),
        ("AS", AXIS_AS, "IN_PROGRESS"),
        ("AS_COMPLETED", AXIS_AS, "COMPLETED"),
        ("DELETED", AXIS_DELETE, "DELETED"),
        ("PRODUCTION", AXIS_MAIN, "PRODUCTION"),
        ("생산", AXIS_MAIN, "PRODUCTION"),
    ],
)
def test_classify_status_single_axis(status: str, axis: str, value: str) -> None:
    """대표 legacy status는 정확히 1개 canonical 축으로 매핑된다."""
    matches = classify_status_to_axes(status)
    assert matches == [(axis, value)]


def test_classify_unmapped_and_display_alias() -> None:
    assert classify_status_to_axes("BOGUS_XYZ") == []
    assert classify_status_to_axes("") == []
    assert is_legacy_display_alias("HAPPYCALL") is True
    assert is_legacy_display_alias("SHIPMENT") is True
    assert is_legacy_display_alias("MEASURED") is False


# --- 3. audit: mirror / projection / overlay 분리 분류 --------------------------
def test_audit_mirror_mismatch_safe_target() -> None:
    """workflow.stage != erp_stage_code, stage가 유효 main → safe_target."""
    order = _order(
        status="MEASURE",
        is_erp_order=True,
        structured_data={"workflow": {"stage": "MEASURE"}},
        erp_stage_code="RECEIVED",
    )
    audit = audit_order_state_axes([order])
    assert len(audit.mirror_mismatch) == 1
    mm = audit.mirror_mismatch[0]
    assert mm.workflow_stage == "MEASURE"
    assert mm.erp_stage_code == "RECEIVED"
    assert mm.safe_target == "MEASURE"
    assert mm in audit.safe


def test_audit_projection_mismatch_recomputable() -> None:
    """canonical projection != order.status, status가 단일 축 → recomputable(safe)."""
    # canonical hold.active=False 인데 status=ON_HOLD → projection=PRODUCTION != ON_HOLD
    order = _order(
        status="ON_HOLD",
        is_erp_order=True,
        structured_data={"workflow": {"stage": "PRODUCTION", "hold": {"active": False}}},
        erp_stage_code="PRODUCTION",
    )
    audit = audit_order_state_axes([order])
    assert len(audit.projection_mismatch) == 1
    pm = audit.projection_mismatch[0]
    assert pm.actual_status == "ON_HOLD"
    assert pm.expected_projection == "PRODUCTION"
    assert pm.recomputable is True
    assert pm in audit.safe


def test_audit_overlay_ambiguity_unmapped_and_display() -> None:
    unmapped = _order(id=10, status="WEIRD_STATUS", is_erp_order=True)
    display = _order(id=11, status="HAPPYCALL", is_erp_order=True)
    audit = audit_order_state_axes([unmapped, display])
    reasons = {a.order_id: a.reason for a in audit.overlay_ambiguity}
    assert reasons[10] == UNMAPPED
    assert reasons[11] == DISPLAY_ALIAS
    assert len(audit.ambiguous) == 2


def test_audit_normal_overlay_divergence_not_mismatch() -> None:
    """logistics overlay가 stage 보존 → projection 일치, mismatch 아님, 별도 집계."""
    order = _order(
        status="SCHEDULED",
        is_erp_order=True,
        structured_data={"workflow": {"stage": "PRODUCTION"}},
        erp_stage_code="PRODUCTION",
    )
    audit = audit_order_state_axes([order])
    assert audit.projection_mismatch == []
    assert audit.overlay_ambiguity == []
    assert audit.normal_overlay_divergence == 1


def test_audit_clean_order_no_findings() -> None:
    order = _order(
        status="RECEIVED",
        is_erp_order=True,
        structured_data={"workflow": {"stage": "RECEIVED"}},
        erp_stage_code="RECEIVED",
    )
    audit = audit_order_state_axes([order])
    assert audit.total == 1
    assert audit.mirror_mismatch == []
    assert audit.projection_mismatch == []
    assert audit.overlay_ambiguity == []
    assert audit.safe == []
    assert audit.ambiguous == []


def test_audit_is_read_only() -> None:
    """audit은 order/structured_data를 절대 변경하지 않는다(자동수정 0)."""
    sd = {"workflow": {"stage": "MEASURE"}}
    order = _order(status="ON_HOLD", is_erp_order=True, structured_data=sd, erp_stage_code="RECEIVED")
    before = copy.deepcopy(sd)
    audit_order_state_axes([order])
    assert order.status == "ON_HOLD"
    assert order.erp_stage_code == "RECEIVED"
    assert order.structured_data == before


def test_to_manual_csv_only_ambiguous_sorted() -> None:
    orders = [
        _order(id=2, status="HAPPYCALL", is_erp_order=True),
        _order(id=1, status="ZZZ_UNKNOWN", is_erp_order=True),
        _order(id=3, status="RECEIVED", is_erp_order=True,
               structured_data={"workflow": {"stage": "RECEIVED"}}, erp_stage_code="RECEIVED"),
    ]
    audit = audit_order_state_axes(orders)
    csv_text = to_manual_csv(audit)
    lines = csv_text.strip().splitlines()
    assert lines[0] == "order_id,status,reason,resolved_axis,resolved_value"
    # order_id 정렬, clean order(3)는 제외
    assert lines[1].startswith("1,ZZZ_UNKNOWN")
    assert lines[2].startswith("2,HAPPYCALL")
    assert len(lines) == 3


# --- 4. registry canonical target read models ----------------------------------
def test_read_current_production_run() -> None:
    order = _order(
        is_erp_order=True,
        structured_data={
            "production": {
                "current_run_id": "r2",
                "runs": [
                    {"run_id": "r1", "status": "SUPERSEDED"},
                    {"run_id": "r2", "status": "IN_PROGRESS"},
                ],
            }
        },
    )
    run = read_current_production_run(order)
    assert run is not None and run["run_id"] == "r2" and run["status"] == "IN_PROGRESS"
    assert read_current_production_run(_order(is_erp_order=True, structured_data={})) is None


def test_read_current_quest_skips_terminal() -> None:
    order = _order(
        is_erp_order=True,
        structured_data={
            "workflow": {"current_quest_id": "q1"},
            "quests": [
                {"quest_id": "q1", "transitions": [{"to": "SUPERSEDED"}]},
            ],
        },
    )
    # current_quest_id가 terminal quest를 가리키면 current 없음
    assert read_current_quest(order) is None

    live = _order(
        is_erp_order=True,
        structured_data={
            "workflow": {"current_quest_id": "q2"},
            "quests": [{"quest_id": "q2", "transitions": [{"to": "APPROVED"}]}],
        },
    )
    quest = read_current_quest(live)
    assert quest is not None and quest["quest_id"] == "q2"


def test_read_drawing_revision_registry_pointers() -> None:
    order = _order(
        is_erp_order=True,
        structured_data={
            "drawing": {
                "current_revision_id": "rev2",
                "receipt_revision_id": "rev2",
                "customer_confirmed_revision_id": None,
                "customer_confirmation_quest_id": None,
                "current_revision_request_id": None,
                "revisions": [
                    {"revision_id": "rev1"},
                    {"revision_id": "rev2", "source": "WIZARD_PENDING"},
                ],
            }
        },
    )
    reg = read_drawing_revision_registry(order)
    assert reg["current_revision_id"] == "rev2"
    assert reg["receipt_revision_id"] == "rev2"
    assert reg["current_revision"]["source"] == "WIZARD_PENDING"

    empty = read_drawing_revision_registry(_order(is_erp_order=True, structured_data={}))
    assert empty["current_revision_id"] is None
    assert empty["current_revision"] is None
