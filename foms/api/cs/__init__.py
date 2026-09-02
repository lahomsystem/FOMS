"""Canonical CS / AS API surface."""

from foms.api.cs.as_orders import erp_orders_as_bp
from foms.api.cs.dashboard import erp_orders_completion_bp
from foms.api.cs.complete import erp_orders_cs_bp
from foms.api.cs.confirm import erp_orders_confirm_bp
from foms.api.cs.settlement import settlement_api_bp
from foms.api.cs.settlement_channel import settlement_channel_api_bp

__all__ = [
    "erp_orders_cs_bp",
    "erp_orders_as_bp",
    "erp_orders_completion_bp",
    "erp_orders_confirm_bp",
    "settlement_api_bp",
    "settlement_channel_api_bp",
]
