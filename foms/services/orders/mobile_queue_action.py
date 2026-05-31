"""Mobile queue swipe action helpers (P3-03)."""

from __future__ import annotations

import datetime
from typing import Any

from foms.services.common.dashboard_cache import invalidate_all_dashboard_slice_caches
from foms.services.erp_policy import get_stage
from foms.services.orders.status_constants import STATUS
from models import Order

_HOLD_BLOCKED = frozenset({"ON_HOLD", "COMPLETED", "DELETED", "AS_COMPLETED"})


def apply_queue_hold(db: Any, order: Order, user_id: int | None) -> tuple[dict[str, Any], int]:
    """Set order status to ON_HOLD (same semantics as legacy status API).

    Args:
        db: SQLAlchemy session.
        order: Target order row.
        user_id: Acting user id for audit logging.

    Returns:
        Tuple of JSON-serializable body and HTTP status code.
    """
    from foms.web.auth import log_access

    current = (order.status or "").strip()
    if current == "ON_HOLD":
        return (
            {
                "success": True,
                "data": {"order_id": order.id, "action": "hold", "new_status": "ON_HOLD"},
            },
            200,
        )
    if current in _HOLD_BLOCKED - {"ON_HOLD"}:
        return {"success": False, "error": "hold not allowed for current status"}, 400
    if current and current not in STATUS:
        return {"success": False, "error": "invalid current status"}, 400

    order.status = "ON_HOLD"
    if hasattr(order, "updated_at"):
        order.updated_at = datetime.datetime.now()
    db.commit()
    invalidate_all_dashboard_slice_caches()
    log_access(
        f"모바일 큐 swipe hold — 주문 #{order.id} ({order.customer_name}) → ON_HOLD",
        user_id,
    )
    return (
        {
            "success": True,
            "data": {"order_id": order.id, "action": "hold", "new_status": "ON_HOLD"},
        },
        200,
    )


def build_swipe_quest_approve_payload(order: Order) -> tuple[dict[str, Any] | None, str | None]:
    """Build quest approve JSON for swipe shortcut.

    Args:
        order: Order with structured_data quests.

    Returns:
        ``(payload, None)`` on success, or ``(None, error_message)`` when approve cannot run.
    """
    from foms.services.erp_policy import STAGE_NAME_TO_CODE
    from foms.services.orders.erp_policy_quests import check_quest_approvals_complete

    sd = order.structured_data if isinstance(order.structured_data, dict) else {}
    stage_code = get_stage(sd)
    if not stage_code:
        return None, "no stage"
    if stage_code == "DRAWING":
        return None, "drawing quest approve disabled"

    code_to_name = {value: key for key, value in STAGE_NAME_TO_CODE.items()}
    stage_name = code_to_name.get(stage_code, stage_code)

    quests = sd.get("quests") or []
    current_quest: dict[str, Any] | None = None
    for quest in quests:
        if not isinstance(quest, dict):
            continue
        quest_stage = quest.get("stage")
        if quest_stage in (stage_name, stage_code):
            current_quest = quest
            break

    if current_quest is None:
        return None, "quest not found"

    approval_mode = current_quest.get("approval_mode", "team")
    if approval_mode == "assignee":
        return {}, None

    _complete, missing_teams = check_quest_approvals_complete(sd, stage_name)
    if not missing_teams:
        return None, "no pending team approval"
    return {"team": missing_teams[0]}, None
