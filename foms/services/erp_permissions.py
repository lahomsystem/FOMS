"""ERP Beta edit-permission helpers and decorators."""

from __future__ import annotations

import json
import re
from functools import wraps
from typing import Any, Callable

from flask import jsonify, session

from foms.web.auth import get_user_by_id

ERP_EDIT_ALLOWED_TEAMS = ("CS", "SALES")

# LIKE 와일드카드 이스케이프 패턴 (PostgreSQL escape char = '\')
_LIKE_ESCAPE_RE = re.compile(r"([%_\\])")

__all__ = [
    "build_mine_sql_filter",
    "can_edit_erp",
    "can_edit_erp_construction",
    "erp_edit_required",
    "erp_construction_edit_required",
]


def _escape_like(value: str) -> str:
    """Escape wildcard characters in SQL LIKE patterns."""
    return _LIKE_ESCAPE_RE.sub(r"\\\1", value)


def _current_dialect_name() -> str:
    """Return the active SQLAlchemy dialect name when available."""
    try:
        from db import db_session

        bind = db_session.get_bind()
        return getattr(getattr(bind, "dialect", None), "name", "") or ""
    except Exception:
        return ""


def _json_like_condition(expr: Any, value: str, *, dialect_name: str) -> Any:
    """Build a JSON text match condition with SQLite unicode-escape fallback."""
    from sqlalchemy import String, cast, or_

    candidates = [value]
    if dialect_name == "sqlite":
        escaped_value = json.dumps(value, ensure_ascii=True)[1:-1]
        if escaped_value and escaped_value not in candidates:
            candidates.append(escaped_value)

    conditions = [
        cast(expr, String).ilike(f"%{_escape_like(candidate)}%", escape="\\")
        for candidate in candidates
    ]
    return or_(*conditions) if len(conditions) > 1 else conditions[0]


def build_mine_sql_filter(user: Any) -> list[Any]:
    """Return SQLAlchemy OR conditions for the current user's ERP ownership filter."""
    from sqlalchemy import String, cast

    from foms.persistence.main.models import Order

    conds: list[Any] = []
    dialect_name = _current_dialect_name()

    u_name = (user.name or "").strip()
    u_username = (user.username or "").strip()
    u_id_str = str(user.id) if getattr(user, "id", None) else ""

    if u_name:
        safe_name = _escape_like(u_name)
        conds.append(Order.manager_name.ilike(f"%{safe_name}%", escape="\\"))
        conds.append(_json_like_condition(Order.structured_data["parties"]["manager"]["name"], u_name, dialect_name=dialect_name))
        conds.append(_json_like_condition(Order.structured_data["workflow"]["current_quest"]["owner_person"], u_name, dialect_name=dialect_name))
        conds.append(_json_like_condition(Order.structured_data["shipment"]["construction_workers"], u_name, dialect_name=dialect_name))
        conds.append(_json_like_condition(Order.structured_data["assignments"]["drawing_assignees"], u_name, dialect_name=dialect_name))

    if u_username:
        safe_uname = _escape_like(u_username)
        if safe_uname != _escape_like(u_name):
            conds.append(Order.manager_name.ilike(f"%{safe_uname}%", escape="\\"))
            conds.append(_json_like_condition(Order.structured_data["parties"]["manager"]["name"], u_username, dialect_name=dialect_name))
            conds.append(_json_like_condition(Order.structured_data["workflow"]["current_quest"]["owner_person"], u_username, dialect_name=dialect_name))
            conds.append(_json_like_condition(Order.structured_data["shipment"]["construction_workers"], u_username, dialect_name=dialect_name))
            conds.append(_json_like_condition(Order.structured_data["assignments"]["drawing_assignees"], u_username, dialect_name=dialect_name))

    if u_id_str:
        conds.append(cast(Order.structured_data["assignments"]["sales_assignee_user_ids"], String).ilike(f"%{u_id_str}%", escape="\\"))
        conds.append(cast(Order.structured_data["assignments"]["drawing_assignee_user_ids"], String).ilike(f"%{u_id_str}%", escape="\\"))

    return conds


def can_edit_erp(user: Any) -> bool:
    """Return whether the given user can edit ERP data."""
    if not user:
        return False
    if user.role == "ADMIN":
        return True
    return (user.team or "").strip() in ERP_EDIT_ALLOWED_TEAMS


def can_edit_erp_construction(user: Any) -> bool:
    """Return whether the user can edit construction-only ERP actions."""
    if not user:
        return False
    if user.role == "ADMIN":
        return True
    return (user.team or "").strip() == "CONSTRUCTION"


def erp_edit_required(f: Callable[..., Any]) -> Callable[..., Any]:
    """ERP Beta write-permission decorator."""

    @wraps(f)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        user = get_user_by_id(session.get("user_id"))
        if not user:
            return jsonify({"success": False, "message": "로그인이 필요합니다."}), 401
        if not can_edit_erp(user):
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "ERP Beta 수정 권한이 없습니다. (관리자, 라홈팀, 하우드팀, 영업팀만 수정 가능)",
                    }
                ),
                403,
            )
        return f(*args, **kwargs)

    return wrapped


def erp_construction_edit_required(f: Callable[..., Any]) -> Callable[..., Any]:
    """Construction-only ERP write-permission decorator."""

    @wraps(f)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        user = get_user_by_id(session.get("user_id"))
        if not user:
            return jsonify({"success": False, "message": "로그인이 필요합니다."}), 401
        if can_edit_erp(user) or can_edit_erp_construction(user):
            return f(*args, **kwargs)
        return (
            jsonify(
                {
                    "success": False,
                    "message": "시공 시작/완료 권한이 없습니다. (관리자, 라홈팀, 영업팀 또는 시공팀만 가능)",
                }
            ),
            403,
        )

    return wrapped
