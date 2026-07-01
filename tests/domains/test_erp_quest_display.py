"""ERP quest display SSOT — resolve, approval state, assignee gate."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from foms.services import erp_quest_display as qd

ROOT = Path(__file__).resolve().parents[2]


def test_resolve_synthesizes_template_when_no_persisted_quest() -> None:
    sd = {"workflow": {"stage": "MEASURE"}, "quests": []}
    quest = qd.resolve_current_quest(sd, "실측", "MEASURE")
    assert quest is not None
    assert quest.get("title")
    assert quest.get("status") == "OPEN"


def test_resolve_skips_completed_when_only_stale_measure_quest() -> None:
    sd = {
        "workflow": {"stage": "DRAWING"},
        "quests": [
            {
                "stage": "실측",
                "title": "실측",
                "status": "COMPLETED",
                "approval_mode": "assignee",
                "assignee_approval": {"approved": True},
            },
            {"stage": "도면", "title": "도면", "status": "OPEN", "approval_mode": "assignee"},
        ],
    }
    quest = qd.resolve_current_quest(sd, "도면", "DRAWING")
    assert quest is None


def test_resolve_picks_open_stage_matched_quest() -> None:
    sd = {
        "workflow": {"stage": "MEASURE"},
        "quests": [
            {"stage": "실측", "title": "실측", "status": "COMPLETED"},
            {"stage": "실측", "title": "실측", "status": "OPEN", "approval_mode": "assignee"},
        ],
    }
    quest = qd.resolve_current_quest(sd, "실측", "MEASURE")
    assert quest is not None
    assert quest.get("status") == "OPEN"


def test_all_approved_assignee_mode_when_approved() -> None:
    quest = {
        "approval_mode": "assignee",
        "assignee_approval": {"approved": True},
        "status": "IN_PROGRESS",
    }
    all_ok, missing, _, _ = qd._compute_approval_state(quest, "실측", {})
    assert all_ok is True
    assert missing == []


def test_build_payload_sets_can_assignee_for_manager_name_match() -> None:
    sd = {
        "workflow": {"stage": "MEASURE"},
        "parties": {"manager": {"name": "Manager Kim"}},
        "quests": [
            {
                "stage": "실측",
                "title": "실측",
                "status": "OPEN",
                "approval_mode": "assignee",
                "assignee_approval": {"approved": False},
            }
        ],
    }
    user = SimpleNamespace(
        id=9,
        name="Manager Kim",
        username="mkim",
        role="STAFF",
        team="CONSTRUCTION",
    )
    order = SimpleNamespace(id=1, manager_name="Manager Kim", structured_data=sd)
    payload = qd.build_current_quest_payload(
        sd=sd,
        stage="실측",
        stage_code="MEASURE",
        order=order,
        current_user=user,
        user_map={},
    )
    assert payload is not None
    assert payload["can_assignee_approve"] is True
    assert payload["all_approved"] is False


def test_mobile_detail_template_allows_assignee_gate() -> None:
    partial = (
        ROOT / "templates" / "orders" / "partials" / "order_detail_mobile_v2.html"
    ).read_text(encoding="utf-8")
    assert "can_approve_quest" in partial
    assert "can_assignee_approve" in partial
    assert "invalidatePrimaryNavFragmentCache" in partial


def test_resolve_order_role_assignees_from_structured_data() -> None:
    sd = {
        "parties": {"manager": {"name": "안중훈"}},
        "assignments": {
            "sales_assignee_user_ids": [7],
            "drawing_assignee_user_ids": [41],
        },
        "drawing_assignees": [{"id": 41, "name": "최상용"}],
        "shipment": {
            "construction_workers": ["김시공", "박시공"],
            "drawing_manager": "레거시도면",
        },
    }
    order = SimpleNamespace(manager_name="안중훈")
    roles = qd.resolve_order_role_assignees(sd, order=order, user_map={7: "한용희", 41: "최상용"})
    assert roles["measurement_assignee"] == "한용희"
    assert roles["drawing_assignee"] == "최상용"
    assert roles["construction_assignee"] == "김시공, 박시공"


def test_resolve_order_role_assignees_from_id_only_drawing_assignees() -> None:
    sd = {
        "drawing_assignees": [{"id": 41}],
        "assignments": {"drawing_assignee_user_ids": [41]},
        "shipment": {},
    }
    roles = qd.resolve_order_role_assignees(sd, user_map={41: "최상용"})
    assert roles["drawing_assignee"] == "최상용"


def test_resolve_order_role_assignees_normalizes_numeric_manager_id() -> None:
    sd = {
        "parties": {"manager": {"name": 99}},
    }
    order = SimpleNamespace(manager_name="Alice")
    roles = qd.resolve_order_role_assignees(sd, order=order, user_map={99: "Resolved Manager"})
    assert roles["measurement_assignee"] == "Resolved Manager"


def test_mobile_order_detail_renders_role_assignee_section() -> None:
    partial = (
        ROOT / "templates" / "orders" / "partials" / "order_detail_mobile_v2.html"
    ).read_text(encoding="utf-8")
    assert "foms-detail-assignee-title" in partial
    assert "measurement_assignee" in partial
    assert "drawing_assignee" in partial
    assert "construction_assignee" in partial
    assert "{'label': '담당', 'value': order.manager_name" not in partial


def test_build_payload_none_for_drawing_stage() -> None:
    sd = {
        "workflow": {"stage": "DRAWING"},
        "quests": [
            {
                "stage": "실측",
                "title": "실측",
                "status": "COMPLETED",
                "approval_mode": "assignee",
                "assignee_approval": {"approved": True},
            }
        ],
    }
    order = SimpleNamespace(id=2761, manager_name="Test", structured_data=sd)
    payload = qd.build_current_quest_payload(
        sd=sd,
        stage="도면",
        stage_code="DRAWING",
        order=order,
        current_user=None,
        user_map={},
    )
    assert payload is None


def test_erp_shell_exports_fragment_cache_invalidation() -> None:
    shell_js = (ROOT / "static" / "js" / "runtime" / "erp-shell.js").read_text(encoding="utf-8")
    assert "invalidatePrimaryNavFragmentCache" in shell_js
    assert "invalidateFragmentCache" in shell_js


def test_measurement_mobile_list_does_not_force_measure_badge() -> None:
    listing = (
        ROOT / "templates" / "measurement" / "partials" / "mobile_list.html"
    ).read_text(encoding="utf-8")
    assert "badge_text='실측'" not in listing
    assert "'--measure'" not in listing
