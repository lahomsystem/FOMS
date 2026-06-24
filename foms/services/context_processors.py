"""Flask context processors and template filters."""

from __future__ import annotations

import json
from typing import Any

from flask import g, request, session, url_for

from foms.services.feature_flags import (
    env_bool,
    env_bool_or_mobile_v2,
    is_enabled_for_user,
    should_render_new_order_wizard,
    wizard_new_order_enabled,
)
from foms.services.datetime_kst import format_datetime_kst
from foms.services.dashboard_counts import get_nav_badge_counts
from foms.services.common.erp_mine_filter import erp_mine_only_from_request
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
    "inject_foms_flags",
    "inject_foms_nav_badges",
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

    erp_order_enabled = env_bool("ERP_ORDER_ENABLED", default=True)
    uid = current_user.id if current_user else None
    erp_mobile_v2_enabled = is_enabled_for_user(
        "ERP_MOBILE_V2_ENABLED",
        uid,
        cohort_key="FOMS_V3_SHELL_COHORT",
    )
    use_direct_upload_env = env_bool("USE_DIRECT_UPLOAD", default=True)
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
                {
                    "id": "completion",
                    "name": "완료",
                    "url": url_for("erp_completion_page.erp_completion_dashboard"),
                },
                {
                    "id": "history",
                    "name": "이력",
                    "url": url_for("erp_history.history_dashboard"),
                },
            ]
    return {"menu": menu}


def inject_foms_flags() -> dict[str, Any]:
    """Inject v1.1 design feature flags for template cohort rollout."""
    current_user = getattr(g, "current_user", None)
    uid = current_user.id if current_user else None
    mobile_v2 = is_enabled_for_user(
        "ERP_MOBILE_V2_ENABLED",
        uid,
        cohort_key="FOMS_V3_SHELL_COHORT",
    )
    split_flag = env_bool_or_mobile_v2(
        "FOMS_TABLET_SPLIT_VIEW_ENABLED",
        mobile_v2_active=mobile_v2,
    )
    show_new_order_wizard = (
        request.endpoint == "order_pages.add_order"
        and should_render_new_order_wizard(uid, request)
    )
    return {
        "flag_mobile_v2": mobile_v2,
        "flag_tokens_v2": env_bool("FOMS_DESIGN_TOKENS_V2_ENABLED", True),
        # wizard draft/API 활성(코호트·전역 플래그). 실제 /add 렌더·chrome 숨김은 show_new_order_wizard.
        "flag_wizard": wizard_new_order_enabled(uid),
        "show_new_order_wizard": show_new_order_wizard,
        "flag_inline": env_bool("FOMS_INLINE_EDIT_ENABLED"),
        # 현장 스펙 즉시견적(ERP order 안에서 WDC 가격엔진 재사용). 기본 on,
        # 비활성화하려면 FOMS_ERP_SPEC_CALC_ENABLED=false.
        "flag_spec_calc": env_bool("FOMS_ERP_SPEC_CALC_ENABLED", True),
        "flag_split_view": split_flag,
        "foms_split_enabled": mobile_v2 and split_flag,
        "flag_rum_baseline": env_bool("FOMS_RUM_BASELINE_ENABLED", True),
        "flag_offline_sw": env_bool("FOMS_OFFLINE_SW_ENABLED"),
        "flag_bottom_nav_htmx": env_bool("FOMS_BOTTOM_NAV_HTMX_ENABLED"),
    }


def inject_foms_nav_badges() -> dict[str, Any]:
    """Inject bottom-nav stage badge counts (P1-01, ERP mobile v2 cohort only)."""
    current_user = getattr(g, "current_user", None)
    uid = current_user.id if current_user else None
    if not is_enabled_for_user(
        "ERP_MOBILE_V2_ENABLED",
        uid,
        cohort_key="FOMS_V3_SHELL_COHORT",
    ):
        return {"foms_nav_badges": {}}
    request_mine = erp_mine_only_from_request(request)
    return {
        "foms_nav_badges": get_nav_badge_counts(
            current_user,
            mine_only=True if request_mine else None,
        )
    }


def register_context_processors(app) -> None:
    """Register all template filters and context processors on the Flask app."""
    app.add_template_filter(parse_json_string_filter, "parse_json_string")
    app.add_template_filter(format_datetime_kst, "format_datetime_kst")
    app.context_processor(inject_statuses)
    app.context_processor(inject_status_list)
    app.context_processor(utility_processor)
    app.context_processor(inject_menu)
    app.context_processor(inject_foms_flags)
    app.context_processor(inject_foms_nav_badges)
