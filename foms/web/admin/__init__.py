"""Canonical admin web surface."""

import foms.web.admin.alimtalk_failures  # noqa: F401 — registers alimtalk-failure route on admin_bp
import foms.web.admin.audit  # noqa: F401 — registers audit routes on admin_bp
import foms.web.admin.backup_status  # noqa: F401 — registers backup-status route on admin_bp
import foms.web.admin.naver_ingest  # noqa: F401 — registers naver ingest routes on admin_bp
import foms.web.admin.naver_ingest  # noqa: F401 - registers naver ingest routes on admin_bp
import foms.web.admin.ops_approvals  # noqa: F401 — registers ops-approval routes on admin_bp

from foms.web.admin.backup_status import ops_ingest_bp
from foms.web.admin.routes import (
    admin_api_users,
    admin_bp,
    admin_notifications,
    admin_test_r2,
    update_menu,
)
from foms.web.admin.storage import storage_dashboard_bp

__all__ = [
    "admin_api_users",
    "admin_bp",
    "admin_notifications",
    "admin_test_r2",
    "ops_ingest_bp",
    "storage_dashboard_bp",
    "update_menu",
]
