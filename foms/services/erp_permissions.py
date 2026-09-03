"""ERP Order edit-permission helpers and decorators."""

from __future__ import annotations

import json
import re
from functools import wraps
from typing import Any, Callable

from flask import jsonify, session

from foms.services.orders.order_mutation_policy import normalize_team, team_has_capability
from foms.web.auth import get_user_by_id

ERP_EDIT_ALLOWED_TEAMS = ("CS", "SALES")
_MINE_SCOPE_BY_TEAM = {
    "DRAWING": "drawing",
    "SALES": "sales",
    "MEASURE": "sales",
    "CS": "sales",
    "ACCOUNTING": "sales",  # 회계팀은 CS 와 같은 업무 범위(2026-09-03)
    "CONSTRUCTION": "construction",
}

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
        cast(expr, String).ilike(f"%{_escape_like(candidate)}%", escape="\\")  # perf-ok: ix_orders_structured_data_text_trgm
        for candidate in candidates
    ]
    return or_(*conditions) if len(conditions) > 1 else conditions[0]


def _json_string_token_condition(expr: Any, value: str, *, dialect_name: str) -> Any:
    """Match one complete JSON string value, including SQLite unicode escapes."""
    from sqlalchemy import String, cast, or_

    candidates = [f'"{value}"']
    if dialect_name == "sqlite":
        escaped_value = json.dumps(value, ensure_ascii=True)[1:-1]
        escaped_token = f'"{escaped_value}"'
        if escaped_token not in candidates:
            candidates.append(escaped_token)
    conditions = [
        cast(expr, String).ilike(  # perf-ok: ix_orders_structured_data_text_trgm
            f"%{_escape_like(candidate)}%",
            escape="\\",
        )
        for candidate in candidates
    ]
    return or_(*conditions) if len(conditions) > 1 else conditions[0]


def _json_int_array_condition(expr: Any, value: int) -> Any:
    """Match an integer JSON-array member without substring collisions (1 vs 10)."""
    from sqlalchemy import String, cast, or_

    text_expr = cast(expr, String)
    patterns = (
        f"%[{value}]%",
        f"%[{value},%",
        f"%, {value},%",
        f"%, {value}]%",
        f"%,{value},%",
        f"%,{value}]%",
    )
    return or_(*(text_expr.ilike(pattern, escape="\\") for pattern in patterns))  # perf-ok: ix_orders_sd_sales_ids_trgm


def resolve_mine_scope_for_user(user: Any) -> str:
    """Map the user's operational team to the matching ERP assignment domain."""
    if (getattr(user, "role", None) or "").strip().upper() == "ADMIN":
        return "all"
    team = (getattr(user, "team", None) or "").strip().upper()
    return _MINE_SCOPE_BY_TEAM.get(team, "all")


def _normalized_identity_values(user: Any) -> set[str]:
    values = set()
    for raw in (getattr(user, "name", None), getattr(user, "username", None)):
        value = str(raw or "").strip().lower()
        if value:
            values.add(value)
    return values


def _normalized_int_values(values: Any) -> set[int]:
    result = set()
    raw_values = values if isinstance(values, (list, tuple, set)) else [values]
    for raw in raw_values:
        if raw is None:
            continue
        try:
            result.add(int(raw))
        except (TypeError, ValueError):
            continue
    return result


def _assignment_names(values: Any) -> set[str]:
    names = set()
    raw_values = values if isinstance(values, (list, tuple, set)) else [values]
    for raw in raw_values:
        if raw is None:
            continue
        if isinstance(raw, dict):
            candidates = (raw.get("name"), raw.get("username"))
        else:
            candidates = (raw,)
        for candidate in candidates:
            value = str(candidate or "").strip().lower()
            if value:
                names.add(value)
    return names


def _assignment_ids(values: Any) -> set[int]:
    ids = set()
    raw_values = values if isinstance(values, (list, tuple, set)) else [values]
    for raw in raw_values:
        if not isinstance(raw, dict):
            continue
        ids.update(_normalized_int_values(raw.get("user_id", raw.get("id"))))
    return ids


def is_order_related_to_user(order: Any, user: Any, *, scope: str | None = None) -> bool:
    """Return whether an order is explicitly assigned to the user in the requested domain."""
    if not order or not user:
        return False

    identities = _normalized_identity_values(user)
    try:
        user_id = int(getattr(user, "id", None))
    except (TypeError, ValueError):
        user_id = None
    if not identities and user_id is None:
        return False

    structured_data = getattr(order, "structured_data", None)
    sd = structured_data if isinstance(structured_data, dict) else {}
    assignments = sd.get("assignments") if isinstance(sd.get("assignments"), dict) else {}
    parties = sd.get("parties") if isinstance(sd.get("parties"), dict) else {}
    workflow = sd.get("workflow") if isinstance(sd.get("workflow"), dict) else {}
    shipment = sd.get("shipment") if isinstance(sd.get("shipment"), dict) else {}
    manager = parties.get("manager") if isinstance(parties.get("manager"), dict) else {}
    current_quest = (
        workflow.get("current_quest")
        if isinstance(workflow.get("current_quest"), dict)
        else {}
    )

    manager_names = {
        str(getattr(order, "manager_name", None) or "").strip().lower(),
        str(manager.get("name") or "").strip().lower(),
        str(current_quest.get("owner_person") or "").strip().lower(),
    }
    manager_names.discard("")

    sales_ids = _normalized_int_values(assignments.get("sales_assignee_user_ids"))
    nested_drawing_assignees = assignments.get("drawing_assignees")
    top_level_drawing_assignees = sd.get("drawing_assignees")
    drawing_ids = _normalized_int_values(assignments.get("drawing_assignee_user_ids"))
    drawing_ids.update(_assignment_ids(nested_drawing_assignees))
    drawing_ids.update(_assignment_ids(top_level_drawing_assignees))
    drawing_names = _assignment_names(nested_drawing_assignees)
    drawing_names.update(_assignment_names(top_level_drawing_assignees))
    construction_names = _assignment_names(shipment.get("construction_workers"))

    manager_match = bool(identities & manager_names)
    sales_match = manager_match or (user_id is not None and user_id in sales_ids)
    drawing_match = bool(identities & drawing_names) or (
        user_id is not None and user_id in drawing_ids
    )
    construction_match = manager_match or bool(identities & construction_names)

    selected_scope = (scope or resolve_mine_scope_for_user(user)).strip().lower()
    matches = {
        "sales": sales_match,
        "drawing": drawing_match,
        "construction": construction_match,
        "all": sales_match or drawing_match or construction_match,
    }
    return matches.get(selected_scope, matches["all"])


def build_mine_sql_filter(user: Any, scope: str | None = None) -> list[Any]:
    """Return SQLAlchemy OR conditions for the user's ERP ownership filter.

    Args:
        user: 현재 사용자.
        scope: "내 항목"을 좁힐 이해관계자 역할. 생략하면 로그인 사용자의
            운영 팀에 맞는 역할을 사용한다.
            ``"all"`` — 모든 역할 union.
            ``"sales"`` — 영업 담당(소유자=manager/parties.manager/quest.owner_person
                + assignments.sales_assignee_user_ids).
            ``"construction"`` — 시공 담당(소유자=manager + shipment.construction_workers).
            ``"drawing"`` — 도면 담당(assignments/top-level drawing_assignees
                + drawing_assignee_user_ids).
                도면담당은 보통 영업(manager)과 다른 사람이라 manager는 제외한다.

    영업·시공은 담당자가 주문 manager로 기록되므로 소유자(manager) 신호를 포함한다.
    construction_workers는 외주 기사일 수 있어 단독으로는 본인 건을 누락(undercount)한다.
    새 역할 scope 추가 시 그 역할의 배정 필드가 manager인지 assignee인지 먼저 확인할 것.

    scope="all"은 기존 union 계약 보존: conds[0]은 manager_name ilike, 그룹 합산 개수 동일.
    """
    from sqlalchemy import and_

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
        manager_conds.append(Order.manager_name.ilike(safe, escape="\\"))  # perf-ok: ix_orders_manager_name_trgm
        manager_conds.append(_json_string_token_condition(Order.structured_data["parties"]["manager"]["name"], value, dialect_name=dialect_name))
        manager_conds.append(_json_string_token_condition(Order.structured_data["workflow"]["current_quest"]["owner_person"], value, dialect_name=dialect_name))
        construction_conds.append(_json_string_token_condition(Order.structured_data["shipment"]["construction_workers"], value, dialect_name=dialect_name))
        drawing_conds.append(_json_string_token_condition(Order.structured_data["assignments"]["drawing_assignees"], value, dialect_name=dialect_name))
        drawing_conds.append(
            and_(
                _json_like_condition(Order.structured_data, value, dialect_name=dialect_name),  # perf-ok: ix_orders_structured_data_text_trgm
                _json_string_token_condition(Order.structured_data["drawing_assignees"], value, dialect_name=dialect_name),
            )
        )

    if u_name:
        _add_name_group(u_name)
    if u_username and _escape_like(u_username) != _escape_like(u_name):
        _add_name_group(u_username)
    if u_id_str:
        user_id = int(u_id_str)
        sales_conds.append(_json_int_array_condition(Order.structured_data["assignments"]["sales_assignee_user_ids"], user_id))  # perf-ok: ix_orders_sd_sales_ids_trgm
        drawing_conds.append(_json_int_array_condition(Order.structured_data["assignments"]["drawing_assignee_user_ids"], user_id))  # perf-ok: ix_orders_sd_drawing_ids_trgm

    groups: dict[str, list[Any]] = {
        "sales": manager_conds + sales_conds,
        "construction": manager_conds + construction_conds,
        "drawing": drawing_conds,
        "all": manager_conds + sales_conds + drawing_conds + construction_conds,
    }
    selected_scope = (scope or resolve_mine_scope_for_user(user)).strip().lower()
    return groups.get(selected_scope, groups["all"])


def can_edit_erp(user: Any) -> bool:
    """Return whether the given user can edit ERP data.

    team 은 AUTH-01 정책 게이트와 **같은 정규화**(trim·upper·``MEASURE``→``SALES``)를
    거친다. 두 게이트가 갈라지면 team=``MEASURE`` 실측 담당자가 정책은 통과하고
    이 데코레이터에서만 403 을 맞는다.

    :param user: 대상 사용자(``role``·``team`` 속성).
    :return: ERP 수정 가능 여부.
    """
    if not user:
        return False
    if user.role == "ADMIN":
        return True
    return team_has_capability(getattr(user, "team", None), ERP_EDIT_ALLOWED_TEAMS)


def can_edit_erp_construction(user: Any) -> bool:
    """Return whether the user can edit construction-only ERP actions.

    :param user: 대상 사용자(``role``·``team`` 속성).
    :return: 시공 전용 ERP 액션 수정 가능 여부.
    """
    if not user:
        return False
    if user.role == "ADMIN":
        return True
    return normalize_team(getattr(user, "team", None)) == "CONSTRUCTION"


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
