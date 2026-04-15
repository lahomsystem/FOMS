"""ERP shell blueprint: shared Jinja filters (no HTML routes)."""

import os

from flask import Blueprint

from foms.services.erp_template_filters import register_erp_template_filters

erp_bp = Blueprint("erp", __name__)
ERP_BETA_DEBUG = os.environ.get("ERP_BETA_DEBUG", "").lower() in ("1", "true", "yes", "on")

register_erp_template_filters(erp_bp)

__all__ = ["ERP_BETA_DEBUG", "erp_bp"]
