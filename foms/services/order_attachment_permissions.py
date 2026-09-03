"""Order attachment delete/modify permission helpers."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, or_

from foms.services.erp_permissions import is_order_related_to_user
from foms.services.orders.order_mutation_policy import normalize_team, team_has_capability

__all__ = [
    "can_delete_order_attachment",
    "can_manage_order_attachments",
    "can_modify_order_attachment",
    "can_reorder_order_attachments",
    "user_may_reorder_attachments",
]

#: 첨부 순서(sort_order)만 ADMIN 과 동일하게 연다. 삭제·item_index 는 기존 정책.
_REORDER_LIKE_ADMIN_ROLES = frozenset({"ADMIN", "MANAGER"})
_REORDER_LIKE_ADMIN_TEAMS = frozenset({"CS"})  # CS = 라홈팀/하우드팀


def _structured_data(order: Any) -> dict[str, Any]:
    raw = getattr(order, "structured_data", None)
    return raw if isinstance(raw, dict) else {}


def _collect_sales_manager_tokens(order: Any, sd: dict[str, Any]) -> set[str]:
    """Collect normalized manager identity tokens from order + structured_data."""
    parties = sd.get("parties") if isinstance(sd.get("parties"), dict) else {}
    manager = parties.get("manager") if isinstance(parties.get("manager"), dict) else {}
    workflow = sd.get("workflow") if isinstance(sd.get("workflow"), dict) else {}
    current_quest = (
        workflow.get("current_quest")
        if isinstance(workflow.get("current_quest"), dict)
        else {}
    )
    tokens: set[str] = set()
    for raw in (
        getattr(order, "manager_name", None),
        manager.get("name"),
        manager.get("user_id"),
        manager.get("id"),
        current_quest.get("owner_person"),
    ):
        value = str(raw or "").strip().lower()
        if value:
            tokens.add(value)
    return tokens


def _manager_id_token_matches(user: Any, order: Any, sd: dict[str, Any]) -> bool:
    """Match when manager fields store numeric user id as text."""
    try:
        current_user_id = int(getattr(user, "id", None))
    except (TypeError, ValueError):
        return False
    for token in _collect_sales_manager_tokens(order, sd):
        if token.isdigit() and int(token) == current_user_id:
            return True
    return False


def _manager_name_db_lookup_matches(user: Any, order: Any, sd: dict[str, Any]) -> bool:
    """Resolve manager display names to active users when assignee ids are absent."""
    assignments = sd.get("assignments") if isinstance(sd.get("assignments"), dict) else {}
    if assignments.get("sales_assignee_user_ids"):
        return False

    try:
        current_user_id = int(getattr(user, "id", None))
    except (TypeError, ValueError):
        return False

    name_tokens = {token for token in _collect_sales_manager_tokens(order, sd) if token and not token.isdigit()}
    if not name_tokens:
        return False

    try:
        from flask import has_app_context

        if not has_app_context():
            return False
    except ImportError:
        return False

    from db import get_db
    from models import User

    db = get_db()
    matched_ids = {
        row[0]
        for row in db.query(User.id)
        .filter(
            or_(
                func.lower(User.name).in_(name_tokens),
                func.lower(User.username).in_(name_tokens),
            )
        )
        .all()
    }
    return current_user_id in matched_ids


def can_manage_order_attachments(user: Any, order: Any) -> bool:
    """Return whether the user may manage all attachments on the order (담당자/관리자)."""
    if not user or not order:
        return False
    if getattr(user, "role", None) == "ADMIN":
        return True

    sd = _structured_data(order)
    if is_order_related_to_user(order, user, scope="sales"):
        return True

    from foms.services.erp_display import _can_modify_sales_domain

    if _can_modify_sales_domain(user, order, sd):
        return True
    if _manager_id_token_matches(user, order, sd):
        return True
    return _manager_name_db_lookup_matches(user, order, sd)


def can_delete_order_attachment(user: Any, order: Any, attachment: Any) -> bool:
    """Return whether the user may delete an attachment on the given order."""
    if not user or not order or not attachment:
        return False
    if can_manage_order_attachments(user, order):
        return True

    try:
        current_user_id = int(getattr(user, "id", None))
    except (TypeError, ValueError):
        current_user_id = None

    attachment_user_id = getattr(attachment, "user_id", None)
    return (
        current_user_id is not None
        and attachment_user_id is not None
        and attachment_user_id == current_user_id
    )


def can_modify_order_attachment(user: Any, order: Any, attachment: Any) -> bool:
    """Return whether the user may modify attachment metadata (e.g. item_index)."""
    return can_delete_order_attachment(user, order, attachment)


def can_reorder_order_attachments(user: Any, order: Any) -> bool:
    """첨부 순서를 ADMIN 과 같이 바꿀 수 있는지(역할·CS 팀·주문 담당자).

    Args:
        user: 현재 사용자.
        order: 대상 주문.

    Returns:
        ADMIN·MANAGER·CS(라홈/하우드) 또는 주문 영업 담당자면 True.
    """
    if not user or not order:
        return False
    role = (getattr(user, "role", None) or "").strip().upper()
    if role == "VIEWER":
        return False
    if role in _REORDER_LIKE_ADMIN_ROLES:
        return True
    if team_has_capability(getattr(user, "team", None), _REORDER_LIKE_ADMIN_TEAMS):
        return True
    return can_manage_order_attachments(user, order)


def user_may_reorder_attachments(user: Any, order: Any, attachments: Any) -> bool:
    """기록 그룹 전체 순서 저장. 팀 권한이 없으면 파일별 수정 권한으로 폴백.

    Args:
        user: 현재 사용자.
        order: 대상 주문.
        attachments: 그 그룹의 살아 있는 첨부 iterable.

    Returns:
        부분 저장 없이 전건 허용이면 True.
    """
    if can_reorder_order_attachments(user, order):
        return True
    live = list(attachments or ())
    if not live:
        return False
    return all(can_modify_order_attachment(user, order, att) for att in live)
