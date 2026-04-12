"""Compatibility shim for the canonical `foms.services.channel_delivery` module."""

from foms.services.channel_delivery import (
    check_legacy_only_success_after_cutover,
    create_pending_delivery,
    get_delivery_metrics,
    get_queue_backlog,
    mark_api_failed,
    mark_api_rejected,
    mark_delivery_status,
    mark_order_updated_for_channel,
    mark_token_rate_limited,
    mask_payload,
)

__all__ = [
    "create_pending_delivery",
    "mark_delivery_status",
    "mark_api_failed",
    "mark_api_rejected",
    "mark_token_rate_limited",
    "get_delivery_metrics",
    "get_queue_backlog",
    "check_legacy_only_success_after_cutover",
    "mark_order_updated_for_channel",
    "mask_payload",
]
