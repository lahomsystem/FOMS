"""확정 뒤 품목 하나 취소 (DRAWING-PARTIAL-CONFIRM 6단계, 설계서 2026-10-12 §10).

``POST /api/orders/<id>/items/<uid>/cancel`` ``{reason, note}`` — 도면 확정 뒤에만.
품목은 지우지 않고 ``items[].cancel`` 을 붙이고, 그 품목에만 묶인 최종 도면은
``drawing_excluded_files`` 로 옮긴다. REV-00 :func:`execute_order_mutation` 한 transaction
(ERP_EDIT 정책 + If-Match + version bump + idempotency + OrderEvent).
"""
from __future__ import annotations

import copy
import hashlib
import json
import logging

from flask import Blueprint, g, jsonify, request
from sqlalchemy.orm.attributes import flag_modified

from db import get_db
from foms.services.common.dashboard_cache import (
    DASHBOARD_FAMILY_CONSTRUCTION,
    DASHBOARD_FAMILY_DRAWING,
    DASHBOARD_FAMILY_PRODUCTION,
    invalidate_order_dashboard_families,
)
from foms.services.datetime_kst import now_utc_naive
from foms.services.orders.drawing_confirm_partial import (
    CANCEL_SOURCE_AFTER_CONFIRM,
    PartialConfirmError,
    apply_partial_confirm,
    cancel_event_payload,
    plan_after_confirm_cancel,
)
from foms.services.orders.order_mutation_policy import POLICY_REGISTRY, evaluate_policy
from foms.services.orders.revision import RevisionError, execute_order_mutation
from models import Order, OrderEvent

logger = logging.getLogger(__name__)

ITEM_CANCEL_POLICY_ID = "ERP_EDIT"

erp_orders_item_cancel_bp = Blueprint('erp_orders_item_cancel', __name__, url_prefix='/api/orders')


def _hashes(order_id: int, uid: str, reason: str, note: str) -> tuple[str, str]:
    scope = hashlib.sha256(f"ITEM_CANCEL:{order_id}:{uid}".encode()).hexdigest()
    body = json.dumps({"uid": uid, "reason": reason, "note": note}, sort_keys=True, ensure_ascii=False)
    return scope, hashlib.sha256(body.encode()).hexdigest()


@erp_orders_item_cancel_bp.route('/<int:order_id>/items/<uid>/cancel', methods=['POST'])
def api_order_item_cancel_after_confirm(order_id: int, uid: str):
    """확정 뒤 품목 하나를 취소한다. 실패하면 아무것도 바꾸지 않는다."""
    # 사용자는 before_request(_set_current_user)가 읽어 둔 값 — 로그인 안 했으면 정책이 막는다.
    user = getattr(g, "current_user", None)
    if user is None:
        return jsonify({"success": False, "data": None, "error": "로그인이 필요해요."}), 401
    decision = evaluate_policy(POLICY_REGISTRY[ITEM_CANCEL_POLICY_ID], user)
    if not decision.allowed:
        return jsonify({"success": False, "data": None, "error": decision.reason, "code": decision.code}), decision.status

    payload = request.get_json(silent=True) or {}
    reason = str(payload.get("reason") or "").strip()
    note = str(payload.get("note") or "").strip()[:200]
    if_match = (request.headers.get("If-Match") or "").strip().strip('"')
    expected = {order_id: int(if_match)} if if_match.isdigit() else None
    idem = (request.headers.get("Idempotency-Key") or "").strip() or None
    scope_hash, request_hash = _hashes(order_id, uid, reason, note)
    captured: dict = {}

    def _mutate(sess, locked):
        order = locked[0]
        sd = copy.deepcopy(order.structured_data if isinstance(order.structured_data, dict) else {})
        plan = plan_after_confirm_cancel(sd, uid, reason, note)
        summary = apply_partial_confirm(sd, plan, actor_user_id=user.id, at_iso=now_utc_naive().isoformat(),
                                        source=CANCEL_SOURCE_AFTER_CONFIRM)
        order.structured_data = sd
        flag_modified(order, "structured_data")
        sess.add(OrderEvent(order_id=order.id, event_type="ITEM_CANCELLED_AFTER_CONFIRM",
                            payload=cancel_event_payload(plan, summary), created_by_user_id=user.id))
        captured["summary"] = summary
        return {order.id: [f"ORDER_DETAIL:{order.id}", "ORDERS_INDEX"]}

    db = get_db()
    try:
        execute_order_mutation(
            db, actor_user_id=user.id, policy_id=ITEM_CANCEL_POLICY_ID, order_ids=[order_id],
            expected_versions=expected, idempotency_key=idem,
            scope_hash=scope_hash, request_hash=request_hash, mutation=_mutate,
        )
        db.commit()
    except PartialConfirmError as exc:
        db.rollback()
        return jsonify({"success": False, "data": None, "error": str(exc), "code": exc.code}), 400
    except RevisionError as rev:
        db.rollback()
        return jsonify({"success": False, "data": None, "error": str(rev), "code": rev.error_code}), rev.status_code
    except Exception as exc:  # noqa: BLE001 - 롤백 후 500
        db.rollback()
        logger.exception("[ITEM_CANCEL] order %s: %s", order_id, exc)
        return jsonify({"success": False, "data": None, "error": "제품을 취소하지 못했어요."}), 500

    order = db.get(Order, order_id)
    if order is not None:
        invalidate_order_dashboard_families(
            order, extra=(DASHBOARD_FAMILY_DRAWING, DASHBOARD_FAMILY_PRODUCTION, DASHBOARD_FAMILY_CONSTRUCTION))
    return jsonify({"success": True, "data": captured.get("summary") or {}, "error": None})
