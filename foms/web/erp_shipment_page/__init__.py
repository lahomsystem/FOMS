"""Canonical ERP shipment page (SFC-B11B: implementation in ``foms.web.erp_shipment_page.routes``)."""

from foms.web.erp_shipment_page.routes import (
    apply_erp_display_fields_to_orders,
    erp_shipment_dashboard,
    erp_shipment_page_bp,
    get_today_kst,
    _ensure_dict,
)

__all__ = [
    "erp_shipment_page_bp",
    "erp_shipment_dashboard",
    "_ensure_dict",
    "apply_erp_display_fields_to_orders",
    "get_today_kst",
]
