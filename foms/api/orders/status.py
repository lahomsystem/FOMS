"""Status mutation handlers for the legacy orders blueprint."""

from __future__ import annotations

import datetime
from typing import Any, Callable

from flask import current_app, jsonify, request, session
from sqlalchemy.orm.attributes import flag_modified

from apps.auth import log_access
from constants import BULK_ACTION_STATUS, STATUS
from db import get_db
from foms.services.erp_display import get_today_kst
from foms.services.erp_sync_columns import sync_erp_flat_columns
from models import Order, OrderEvent


def update_order_status_response(
    *,
    get_today_kst_func: Callable[[], Any] = get_today_kst,
):
    """Handle the single-order status mutation."""
    db = get_db()
    try:
        data = request.get_json() or {}
        order_id = data.get("order_id")
        new_status = data.get("status")

        if not order_id or not new_status:
            return jsonify({"success": False, "message": "필수 파라미터가 누락되었습니다."}), 400
        if new_status not in STATUS:
            return jsonify({"success": False, "message": "유효하지 않은 상태입니다."}), 400

        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({"success": False, "message": "주문을 찾을 수 없습니다."}), 404

        old_status = getattr(order, "status", None) or ""
        order.status = new_status
        if new_status == "AS_RECEIVED" and not getattr(order, "as_received_date", None):
            setattr(order, "as_received_date", get_today_kst_func().strftime("%Y-%m-%d"))

        db.commit()

        user_id = session.get("user_id")
        old_status_name = STATUS.get(old_status, old_status)
        new_status_name = STATUS.get(new_status, new_status)
        log_access(f"주문 #{order_id} 상태 변경: {old_status_name} → {new_status_name}", user_id)

        return jsonify(
            {
                "success": True,
                "old_status": old_status,
                "new_status": new_status,
                "status_display": STATUS.get(new_status, new_status),
            }
        )
    except Exception as exc:
        db.rollback()
        current_app.logger.error(f"주문 상태 업데이트 실패: {str(exc)}")
        return (
            jsonify({"success": False, "message": f"오류 발생: {str(exc)}"}),
            500,
        )


def bulk_update_order_status_response(
    *,
    get_today_kst_func: Callable[[], Any] = get_today_kst,
):
    """Handle the bulk order-status mutation and ERP Beta workflow sync."""
    try:
        data = request.get_json() or {}
        order_ids = data.get("order_ids")
        new_status = (data.get("status") or "").strip()

        if not order_ids or not isinstance(order_ids, list):
            return jsonify({"success": False, "message": "order_ids(배열)가 필요합니다."}), 400
        if not new_status:
            return jsonify({"success": False, "message": "status가 필요합니다."}), 400

        is_delete = new_status == "DELETED"
        if not is_delete and new_status not in BULK_ACTION_STATUS:
            return jsonify({"success": False, "message": "유효한 status가 필요합니다."}), 400

        db = get_db()
        user_id = session.get("user_id")
        updated = 0
        deleted_at_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        valid_ids = []
        for order_id in order_ids:
            try:
                valid_ids.append(int(order_id))
            except (TypeError, ValueError):
                continue
        if not valid_ids:
            return jsonify({"success": False, "message": "유효한 주문 ID가 없습니다."}), 400

        orders = db.query(Order).filter(Order.id.in_(valid_ids)).all()
        for order in orders:
            old_status = getattr(order, "status", None) or ""
            if is_delete:
                setattr(order, "status", "DELETED")
                setattr(order, "original_status", old_status or "RECEIVED")
                setattr(order, "deleted_at", deleted_at_str)
                log_access(
                    f"주문 #{order.id} 휴지통 이동 (bulk): {old_status} → DELETED",
                    user_id,
                    auto_commit=False,
                )
                updated += 1
                continue

            setattr(order, "status", new_status)
            if new_status == "AS_RECEIVED" and not getattr(order, "as_received_date", None):
                setattr(order, "as_received_date", get_today_kst_func().strftime("%Y-%m-%d"))

            structured_data = getattr(order, "structured_data", None)
            if getattr(order, "is_erp_beta", False) and structured_data:
                if not isinstance(structured_data, dict):
                    continue
                workflow = structured_data.get("workflow") or {}
                old_stage = (workflow.get("stage") or "").strip()
                if new_status in STATUS:
                    workflow = dict(workflow)
                    workflow["stage"] = new_status
                    workflow["stage_updated_at"] = datetime.datetime.now().isoformat()
                    structured_data["workflow"] = workflow
                    setattr(order, "structured_data", structured_data)
                    flag_modified(order, "structured_data")
                    sync_erp_flat_columns(order, structured_data)
                db.add(
                    OrderEvent(
                        order_id=order.id,
                        event_type="STAGE_CHANGED",
                        payload={
                            "from": old_stage,
                            "to": new_status,
                            "manual": True,
                            "bulk": True,
                        },
                        created_by_user_id=user_id,
                    )
                )

            log_access(
                f"주문 #{order.id} 상태 변경: {old_status} → {new_status}",
                user_id,
                auto_commit=False,
            )
            updated += 1

        db.commit()
        return jsonify(
            {
                "success": True,
                "updated": updated,
                "new_status": new_status,
                "status_display": STATUS.get(new_status, new_status),
            }
        )
    except Exception as exc:
        db = get_db()
        if db:
            db.rollback()
        current_app.logger.error(f"bulk_update_order_status 실패: {str(exc)}")
        return (
            jsonify({"success": False, "message": f"오류 발생: {str(exc)}"}),
            500,
        )


__all__ = [
    "bulk_update_order_status_response",
    "update_order_status_response",
]
