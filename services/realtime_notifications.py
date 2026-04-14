"""Compatibility shim for the canonical notifications package module."""

from foms.services.notifications.realtime_notifications import emit_erp_notification_to_users

__all__ = ["emit_erp_notification_to_users"]
