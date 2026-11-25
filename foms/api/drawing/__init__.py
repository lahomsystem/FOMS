"""Canonical drawing API surface."""

from foms.api.drawing.as_drawing import erp_orders_as_drawing_bp
from foms.api.drawing.erp_orders_drawing import erp_orders_drawing_bp
from foms.api.drawing import erp_orders_drawing_fix_read  # noqa: F401  R1 라우트를 erp_orders_drawing_bp 에 더한다
from foms.api.drawing.erp_orders_draftsman import erp_orders_draftsman_bp
from foms.api.drawing.erp_orders_item_cancel import erp_orders_item_cancel_bp
from foms.api.drawing.erp_orders_revision import erp_orders_revision_bp
from foms.api.drawing.erp_orders_sheet_factory import erp_orders_sheet_factory_bp
from foms.api.drawing.wizard import erp_orders_drawing_wizard_bp
from foms.api.drawing.erp_orders_drawing_fix import erp_orders_drawing_fix_bp  # [수정 시작] · [수정 취소](설계서 2026-11-25 N1 · N2)

__all__ = [
    "erp_orders_as_drawing_bp",
    "erp_orders_drawing_bp",
    "erp_orders_revision_bp",
    "erp_orders_draftsman_bp",
    "erp_orders_item_cancel_bp",
    "erp_orders_sheet_factory_bp",
    "erp_orders_drawing_wizard_bp",
    "erp_orders_drawing_fix_bp",
]
