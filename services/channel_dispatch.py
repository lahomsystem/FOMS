"""Compatibility shim for the canonical `foms.services.channel_dispatch` module."""

from foms.services.channel_dispatch import dispatch_channel_push, dispatch_order_event

__all__ = [
    "dispatch_channel_push",
    "dispatch_order_event",
]
