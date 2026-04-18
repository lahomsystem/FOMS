"""Flask context processors and template filters."""

from __future__ import annotations

import json
import os
from typing import Any

from flask import g, session, url_for

from foms.web.auth import ROLES
from foms.services.orders.status_constants import BULK_ACTION_STATUS, STATUS
from foms.persistence.main.db import get_db
from foms.persistence.main.models import User
from foms.services.menu_config import load_menu_config

__all__ = [
    "parse_json_string_filter",
    "parse_json_string",
    "inject_statuses",
    "inject_status_list",
    "utility_processor",
    "inject_menu",
    "register_context_processors",
]


def parse_json_string_filter(value: Any) -> Any:
    """Template filter: parse JSON-like strings, fallback to {} on failure."""
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return {}


def parse_json_string(json_string: str | None) -> Any | None:
    """Template helper: parse json_string, fallback to None on failure."""
    if not json_string:
        return None
    try:
        return json.loads(json_string)
    except json.JSONDecodeError:
        return None


def inject_statuses() -> dict[str, Any]:
    """Inject status constants."""
    return {
        "ALL_STATUS": STATUS,
        "BULK_ACTION_STATUS": BULK_ACTION_STATUS,
    }


def inject_status_list() -> dict[str, Any]:
    """Inject status lists and current-user context into templates."""
    display_status = {k: v for k, v in STATUS.items() if k != "DELETED"}
    bulk_action_status = {k: v for k, v in STATUS.items() if k != "DELETED"}
    current_user = getattr(g, "current_user", None)

    admin_switch_users: list[User] = []
    impersonating_from_id = session.get("impersonating_from")
    if current_user and current_user.role == "ADMIN":
        db = get_db()
        admin_switch_users = (
            db.query(User)
            .filter(
                User.is_active == True,
                User.id != current_user.id,
            )
            .order_by(User.name)
            .all()
        )

    erp_order_enabled = str(
        os.getenv("ERP_ORDER_ENABLED", os.getenv("ERP_BETA_ENABLED", "true"))
    ).lower() in [
        "1",
        "true",
        "yes",
        "y",
        "on",
    ]
    erp_mobile_v2_enabled = str(os.getenv("ERP_MOBILE_V2_ENABLED", "false")).lower() in [
        "1",
        "true",
        "yes",
        "y",
        "on",
    ]
    use_direct_upload_env = str(os.getenv("USE_DIRECT_UPLOAD", "1")).lower() in [
        "1",
        "true",
        "yes",
        "on",
    ]
    try:
        from foms.services.storage import get_storage

        storage = get_storage()
        use_direct_upload = use_direct_upload_env and storage.storage_type in ("r2", "s3")
    except Exception:
        use_direct_upload = False

    return {
        "STATUS": display_status,
        "BULK_ACTION_STATUS": bulk_action_status,
        "ALL_STATUS": STATUS,
        "ROLES": ROLES,
        "current_user": current_user,
        "admin_switch_users": admin_switch_users,
        "impersonating_from_id": impersonating_from_id,
        "erp_order_enabled": erp_order_enabled,
        "erp_mobile_v2_enabled": erp_mobile_v2_enabled,
        "use_direct_upload": use_direct_upload,
    }


def utility_processor() -> dict[str, Any]:
    """Inject small template utility helpers."""
    return {"parse_json_string": parse_json_string}


def inject_menu() -> dict[str, Any]:
    """Inject menu config, narrowing the construction-team navigation."""
    menu = load_menu_config()
    if isinstance(menu, dict):
        user = getattr(g, "current_user", None)
        if user and getattr(user, "team", None) == "CONSTRUCTION":
            menu = dict(menu)
            menu["main_menu"] = [
                {
                    "id": "shipment",
                    "name": "출고",
                    "url": url_for("erp_shipment_page.erp_shipment_dashboard"),
                },
                {
                    "id": "construction",
                    "name": "시공",
                    "url": url_for("erp_construction_page.erp_construction_dashboard"),
                },
            ]
    return {"menu": menu}


def register_context_processors(app) -> None:
    """Register all template filters and context processors on the Flask app."""
    app.add_template_filter(parse_json_string_filter, "parse_json_string")
    app.context_processor(inject_statuses)
    app.context_processor(inject_status_list)
    app.context_processor(utility_processor)
    app.context_processor(inject_menu)
