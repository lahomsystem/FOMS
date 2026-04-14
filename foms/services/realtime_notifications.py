"""Compatibility shim: flat `foms.services.realtime_notifications` → notifications package."""

from foms.services.notifications.realtime_notifications import emit_erp_notification_to_users

__all__ = ["emit_erp_notification_to_users"]
