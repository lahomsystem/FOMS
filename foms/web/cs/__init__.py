"""Canonical CS web surface."""

from foms.web.erp_as_page import erp_as_page_bp
from foms.web.cs.completion_dashboard import erp_completion_page_bp

__all__ = ["erp_as_page_bp", "erp_completion_page_bp"]
"""CS / completion bounded-context web package (Wave 4 page slice)."""
