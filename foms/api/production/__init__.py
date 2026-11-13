"""Canonical production API surface."""

from foms.api.production.orders import erp_orders_production_bp
from foms.api.production.part_marks import production_part_marks_bp
import foms.api.production.part_marks_read  # noqa: F401,E402  # 같은 Blueprint 에 30초 받아 오기 GET 을 붙인다(P15-7)

__all__ = ["erp_orders_production_bp", "production_part_marks_bp"]
