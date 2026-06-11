"""Stage-aware queue deep links (search, briefing board, notifications)."""

from __future__ import annotations

from urllib.parse import quote

from models import Order

from foms.services.erp_display import _ensure_dict, _erp_get_stage
from foms.services.erp_policy import STAGE_NAME_TO_CODE

# 단계별 큐 대시보드 (personal_board STAGE_DASHBOARD_URL SSOT)
STAGE_DASHBOARD_URL: dict[str, str] = {
    "RECEIVED": "/erp/dashboard",
    "MEASURE": "/erp/measurement",
    "DRAWING": "/erp/drawing-workbench",
    "CONFIRM": "/erp/dashboard",
    "PRODUCTION": "/erp/production/dashboard",
    "CONSTRUCTION": "/erp/construction/dashboard",
    "CS": "/erp/dashboard",
    "COMPLETED": "/erp/completion",
    "AS": "/erp/as",
    "AS_RECEIVED": "/erp/as",
    "AS_COMPLETED": "/erp/as",
}


def resolve_order_stage_code(order: Order) -> str:
    """
    Resolve canonical workflow stage code for an ERP order.

    Args:
        order: Loaded Order ORM row.

    Returns:
        Stage code string (e.g. ``DRAWING``, ``MEASURE``).
    """
    sd = _ensure_dict(order.structured_data)
    stage_raw = order.erp_stage_code or order.status or _erp_get_stage(order, sd) or ""
    if str(stage_raw).lower() in {"erpbeta", "erporder"}:
        stage_raw = _erp_get_stage(order, sd) or "RECEIVED"
    return STAGE_NAME_TO_CODE.get(stage_raw, stage_raw) or "RECEIVED"


def build_order_queue_focus_href(
    order: Order,
    *,
    search_query: str | None = None,
) -> str:
    """
    Build mobile search / briefing deep link to the stage queue with card focus.

    Lands on the same queue-card surfaces as each workflow tab (not ``/edit``).

    Args:
        order: ERP order row.
        search_query: Optional search term to pre-filter the queue list.

    Returns:
        Relative URL with ``focus_order`` (and ``view=queue`` on home when needed).
    """
    stage_code = resolve_order_stage_code(order)
    base = STAGE_DASHBOARD_URL.get(stage_code, "/erp/dashboard").split("?")[0]
    params: list[str] = []

    if stage_code == "AS_COMPLETED":
        params.append("tab=completed")
    elif stage_code in ("AS", "AS_RECEIVED"):
        params.append("tab=incomplete")
    elif base in ("/erp/dashboard",):
        params.append("view=queue")

    trimmed_q = (search_query or "").strip()
    if trimmed_q:
        params.append(f"q={quote(trimmed_q, safe='')}")

    params.append(f"focus_order={order.id}")
    return f"{base}?{'&'.join(params)}"


__all__ = [
    "STAGE_DASHBOARD_URL",
    "resolve_order_stage_code",
    "build_order_queue_focus_href",
]
