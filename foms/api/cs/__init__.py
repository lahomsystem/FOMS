"""Canonical CS / AS API surface."""

from foms.api.cs.as_orders import erp_orders_as_bp
from foms.api.cs.dashboard import erp_orders_completion_bp
# 차감 넣기 · 취소 라우트를 같은 블루프린트에 붙인다(등록 전에 import 돼야 한다).
from foms.api.cs import settlement_deductions as _settlement_deductions  # noqa: F401,E402
from foms.api.cs.complete import erp_orders_cs_bp
from foms.api.cs.settlement import settlement_api_bp
from foms.api.cs.settlement_channel import settlement_channel_api_bp

__all__ = [
    "erp_orders_cs_bp",
    "erp_orders_as_bp",
    "erp_orders_completion_bp",
    "settlement_api_bp",
    "settlement_channel_api_bp",
]
