"""Status mutation handlers for the legacy orders blueprint."""

from __future__ import annotations

import datetime
from typing import Any, Callable

from flask import current_app, jsonify, request, session
from sqlalchemy.orm.attributes import flag_modified

from foms.web.auth import log_access
from foms.services.orders.status_constants import BULK_ACTION_STATUS, STATUS
from foms.services.orders.stage_override import (
    OVERRIDE_BLOCK_MESSAGE,
    current_stage_for_order,
    requires_privileged_override,
)
from foms.services.erp_order_flags import is_erp_order_record
from db import get_db
from foms.services.datetime_kst import now_kst
from foms.services.erp_display import get_today_kst
from foms.services.erp_sync_columns import sync_erp_flat_columns
from models import Order, OrderEvent


def _sync_erp_stage(order: Order, new_status: str, user_id: Any, db: Any, *, bulk: bool) -> None:
    """ERP 주문의 workflow.stage 동기화 + STAGE_CHANGED 이벤트 기록 (단건/벌크 공용).

    비ERP 주문이나 structured_data 가 dict 가 아니면 아무것도 하지 않는다.
    bulk 핸들러의 기존 ERP 블록을 그대로 옮긴 것으로, workflow 는 dict() 셸
    복사 패턴을 유지한다(기존 동작 보존).

    :param order: status 가 이미 갱신된 주문 ORM 객체.
    :param new_status: 새 상태 코드(STATUS 키).
    :param user_id: STAGE_CHANGED 기록용 사용자 id(없으면 None).
    :param db: 활성 DB 세션(commit 은 호출부 소관).
    :param bulk: STAGE_CHANGED payload 의 bulk 플래그(단건 False, 벌크 True).
    """
    structured_data = getattr(order, "structured_data", None)
    if not (is_erp_order_record(order) and isinstance(structured_data, dict) and structured_data):
        return
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
                "bulk": bulk,
            },
            created_by_user_id=user_id,
        )
    )


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
        from_stage = current_stage_for_order(order)
        if is_erp_order_record(order) and requires_privileged_override(from_stage, new_status):
            return jsonify({"success": False, "message": OVERRIDE_BLOCK_MESSAGE}), 403

        user_id = session.get("user_id")
        order.status = new_status
        if new_status == "AS_RECEIVED" and not getattr(order, "as_received_date", None):
            setattr(order, "as_received_date", get_today_kst_func().strftime("%Y-%m-%d"))

        # ERP 주문이면 workflow.stage 동기화 + STAGE_CHANGED 기록 (bulk 핸들러와 동일 헬퍼).
        _sync_erp_stage(order, new_status, user_id, db, bulk=False)

        db.commit()

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
        blocked_override_required: list[int] = []
        deleted_at_str = now_kst().strftime("%Y-%m-%d %H:%M:%S")

        valid_ids = []
        for order_id in order_ids:
            try:
                valid_ids.append(int(order_id))
            except (TypeError, ValueError):
                continue
        if not valid_ids:
            return jsonify({"success": False, "message": "유효한 주문 ID가 없습니다."}), 400

        orders = db.query(Order).filter(Order.id.in_(valid_ids)).all()  # perf-ok: request bulk order id batch
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

            from_stage = current_stage_for_order(order)
            if is_erp_order_record(order) and requires_privileged_override(from_stage, new_status):
                blocked_override_required.append(int(order.id))
                continue

            setattr(order, "status", new_status)
            if new_status == "AS_RECEIVED" and not getattr(order, "as_received_date", None):
                setattr(order, "as_received_date", get_today_kst_func().strftime("%Y-%m-%d"))

            # 기존 동작 보존: ERP 주문의 dict 아닌 truthy sd 는 집계/로그 제외(continue).
            structured_data = getattr(order, "structured_data", None)
            if is_erp_order_record(order) and structured_data and not isinstance(structured_data, dict):
                continue
            _sync_erp_stage(order, new_status, user_id, db, bulk=True)

            log_access(
                f"주문 #{order.id} 상태 변경: {old_status} → {new_status}",
                user_id,
                auto_commit=False,
            )
            updated += 1

        db.commit()
        success = updated > 0 or not blocked_override_required
        message = None
        if blocked_override_required and updated == 0:
            success = False
            message = OVERRIDE_BLOCK_MESSAGE
        elif blocked_override_required:
            message = (
                f"{len(blocked_override_required)}건은 역행/건너뛰기로 차단됨. "
                "「단계 강제 변경」을 사용하세요."
            )
        payload: dict[str, Any] = {
            "success": success,
            "updated": updated,
            "new_status": new_status,
            "status_display": STATUS.get(new_status, new_status),
            "blocked_override_required": blocked_override_required,
        }
        if message:
            payload["message"] = message
        status_code = 200 if success else 403
        return jsonify(payload), status_code
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
