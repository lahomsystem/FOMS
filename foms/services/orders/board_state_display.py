"""주문 목록·휴대폰 '현재 작업' 칸의 보드 단계(생산·시공·완료·AS) 표시."""
from __future__ import annotations

from typing import Any

from foms.services.erp_display import _erp_get_stage
from foms.services.orders.erp_policy_constants import STAGE_NAME_TO_CODE
from foms.services.orders.quest_approve_cta import display_quest_title
from foms.services.production_read_model import (
    _kpi_stage_label_from_erp_stage,
    fetch_production_current_run_ids,
)

__all__ = [
    "build_board_state",
    "construction_display_stage",
    "production_run_ids_for",
]


def construction_display_stage(order, structured_data):
    stage = _erp_get_stage(order, structured_data)
    workflow = structured_data.get("workflow")
    history = (workflow.get("history") if isinstance(workflow, dict) else None) or []
    is_started = any(
        isinstance(entry, dict) and str(entry.get("note")).strip() == "시공 시작"
        for entry in history
    )
    if stage in ("CONSTRUCTION", "시공"):
        return "시공중" if is_started else "시공대기"
    if stage in ("COMPLETED", "완료", "AS_WAIT") or stage == "CS":
        return "시공완료"
    if stage == "CONSTRUCTING":
        return "시공중"
    return None


def production_run_ids_for(db: Any, orders: list[Any], sds_by_id: dict[int, Any]) -> set[int]:
    """생산 단계 주문만 골라 current run 이 있는 id 집합. 고른 것이 없으면 쿼리 0회."""
    picked = [
        o for o in orders
        if STAGE_NAME_TO_CODE.get(_erp_get_stage(o, sds_by_id.get(o.id) or {}), '') == 'PRODUCTION'
    ]
    if not picked:
        return set()
    return fetch_production_current_run_ids(db, picked)


def _state(kind, label, tone, *, title="", link_label="", link_endpoint="", link_params=None):
    return {
        "kind": kind,
        "label": label,
        "tone": tone,
        "title": title,
        "link_label": link_label,
        "link_endpoint": link_endpoint,
        "link_params": link_params or {},
    }


def build_board_state(order, sd, stage_code, *, has_current_run=False, current_quest=None) -> dict | None:
    if stage_code == "PRODUCTION":
        if current_quest and not current_quest.get("is_synthesized") and not current_quest.get("is_done"):
            return None
        return _state(
            "production",
            _kpi_stage_label_from_erp_stage("PRODUCTION", has_current_run),
            "soft",
            link_label="생산 보드 열기",
            link_endpoint="erp_production_page.erp_production_dashboard",
            link_params={"focus_order": order.id},
        )
    if stage_code == "CONSTRUCTION":
        return _state(
            "construction",
            construction_display_stage(order, sd),
            "soft",
            link_label="시공 보드 열기",
            link_endpoint="erp_construction_page.erp_construction_dashboard",
            link_params={"focus_order": order.id},
        )
    if stage_code in ("COMPLETED", "AS_COMPLETED"):
        return _state("completed", "완료", "ok")
    if stage_code in ("AS", "AS_RECEIVED"):
        return _state(
            "as",
            "할 일",
            "warn",
            title=display_quest_title("AS", None),
            link_label="AS 화면 열기",
            link_endpoint="erp_as_page.erp_as_dashboard",
            link_params={"focus_order": order.id},
        )
    return None
