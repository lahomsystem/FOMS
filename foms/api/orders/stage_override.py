"""의도적 워크플로 단계 강제 변경 API (역행·건너뛰기)."""

from __future__ import annotations

from typing import Any

from flask import current_app, jsonify, request, session

from db import get_db
from foms.services.orders.stage_override import (
    OVERRIDE_ALLOWED_ROLES,
    apply_stage_override,
)
from foms.web.auth import log_access
from models import Order, User


def stage_override_response(order_id: int):
    """POST /api/orders/<id>/workflow/stage-override 핸들러."""
    db = get_db()
    try:
        user_id = session.get("user_id")
        user = db.query(User).filter(User.id == user_id).first() if user_id else None
        if not user:
            return jsonify({"success": False, "error": "로그인이 필요합니다."}), 401
        role = str(getattr(user, "role", "") or "").strip().upper()
        if role not in OVERRIDE_ALLOWED_ROLES:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "단계 강제 변경은 ADMIN/MANAGER만 가능합니다.",
                    }
                ),
                403,
            )

        data = request.get_json(silent=True) or {}
        if data.get("confirm") is not True:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "confirm: true 가 필요합니다.",
                    }
                ),
                400,
            )

        to_stage = data.get("to_stage")
        reason = data.get("reason")
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({"success": False, "error": "주문을 찾을 수 없습니다."}), 404

        try:
            payload = apply_stage_override(
                order=order,
                to_stage=str(to_stage or ""),
                reason=str(reason or ""),
                user_id=user_id,
                db=db,
            )
        except ValueError as exc:
            return jsonify({"success": False, "error": str(exc)}), 400

        db.commit()
        log_access(
            f"주문 #{order_id} 단계 강제 변경({payload['mode']}): "
            f"{payload['from']} → {payload['to']} ({payload['reason']})",
            user_id,
        )
        return jsonify(
            {
                "success": True,
                "data": {
                    "order_id": order_id,
                    "from": payload["from"],
                    "to": payload["to"],
                    "mode": payload["mode"],
                    "reason": payload["reason"],
                    "status": order.status,
                },
            }
        )
    except Exception as exc:
        db.rollback()
        current_app.logger.error("stage_override 실패: %s", exc, exc_info=True)
        return (
            jsonify({"success": False, "error": f"오류 발생: {exc}"}),
            500,
        )


__all__ = ["stage_override_response"]
