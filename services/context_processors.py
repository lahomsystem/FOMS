"""Compatibility shim for the canonical `foms.services.context_processors` module."""

from foms.services.context_processors import (
    inject_menu,
    inject_status_list,
    inject_statuses,
    parse_json_string,
    parse_json_string_filter,
    register_context_processors,
    utility_processor,
)

__all__ = [
    "parse_json_string_filter",
    "parse_json_string",
    "inject_statuses",
    "inject_status_list",
    "utility_processor",
    "inject_menu",
    "register_context_processors",
]
