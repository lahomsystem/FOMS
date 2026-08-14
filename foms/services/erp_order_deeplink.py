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


RETURN_TO_BACK_ENDPOINT: dict[str, str] = {
    "erp_measurement_dashboard": "erp_measurement_dashboard.erp_measurement_dashboard",
    "erp_shipment_dashboard": "erp_shipment_page.erp_shipment_dashboard",
    "erp_production_dashboard": "erp_production_page.erp_production_dashboard",
    "erp_construction_dashboard": "erp_construction_page.erp_construction_dashboard",
    "erp_drawing_workbench_dashboard": "erp_drawing_workbench.erp_drawing_workbench_dashboard",
    "erp_history_dashboard": "erp_history.history_dashboard",
}


def resolve_edit_return_back_endpoint(return_to: str) -> str:
    """
    Map ``return_to`` query tokens from queue/edit deep links to Flask endpoints.

    Args:
        return_to: Raw ``return_to`` query value from edit or mobile detail URLs.

    Returns:
        Blueprint endpoint name for ``url_for``.
    """
    token = (return_to or "").strip()
    return RETURN_TO_BACK_ENDPOINT.get(token, "erp_dashboard.erp_dashboard")


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


def load_focus_order_only(base_query, focus_order_id: int | None) -> list[Order]:
    """
    Search deep-link SSOT: ``focus_order`` → exactly one queue row (or empty).

    When both ``q`` and ``focus_order`` appear on a landing URL, ``q`` is for the
    search bar only; it must not widen the list to all name/phone matches.
    """
    if not focus_order_id:
        return []
    row = base_query.filter(Order.id == focus_order_id).first()
    return [row] if row else []


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
    "RETURN_TO_BACK_ENDPOINT",
    "resolve_order_stage_code",
    "load_focus_order_only",
    "build_order_queue_focus_href",
    "resolve_edit_return_back_endpoint",
]
