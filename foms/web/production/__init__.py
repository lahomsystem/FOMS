"""Canonical production web surface."""

from foms.web.production.dashboard import erp_production_page_bp
import foms.web.production.home  # noqa: F401  # 같은 Blueprint 에 /production/home 라우트를 붙인다
import foms.web.production.part_thumb  # noqa: F401  # 같은 Blueprint 에 도면 카드 작은 그림 길을 붙인다(P15-5)

__all__ = ["erp_production_page_bp"]
"""Production bounded-context web package (Wave 4 page slice)."""
