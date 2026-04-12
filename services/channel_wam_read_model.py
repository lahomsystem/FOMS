"""Compatibility shim for the canonical `foms.services.channel_wam_read_model` module."""

from foms.services.channel_wam_read_model import (
    STATUS_LABELS,
    WamOrderReadModel,
    WamTimelineEntry,
    build_order_read_model,
    get_order_for_wam,
    get_recent_events_for_wam,
    load_wam_order_read_model,
)

__all__ = [
    "STATUS_LABELS",
    "WamTimelineEntry",
    "WamOrderReadModel",
    "get_order_for_wam",
    "load_wam_order_read_model",
    "build_order_read_model",
    "get_recent_events_for_wam",
]
