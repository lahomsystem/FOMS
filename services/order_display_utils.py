"""Compatibility shim for the canonical `foms.services.order_display_utils` module."""

from foms.services.order_display_utils import (
    _ensure_dict,
    format_options_for_display,
)

__all__ = [
    "format_options_for_display",
    "_ensure_dict",
]
