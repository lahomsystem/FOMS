"""Compatibility shim for the canonical `foms.services.geocode_helpers` module."""

from foms.services.geocode_helpers import (
    compute_address_hash,
    extract_address_from_order,
    extract_address_from_structured_data,
)

__all__ = [
    "compute_address_hash",
    "extract_address_from_structured_data",
    "extract_address_from_order",
]
