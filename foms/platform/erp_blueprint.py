"""ERP shell blueprint: shared Jinja filters (no HTML routes)."""

import os

from flask import Blueprint

from foms.services.erp_template_filters import register_erp_template_filters

erp_bp = Blueprint("erp", __name__)


def _erp_debug_flags_enabled() -> bool:
    """True when ERP_ORDER_DEBUG or legacy ERP_BETA_DEBUG enables verbose ERP diagnostics."""
    raw = (os.environ.get("ERP_ORDER_DEBUG") or os.environ.get("ERP_BETA_DEBUG") or "").lower()
    return raw in ("1", "true", "yes", "on")


ERP_ORDER_DEBUG = _erp_debug_flags_enabled()
ERP_BETA_DEBUG = ERP_ORDER_DEBUG  # legacy alias; remove when live gate allows

register_erp_template_filters(erp_bp)

__all__ = ["ERP_BETA_DEBUG", "ERP_ORDER_DEBUG", "erp_bp"]
