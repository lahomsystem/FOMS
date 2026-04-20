"""Canonical admin web surface."""

import foms.web.admin.audit  # noqa: F401 — registers audit routes on admin_bp

from foms.web.admin.excel_import import excel_bp
from foms.web.admin.routes import (
    admin_api_users,
    admin_bp,
    admin_migration,
    admin_notifications,
    admin_test_r2,
    update_menu,
)
from foms.web.admin.storage import storage_dashboard_bp

__all__ = [
    "admin_api_users",
    "admin_bp",
    "admin_migration",
    "admin_notifications",
    "admin_test_r2",
    "excel_bp",
    "storage_dashboard_bp",
    "update_menu",
]
