"""Compatibility shim for the canonical `foms.services.channel_quick_actions` module."""

from foms.services.channel_quick_actions import (
    STATUS_MAP,
    get_order_attachments_for_wam,
    get_order_summary_for_wam,
    parse_foms_command,
    process_foms_command,
)

__all__ = [
    "STATUS_MAP",
    "parse_foms_command",
    "process_foms_command",
    "get_order_summary_for_wam",
    "get_order_attachments_for_wam",
]
