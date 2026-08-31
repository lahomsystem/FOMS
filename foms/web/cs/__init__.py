"""Canonical CS web surface."""

from foms.web.cs.as_dashboard import erp_as_page_bp
from foms.web.cs.completion_dashboard import erp_completion_page_bp
from foms.web.cs.settlement_dashboard import erp_settlement_page_bp

__all__ = ["erp_as_page_bp", "erp_completion_page_bp", "erp_settlement_page_bp"]
