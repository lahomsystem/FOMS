"""Canonical auth web surface (SFC-B11B: implementation in ``foms.web.auth.routes``)."""

from foms.web.auth.routes import (
    ROLES,
    TEAMS,
    auth_bp,
    detach_user_references_for_delete,
    get_user_by_id,
    get_user_by_username,
    is_password_strong,
    log_access,
    login_required,
    role_required,
)

__all__ = [
    "ROLES",
    "TEAMS",
    "auth_bp",
    "detach_user_references_for_delete",
    "get_user_by_id",
    "get_user_by_username",
    "is_password_strong",
    "log_access",
    "login_required",
    "role_required",
]
