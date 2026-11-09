"""Canonical production web surface."""

from foms.web.production.dashboard import erp_production_page_bp
import foms.web.production.home  # noqa: F401  # 같은 Blueprint 에 /production/home 라우트를 붙인다

__all__ = ["erp_production_page_bp"]
"""Production bounded-context web package (Wave 4 page slice)."""
