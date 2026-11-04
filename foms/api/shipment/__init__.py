"""Canonical shipment API surface."""

from foms.api.shipment.settings import erp_shipment_bp

import foms.api.shipment.recommendations  # noqa: F401 — registers AS recommendation routes on erp_shipment_bp
import foms.api.shipment.packing  # noqa: F401 — registers packing checklist routes on erp_shipment_bp
import foms.api.shipment.change_ack  # noqa: F401 — registers 시공일 변경 확인(ack) route on erp_shipment_bp
import foms.api.shipment.partner_request  # noqa: F401 — registers 시공일 정하기(협력사 희망 판 · 주문 화면) routes on erp_shipment_bp

__all__ = ["erp_shipment_bp"]
