"""Canonical orders web surface."""

from foms.web.orders.dashboard import (
    STAGE_LABELS,
    erp_dashboard,
    erp_dashboard_bp,
    recommend_owner_team,
    _ensure_dict,
    _erp_alerts,
    _erp_get_stage,
    _erp_has_media,
)
from foms.web.orders.edit import order_edit_bp
from foms.web.orders.history import erp_history_bp, history_dashboard
from foms.web.orders.listing import enqueue_geocode_order_address, order_pages_bp
from foms.web.orders.trash import order_trash_bp

__all__ = [
    "order_pages_bp",
    "order_edit_bp",
    "order_trash_bp",
    "enqueue_geocode_order_address",
    "erp_dashboard_bp",
    "erp_dashboard",
    "STAGE_LABELS",
    "recommend_owner_team",
    "_ensure_dict",
    "_erp_get_stage",
    "_erp_alerts",
    "_erp_has_media",
    "erp_history_bp",
    "history_dashboard",
]
