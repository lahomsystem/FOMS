"""Compatibility shim for the canonical `foms.services.channel_event_payloads` module."""

from foms.services.channel_event_payloads import (
    build_field_change_payload,
    build_payment_confirmation_payload,
    build_shipment_update_payload,
    build_structured_update_payload,
)

__all__ = [
    "build_structured_update_payload",
    "build_field_change_payload",
    "build_shipment_update_payload",
    "build_payment_confirmation_payload",
]
