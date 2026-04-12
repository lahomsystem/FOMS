"""Regional/self-measurement mutation handlers for the legacy orders blueprint."""

from __future__ import annotations

from flask import jsonify, request, session

from apps.auth import log_access
from db import get_db
from models import Order

REGIONAL_ALLOWED_FIELDS = [
    "measurement_completed",
    "regional_sales_order_upload",
    "regional_blueprint_sent",
    "regional_order_upload",
    "regional_cargo_sent",
    "regional_construction_info_sent",
]


def update_regional_status_response():
    """Update regional/self-measurement checklist fields."""
    db = get_db()
    data = request.get_json() or {}

    order_id = data.get("order_id")
    field = data.get("field")
    value = data.get("value")
    order = db.query(Order).filter_by(id=order_id).first()

    is_regional = getattr(order, "is_regional", False)
    is_self_measurement = getattr(order, "is_self_measurement", False)
    if not order or (not is_regional and not is_self_measurement):
        return jsonify({"success": False, "message": "유효하지 않은 주문입니다."}), 404

    if field not in REGIONAL_ALLOWED_FIELDS:
        return jsonify({"success": False, "message": "허용되지 않은 필드입니다."}), 400

    try:
        setattr(order, field, value)
        db.commit()
        order_type = "자가실측" if is_self_measurement else "지방 주문"
        log_access(
            f"{order_type} #{order.id}의 '{field}' 상태를 '{value}'(으)로 변경",
            session["user_id"],
        )
        return jsonify({"success": True, "message": "상태가 업데이트되었습니다."})
    except Exception as exc:
        db.rollback()
        return (
            jsonify({"success": False, "message": f"오류 발생: {str(exc)}"}),
            500,
        )


def update_regional_memo_response():
    """Update the legacy regional memo field."""
    db = get_db()
    data = request.get_json() or {}

    order_id = data.get("order_id")
    memo = data.get("memo", "")
    order = db.query(Order).filter_by(id=order_id).first()

    is_regional = getattr(order, "is_regional", False)
    is_self_measurement = getattr(order, "is_self_measurement", False)
    if not order or (not is_regional and not is_self_measurement):
        return jsonify({"success": False, "message": "유효하지 않은 주문입니다."}), 404

    try:
        order.regional_memo = memo
        db.commit()
        order_type = "자가실측" if is_self_measurement else "지방 주문"
        log_access(f"{order_type} #{order.id}의 메모를 업데이트", session["user_id"])
        return jsonify({"success": True, "message": "메모가 저장되었습니다."})
    except Exception as exc:
        db.rollback()
        return (
            jsonify({"success": False, "message": f"오류 발생: {str(exc)}"}),
            500,
        )


__all__ = [
    "REGIONAL_ALLOWED_FIELDS",
    "update_regional_memo_response",
    "update_regional_status_response",
]
