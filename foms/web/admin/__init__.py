"""Canonical admin web surface."""

from foms.web.admin.routes import admin_api_users, admin_bp, admin_migration, admin_notifications, admin_test_r2, update_menu

__all__ = [
    "admin_bp",
    "update_menu",
    "admin_migration",
    "admin_test_r2",
    "admin_notifications",
    "admin_api_users",
]
