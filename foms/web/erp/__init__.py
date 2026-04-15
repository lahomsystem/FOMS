"""ERP hub blueprint and display helpers (canonical `foms.web.erp`)."""

from foms.web.erp.hub import (
    ERP_BETA_DEBUG,
    apply_erp_display_fields_to_orders,
    erp_bp,
    _can_modify_sales_domain,
    _ensure_dict,
    _normalize_for_search,
)

__all__ = [
    "ERP_BETA_DEBUG",
    "apply_erp_display_fields_to_orders",
    "erp_bp",
    "_can_modify_sales_domain",
    "_ensure_dict",
    "_normalize_for_search",
]
