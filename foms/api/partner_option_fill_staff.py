"""단가표 전 협력사 주문 옵션 채우기 — 우리 CS JSON API(설계서 docs/specs/2026-11-03-partner-statement_SPEC.md 결정 12).

접두 ``/api/partner-statements`` (명세서 API 와 같은 접두 · 같은 권한):

- ``GET /fill`` 옵션 채울 주문 목록(단가표가 있는 협력사 주문 중 옵션 줄이 없는 품목이 남은 것).
- ``GET /orders/<order_id>/options`` 한 주문 — 품목마다 예전 글 칸 · 고를 목록(이름만).
- ``POST /orders/<order_id>/options`` 저장 ``{items: {품목 uid: {base, state, lines, customs}}}`` — 감사 한 줄.

ADMIN, 또는 CS 권한 팀의 STAFF · MANAGER 만(:func:`can_manage_statements` — 쓰기 정책 ``PARTNER_STATEMENT``).
응답은 ``{"success", "data", "error"}``.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from flask import Blueprint, g, jsonify, request
from sqlalchemy.exc import SQLAlchemyError

from db import get_db
from foms.services.partners.item_options import ItemOptionsError
from foms.services.partners.option_fill import fill_options, fill_rows, fill_view
from foms.services.partners.statements import can_manage_statements
from models import Order, SecurityLog

logger = logging.getLogger(__name__)

partner_option_fill_api_bp = Blueprint("partner_option_fill_api", __name__, url_prefix="/api/partner-statements")


def _ok(data: Any, status: int = 200):
    response = jsonify({"success": True, "data": data, "error": None})
    response.headers["Cache-Control"] = "private, no-store"
    return response, status


def _fail(status: int, error: str):
    return jsonify({"success": False, "data": None, "error": error}), status


def _staff() -> tuple[Optional[Any], Optional[tuple[Any, int]]]:
    user = getattr(g, "current_user", None)
    if user is None or getattr(user, "is_active", None) is False:
        return None, _fail(401, "로그인이 필요합니다.")
    if not can_manage_statements(user):
        return None, _fail(403, "CS 팀과 관리자만 쓸 수 있습니다.")
    return user, None


@partner_option_fill_api_bp.route("/fill", methods=["GET"], endpoint="fill_list")
def api_fill_list():
    """옵션 채울 주문 목록."""
    _actor, denied = _staff()
    if denied:
        return denied
    return _ok({"rows": fill_rows(get_db())})


@partner_option_fill_api_bp.route("/orders/<int:order_id>/options", methods=["GET"], endpoint="fill_get")
def api_fill_get(order_id: int):
    """한 주문 채우기 화면 값."""
    _actor, denied = _staff()
    if denied:
        return denied
    db = get_db()
    order = db.query(Order).filter(Order.id == order_id, Order.active_filter(), Order.partner_org_id.isnot(None)).first()
    if order is None:
        return _fail(404, "주문을 찾을 수 없습니다.")
    try:
        return _ok(fill_view(db, order))
    except ItemOptionsError as exc:
        return _fail(409, str(exc))


@partner_option_fill_api_bp.route("/orders/<int:order_id>/options", methods=["POST"], endpoint="fill_save")
def api_fill_save(order_id: int):
    """옵션 채우기 저장 — 생산 뒤 주문은 확정본까지(바로 발행 대기), 그 전은 협력사 도면 확인이 확정한다."""
    actor, denied = _staff()
    if denied:
        return denied
    body = request.get_json(silent=True)
    items = body.get("items") if isinstance(body, dict) else None
    db = get_db()
    exists = db.query(Order.id).filter(Order.id == order_id, Order.active_filter(), Order.partner_org_id.isnot(None)).first()
    if exists is None:
        return _fail(404, "주문을 찾을 수 없습니다.")
    try:
        result = fill_options(db, order_id, items, actor.id)
        order = result.pop("order")
        db.add(SecurityLog(user_id=actor.id, action="PARTNER_OPTIONS_FILLED", target_type="order", target_id=int(order.id),
                           message=f"협력사 주문 옵션을 CS 가 채움: {result['items']}개 품목"
                                   + (" (확정본까지)" if result["confirmed"] else ""),
                           detail={"order_id": order.id, "partner_org_id": order.partner_org_id, **result}))
        db.commit()
    except ItemOptionsError as exc:
        db.rollback()
        return _fail(409, str(exc))
    except SQLAlchemyError:
        db.rollback()
        logger.exception("[PARTNER_OPTION_FILL] 저장 실패 order=%s", order_id)
        return _fail(500, "저장하지 못했습니다. 잠시 뒤 다시 해 주세요.")
    return _ok(result)
