"""Compatibility shim for the canonical order date sync event stub."""

from foms.services.order_date_sync_event import register_order_date_sync_listener, sync_order_dates

__all__ = ["sync_order_dates", "register_order_date_sync_listener"]
