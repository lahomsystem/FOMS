"""Compatibility shim for the canonical `foms.services.estimate_service` module."""

from foms.services.estimate_service import (
    create_estimate,
    extract_estimate_data_from_order,
    generate_estimate_number,
    update_estimate,
)

__all__ = [
    "generate_estimate_number",
    "extract_estimate_data_from_order",
    "create_estimate",
    "update_estimate",
]
