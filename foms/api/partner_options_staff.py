"""협력사 주문 옵션 — 우리 직원 읽기 API(설계서 docs/specs/2026-11-03-partner-statement_SPEC.md §5.3 — 3단계).

``GET /api/orders/<id>/partner-options`` → 도면 작업실 "도면 전달" 창이 품목마다 협력사가 고른 옵션(지금 값) · 원문과
달라진 것 · 고를 목록(이름 · 단위, 금액 없음)을 그린다. 고친 값은 전달 요청(``/transfer-drawing`` 의 ``partner_options``)에
실려 전달 쓰기와 같은 트랜잭션으로 저장된다(:func:`foms.services.partners.item_options.prepare_review_options`).

로그인한 우리 직원만(협력사 계정은 문지기 허용 목록에 없어 막힌다 · 여기서도 403). 협력사 주문이 아니거나 옵션 줄이 없으면
``data: null``. 읽기 전용이라 쓰기 정책 · CSRF 목록 대상이 아니다.
"""
from __future__ import annotations

from flask import Blueprint, g, jsonify

from db import get_db
from foms.services.partners.item_options import option_review
from models import Order

partner_options_staff_api_bp = Blueprint("partner_options_staff_api", __name__)


@partner_options_staff_api_bp.route("/api/orders/<int:order_id>/partner-options", methods=["GET"],
                                    endpoint="order_partner_options")
def api_order_partner_options(order_id: int):
    """품목마다 협력사 옵션(지금 값 · 원문과 달라진 것) + 고를 목록."""
    user = getattr(g, "current_user", None)
    if user is None or getattr(user, "is_active", None) is False:
        return jsonify({"success": False, "data": None, "error": "로그인이 필요합니다."}), 401
    if getattr(user, "partner_org_id", None) is not None:
        return jsonify({"success": False, "data": None, "error": "직원 전용입니다."}), 403
    db = get_db()
    order = db.query(Order).filter(Order.id == order_id, Order.active_filter()).first()
    if order is None:
        return jsonify({"success": False, "data": None, "error": "주문을 찾을 수 없습니다."}), 404
    data = option_review(db, order) if order.partner_org_id else None
    response = jsonify({"success": True, "data": data, "error": None})
    response.headers["Cache-Control"] = "private, no-store"
    return response
