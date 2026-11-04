"""협력사 주문 지우기 JSON API(설계서 docs/specs/2026-11-04-partner-order-delete_SPEC.md).

* ``POST /api/partner/orders/<id>/delete`` ``{reason}`` — 자기 회사 주문을 휴지통으로("이대로 만들어 주세요" 전까지).

지우기 · 감사 · 팀 알림은 한 트랜잭션(:func:`delete_partner_order`), 커밋 뒤 대시보드 캐시를 모두 비우고
발주방에 짧은 글을 한 번 보낸다(실패해도 지우기는 그대로). 문지기 허용 목록 · 매니페스트(``PARTNER_PORTAL``)에 같이 있다.
"""
from __future__ import annotations

import logging

from flask import Blueprint, g, jsonify, request, url_for

from db import get_db
from foms.api.notifications import invalidate_badge_cache_for_user_ids, resolve_notification_recipient_user_ids
from foms.services.auth.partner_scope import partner_required
from foms.services.common.dashboard_cache import invalidate_dashboard_caches_after_delete_transition
from foms.services.orders.revision import RevisionError
from foms.services.partners.order_delete import PartnerDeleteError, delete_partner_order, send_channel_notice

logger = logging.getLogger(__name__)

partner_order_delete_bp = Blueprint("partner_order_delete", __name__, url_prefix="/api/partner")


def _fail(message: str, status: int):
    return jsonify({"success": False, "data": None, "error": message}), status


@partner_order_delete_bp.route("/orders/<int:order_id>/delete", methods=["POST"])
@partner_required
def delete_order(order_id: int):
    """자기 회사 주문 지우기 — 이유 한 줄 필수, 제작 요청 뒤는 409."""
    db = get_db()
    payload = request.get_json(silent=True) or {}
    try:
        info = delete_partner_order(db, g.current_user, order_id, payload.get("reason"))
        db.commit()
    except PartnerDeleteError as exc:
        db.rollback()
        return _fail(str(exc), exc.status)
    except RevisionError:
        db.rollback()
        return _fail("다른 사람이 먼저 고쳤습니다. 화면을 새로고침해 주세요.", 409)
    invalidate_dashboard_caches_after_delete_transition("partner_order_delete")
    invalidate_badge_cache_for_user_ids(resolve_notification_recipient_user_ids(
        db, target_team=info["team"], target_manager_name=None, include_admin=False))
    sent = send_channel_notice(info, g.current_user)
    return jsonify({"success": True, "data": {"order_id": order_id, "channel_sent": sent,
                                              "redirect": url_for("partner_portal.home")}, "error": None})
