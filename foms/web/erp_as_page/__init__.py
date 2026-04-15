"""Canonical ERP AS page (SFC-B11B: implementation in ``foms.web.erp_as_page.routes``)."""

from foms.web.erp_as_page.routes import (
    apply_erp_display_fields_to_orders,
    erp_as_dashboard,
    erp_as_page_bp,
    get_today_kst,
    sanitize_as_content_html,
    _ensure_dict,
)

__all__ = [
    "erp_as_page_bp",
    "erp_as_dashboard",
    "sanitize_as_content_html",
    "_ensure_dict",
    "apply_erp_display_fields_to_orders",
    "get_today_kst",
]
