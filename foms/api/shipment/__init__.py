"""Canonical shipment API surface."""

from foms.api.shipment.settings import erp_shipment_bp

import foms.api.shipment.recommendations  # noqa: F401 — registers AS recommendation routes on erp_shipment_bp

__all__ = ["erp_shipment_bp"]
