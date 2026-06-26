"""Initial ERP workflow stage resolution for new orders (wizard + ERP form parity)."""

from __future__ import annotations

from typing import Any

__all__ = ["resolve_initial_workflow_stage"]


def _has_measurement_date(
    schedule: dict[str, Any] | None,
    items: list[dict[str, Any]] | None,
) -> bool:
    """Return True when schedule or any item carries a non-empty measurement date."""
    sched = schedule if isinstance(schedule, dict) else {}
    if str(sched.get("measurement_date") or "").strip():
        return True
    for raw in items or []:
        if isinstance(raw, dict) and str(raw.get("measurement_date") or "").strip():
            return True
    return False


def resolve_initial_workflow_stage(
    *,
    orderer: str | None = None,
    schedule: dict[str, Any] | None = None,
    items: list[dict[str, Any]] | None = None,
) -> str:
    """
    Resolve workflow.stage for a newly created ERP order.

    Mirrors ``erp-order-shared.js`` submit rules:
    - 실측일(schedule or item) 있으면 MEASURE (발주사 무관)
    - 발주사가 라홈이 아니면 MEASURE (하우드·직접입력 포함)
    - 그 외 RECEIVED
    """
    if _has_measurement_date(schedule, items):
        return "MEASURE"
    orderer_name = (orderer or "").strip()
    if orderer_name and orderer_name != "라홈":
        return "MEASURE"
    return "RECEIVED"
