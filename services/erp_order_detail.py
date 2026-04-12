"""Compatibility shim for the canonical `foms.services.erp_order_detail` module."""

from foms.services.erp_order_detail import (
    attach_order_detail_payloads,
    build_order_detail_payload_map,
)

__all__ = [
    "build_order_detail_payload_map",
    "attach_order_detail_payloads",
]
