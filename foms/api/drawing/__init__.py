"""Canonical drawing API surface."""

from foms.api.drawing.erp_orders_drawing import erp_orders_drawing_bp
from foms.api.drawing.erp_orders_draftsman import erp_orders_draftsman_bp
from foms.api.drawing.erp_orders_revision import erp_orders_revision_bp
from foms.api.drawing.wizard import erp_orders_drawing_wizard_bp

__all__ = [
    "erp_orders_drawing_bp",
    "erp_orders_revision_bp",
    "erp_orders_draftsman_bp",
    "erp_orders_drawing_wizard_bp",
]
