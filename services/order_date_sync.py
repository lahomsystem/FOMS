"""Compatibility shim for the canonical `foms.services.order_date_sync` module."""

from foms.services.order_date_sync import (
    collect_order_schedule_date_specs,
    register_date_sync_listener,
    sync_order_dates,
)

__all__ = [
    "collect_order_schedule_date_specs",
    "sync_order_dates",
    "register_date_sync_listener",
]

