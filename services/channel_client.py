"""Compatibility shim for the canonical `foms.services.channel_client` module."""

from foms.services.channel_client import (
    CHANNEL_APP_SECRET,
    CHANNEL_GROUP_CONSTRUCTION,
    CHANNEL_GROUP_GENERAL,
    CHANNEL_GROUP_MEASUREMENT,
    CHANNEL_ID,
    FOMS_BASE_URL,
    format_order_message,
    get_attachment_category_for_status,
    get_target_group_id,
    is_configured,
    send_group_message,
)

__all__ = [
    "CHANNEL_APP_SECRET",
    "CHANNEL_ID",
    "CHANNEL_GROUP_MEASUREMENT",
    "CHANNEL_GROUP_CONSTRUCTION",
    "CHANNEL_GROUP_GENERAL",
    "FOMS_BASE_URL",
    "is_configured",
    "get_target_group_id",
    "get_attachment_category_for_status",
    "format_order_message",
    "send_group_message",
]
