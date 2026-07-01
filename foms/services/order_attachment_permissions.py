"""Order attachment delete permission helpers."""

from __future__ import annotations

from typing import Any

from foms.services.erp_permissions import is_order_related_to_user

__all__ = ["can_delete_order_attachment", "can_manage_order_attachments"]


def can_manage_order_attachments(user: Any, order: Any) -> bool:
    """Return whether the user may manage all attachments on the order (담당자/관리자)."""
    if not user or not order:
        return False
    if getattr(user, "role", None) == "ADMIN":
        return True
    return is_order_related_to_user(order, user, scope="sales")


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
