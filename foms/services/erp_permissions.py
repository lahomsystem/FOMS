"""ERP Order edit-permission helpers and decorators."""

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


def build_mine_sql_filter(user: Any, scope: str = "all") -> list[Any]:
    """Return SQLAlchemy OR conditions for the user's ERP ownership filter.

    Args:
        user: 현재 사용자.
        scope: "내 항목"을 좁힐 이해관계자 역할.
            ``"all"`` (기본·기존 동작) — 모든 역할 union.
            ``"sales"`` — 영업 담당(소유자=manager/parties.manager/quest.owner_person
                + assignments.sales_assignee_user_ids).
            ``"construction"`` — 시공 담당(소유자=manager + shipment.construction_workers).
            ``"drawing"`` — 도면 담당(assignments.drawing_assignees + drawing_assignee_user_ids).
                도면담당은 보통 영업(manager)과 다른 사람이라 manager는 제외한다.

    영업·시공은 담당자가 주문 manager로 기록되므로 소유자(manager) 신호를 포함한다.
    construction_workers는 외주 기사일 수 있어 단독으로는 본인 건을 누락(undercount)한다.
    새 역할 scope 추가 시 그 역할의 배정 필드가 manager인지 assignee인지 먼저 확인할 것.

    scope="all"은 기존 계약 보존: conds[0]은 manager_name ilike, 그룹 합산 개수 동일.
    """
    from sqlalchemy import String, cast

    from foms.persistence.main.models import Order

    dialect_name = _current_dialect_name()
    u_name = (user.name or "").strip()
    u_username = (user.username or "").strip()
    u_id_str = str(user.id) if getattr(user, "id", None) else ""

    manager_conds: list[Any] = []  # 영업/소유자 (manager_name, parties.manager, quest.owner_person)
    sales_conds: list[Any] = []  # sales_assignee_user_ids (id)
    drawing_conds: list[Any] = []  # drawing_assignees(name) + drawing_assignee_user_ids(id)
    construction_conds: list[Any] = []  # shipment.construction_workers (name)

    def _add_name_group(value: str) -> None:
        safe = _escape_like(value)
        manager_conds.append(Order.manager_name.ilike(f"%{safe}%", escape="\\"))
        manager_conds.append(_json_like_condition(Order.structured_data["parties"]["manager"]["name"], value, dialect_name=dialect_name))
        manager_conds.append(_json_like_condition(Order.structured_data["workflow"]["current_quest"]["owner_person"], value, dialect_name=dialect_name))
        construction_conds.append(_json_like_condition(Order.structured_data["shipment"]["construction_workers"], value, dialect_name=dialect_name))
        drawing_conds.append(_json_like_condition(Order.structured_data["assignments"]["drawing_assignees"], value, dialect_name=dialect_name))

    if u_name:
        _add_name_group(u_name)
    if u_username and _escape_like(u_username) != _escape_like(u_name):
        _add_name_group(u_username)
    if u_id_str:
        sales_conds.append(cast(Order.structured_data["assignments"]["sales_assignee_user_ids"], String).ilike(f"%{u_id_str}%", escape="\\"))  # perf-ok: ix_orders_sd_sales_ids_trgm
        drawing_conds.append(cast(Order.structured_data["assignments"]["drawing_assignee_user_ids"], String).ilike(f"%{u_id_str}%", escape="\\"))  # perf-ok: ix_orders_sd_drawing_ids_trgm

    groups: dict[str, list[Any]] = {
        "sales": manager_conds + sales_conds,
        "construction": manager_conds + construction_conds,
        "drawing": drawing_conds,
        "all": manager_conds + sales_conds + drawing_conds + construction_conds,
    }
    return groups.get(scope, groups["all"])


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
    """ERP Order write-permission decorator."""

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
                        "message": "ERP Order 수정 권한이 없습니다. (관리자, 라홈팀, 하우드팀, 영업팀만 수정 가능)",
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
