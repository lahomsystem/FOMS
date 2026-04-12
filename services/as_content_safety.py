"""Compatibility shim for the canonical `foms.services.as_content_safety` module."""

from foms.services.as_content_safety import (
    as_content_html_to_text,
    load_structured_data_dict_or_raise,
    sanitize_as_content_html,
)

__all__ = [
    "sanitize_as_content_html",
    "as_content_html_to_text",
    "load_structured_data_dict_or_raise",
]
