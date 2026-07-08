"""Order copy API handlers."""

from __future__ import annotations

from flask import current_app, jsonify, request, session

from db import get_db
from foms.services.common.dashboard_cache import invalidate_all_dashboard_slice_caches
from foms.services.jobs.queue import enqueue_geocode_order_address
from foms.services.order_copy import copy_order_as_new
from foms.web.auth import log_access
from models import Order


def _valid_order_ids(raw_order_ids) -> list[int]:
    valid_ids: list[int] = []
    seen: set[int] = set()
    if not isinstance(raw_order_ids, list):
        return valid_ids
    for raw_order_id in raw_order_ids:
        try:
            order_id = int(raw_order_id)
        except (TypeError, ValueError):
            continue
        if order_id in seen:
            continue
        seen.add(order_id)
        valid_ids.append(order_id)
    return valid_ids


def copy_orders_response():
    """Copy selected orders into new order rows with fresh DB order numbers."""
    db = get_db()
    try:
        data = request.get_json() or {}
        order_ids = _valid_order_ids(data.get("order_ids"))
        if not order_ids:
            return jsonify({"success": False, "message": "복사할 주문을 선택하세요."}), 400

        originals_by_id = {
            order.id: order
            for order in (
                db.query(Order)
                .filter(Order.id.in_(order_ids), Order.not_deleted_filter())
                .all()  # perf-ok: request bulk order id batch
            )
        }

        copied_orders = []
        failed_ids = []
        user_id = session.get("user_id")
        for order_id in order_ids:
            original_order = originals_by_id.get(order_id)
            if original_order is None:
                failed_ids.append(order_id)
                continue
            copied_order = copy_order_as_new(original_order)
            db.add(copied_order)
            db.flush()
            copied_orders.append(
                {
                    "original_order_id": original_order.id,
                    "new_order_id": copied_order.id,
                }
            )
            log_access(
                f"주문 #{original_order.id}를 새 주문 #{copied_order.id}로 복사",
                user_id,
                auto_commit=False,
            )

        if not copied_orders:
            db.rollback()
            return jsonify({"success": False, "message": "복사 가능한 주문이 없습니다."}), 404

        db.commit()

        for item in copied_orders:
            enqueue_geocode_order_address(item["new_order_id"])
        try:
            invalidate_all_dashboard_slice_caches()
        except Exception as cache_exc:
            current_app.logger.warning(
                "copy_orders dashboard cache invalidation failed: %s",
                cache_exc,
                exc_info=True,
            )

        return jsonify(
            {
                "success": True,
                "copied": len(copied_orders),
                "failed": len(failed_ids),
                "orders": copied_orders,
                "failed_order_ids": failed_ids,
            }
        )
    except Exception as exc:
        db.rollback()
        current_app.logger.error("copy_orders 실패: %s", exc, exc_info=True)
        return jsonify({"success": False, "message": f"오류 발생: {exc}"}), 500


__all__ = ["copy_orders_response"]
