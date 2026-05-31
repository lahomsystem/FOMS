"""P3-03: Mobile queue card swipe actions API."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from flask import Blueprint, jsonify, request, session

from db import get_db
from foms.services.orders.mobile_queue_action import apply_queue_hold, build_swipe_quest_approve_payload
from foms.web.auth import get_user_by_id, login_required, log_access, role_required
from models import Order

foms_queue_actions_bp = Blueprint("foms_queue_actions", __name__, url_prefix="/api/foms/queue")


@foms_queue_actions_bp.route("/<int:order_id>/action", methods=["POST"])
@login_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def queue_card_action(order_id: int) -> tuple[Any, int]:
    """
    Handle mobile queue swipe actions (approve / hold).

    Body JSON: ``{"action": "approve"|"hold"}``
    """
    payload = request.get_json(silent=True) or {}
    action = (payload.get("action") or "").strip().lower()
    if action not in {"approve", "hold"}:
        return jsonify({"success": False, "error": "invalid action"}), 400

    db = get_db()
    order = db.query(Order).filter(Order.id == order_id, Order.not_deleted_filter()).first()
    if order is None:
        return jsonify({"success": False, "error": "order not found"}), 404

    user = get_user_by_id(session.get("user_id"))
    user_name = user.name if user else "Unknown"
    log_access(
        f"모바일 큐 swipe {action} — 주문 #{order_id} ({order.customer_name}) — {user_name}",
        session.get("user_id"),
    )

    if action == "hold":
        body, status = apply_queue_hold(db, order, session.get("user_id"))
        return jsonify(body), status

    approve_payload, err = build_swipe_quest_approve_payload(order)
    if err:
        return jsonify({"success": False, "error": err}), 400

    from foms.api.quest import api_order_quest_approve

    with patch.object(request, "get_json", return_value=approve_payload):
        return api_order_quest_approve(order_id)
