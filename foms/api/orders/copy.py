"""Order copy API handlers (ORDER-COPY-01)."""

from __future__ import annotations

from typing import Optional

from flask import current_app, jsonify, request, session

from db import get_db
from foms.services.common.dashboard_cache import invalidate_all_dashboard_slice_caches
from foms.services.order_copy import OrderCopyError, copy_orders_batch
from foms.services.orders.order_create import OrderCreateError
from foms.web.auth import get_user_by_id, log_access


def _valid_order_ids(raw_order_ids) -> list[int]:
    """요청 order_ids 를 정수 목록으로 정규화한다(중복·비정수 제거, 입력 순서 보존)."""
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


def _requested_owner_user_id(data: dict) -> Optional[int]:
    """요청 body 의 ``owner_user_id`` (Admin/Manager 가 지정하는 SALES owner)를 파싱한다.

    STAFF 는 self owner 로 생성되므로 생략 가능하다(None). 값이 있으나 정수가 아니면
    :class:`OrderCreateError` 로 400 매핑한다.
    """
    raw = data.get("owner_user_id")
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise OrderCreateError("owner_user_id 는 정수여야 합니다.") from exc


def copy_orders_response():
    """선택 주문을 fresh identity 새 주문으로 복사한다(all-or-none, create_order 경유)."""
    db = get_db()
    try:
        data = request.get_json() or {}
        order_ids = _valid_order_ids(data.get("order_ids"))
        if not order_ids:
            return jsonify({"success": False, "message": "복사할 주문을 선택하세요."}), 400

        actor = get_user_by_id(session.get("user_id"))
        if actor is None:
            return jsonify({"success": False, "message": "로그인이 필요합니다."}), 401

        copied = copy_orders_batch(
            db,
            actor=actor,
            order_ids=order_ids,
            requested_owner_user_id=_requested_owner_user_id(data),
        )
        for original_id, new_order in copied:
            log_access(
                f"주문 #{original_id}를 새 주문 #{new_order.id}로 복사",
                actor.id,
                auto_commit=False,
            )
        db.commit()

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
                "copied": len(copied),
                "orders": [
                    {"original_order_id": original_id, "new_order_id": new_order.id}
                    for original_id, new_order in copied
                ],
            }
        )
    except OrderCopyError as exc:
        db.rollback()
        return jsonify({"success": False, "message": str(exc)}), exc.status_code
    except OrderCreateError as exc:
        db.rollback()
        return jsonify({"success": False, "message": str(exc)}), exc.status_code
    except Exception as exc:
        db.rollback()
        current_app.logger.error("copy_orders 실패: %s", exc, exc_info=True)
        return jsonify({"success": False, "message": f"오류 발생: {exc}"}), 500


__all__ = ["copy_orders_response"]
