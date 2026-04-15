"""Canonical ERP main dashboard (SFC-B11B: implementation in ``foms.web.erp_dashboard.routes``)."""

from foms.web.erp_dashboard.routes import (
    STAGE_LABELS,
    erp_dashboard,
    erp_dashboard_bp,
    recommend_owner_team,
    _ensure_dict,
    _erp_alerts,
    _erp_get_stage,
    _erp_has_media,
)

__all__ = [
    "erp_dashboard_bp",
    "erp_dashboard",
    "STAGE_LABELS",
    "recommend_owner_team",
    "_ensure_dict",
    "_erp_get_stage",
    "_erp_alerts",
    "_erp_has_media",
]
