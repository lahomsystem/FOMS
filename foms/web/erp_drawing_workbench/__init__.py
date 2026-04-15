"""Canonical ERP drawing workbench (SFC-B11B: implementation in ``foms.web.erp_drawing_workbench.routes``)."""

from foms.web.erp_drawing_workbench.routes import (
    erp_drawing_workbench_bp,
    erp_drawing_workbench_dashboard,
    erp_drawing_workbench_detail,
    _can_modify_sales_domain,
    _drawing_next_action_text,
    _drawing_status_label,
    _ensure_dict,
    _erp_alerts,
    _erp_get_stage,
)

__all__ = [
    "erp_drawing_workbench_bp",
    "erp_drawing_workbench_dashboard",
    "erp_drawing_workbench_detail",
    "_ensure_dict",
    "_erp_get_stage",
    "_erp_alerts",
    "_can_modify_sales_domain",
    "_drawing_status_label",
    "_drawing_next_action_text",
]
