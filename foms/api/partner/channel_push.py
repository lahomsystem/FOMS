"""협력사 주문 화면 영발 · 발주 PUSH JSON API(사용자 결정 2026-10-29).

* ``GET  /api/partner/orders/<id>/channel-push?kind=measurement|drawing`` — 변환(보낼 글 미리 보기) + 버튼 상태.
* ``POST /api/partner/orders/<id>/channel-push`` — ``kind`` · 재전송이면 ``change_note``.

글은 서버가 만든다(:func:`build_partner_push_text`) — 협력사가 고친 글을 보내지 않는다. 보내기는 ERP 와 같은
:func:`run_manual_push`(같은 방 · 같은 이력 칸 · 재전송 메모 · 동시 클릭 막기). 발주 PUSH 는 "이대로 만들어
주세요" 뒤에만 열고, 그 승인 직후 한 번은 :func:`auto_drawing_push` 가 자동으로 보낸다.
5xx · 설정 오류 문구(환경변수 이름 · 예외 글)는 협력사에게 그대로 보이지 않는다.
스펙: docs/specs/2026-10-29-partner-channel-push_SPEC.md
"""
from __future__ import annotations

import logging
from typing import Any

from flask import Blueprint, g, jsonify, request

from db import get_db
from foms.api.channel.channel_integration import run_manual_push
from foms.services.auth.partner_scope import partner_can_read_order, partner_required
from foms.services.error_logging import log_handled_exception
from foms.services.partners.channel_push import KINDS, build_partner_push_text, push_state
from models import Order

logger = logging.getLogger(__name__)

partner_channel_push_bp = Blueprint("partner_channel_push", __name__, url_prefix="/api/partner")

_SEND_FAILED = "지금은 보내지 못했습니다. 잠시 뒤 다시 시도해 주세요."
AUTO_SENT_NOTE = "발주방에 도면을 보냈습니다."
AUTO_FAILED_NOTE = '발주방 전송은 실패했습니다. 주문 화면의 "발주 PUSH"로 다시 보내 주세요.'


def _fail(message: str, status: int):
    return jsonify({"success": False, "data": None, "error": message}), status


def _own_order(db, order_id: int) -> Order | None:
    order = db.query(Order).filter(Order.id == order_id, Order.active_filter()).first()
    return order if partner_can_read_order(g.current_user, order) else None


def _send(db, user: Any, order: Order, kind: str, change_note: str) -> tuple[bool, str, int]:
    """ERP 와 같은 보내기 한 건. 반환 (성공, 협력사에게 보일 문구, HTTP 상태)."""
    body, status = run_manual_push(
        db,
        {"order_id": order.id, "text": build_partner_push_text(order), "push_kind": kind, "change_note": change_note},
        user,
        pushed_by_name=f"{user.name} (협력사)",
    )
    if body.get("success"):
        return True, "", 200
    db.rollback()
    if status >= 500 or status == 410:
        logger.error("[협력사 채널톡 PUSH] 실패 order=%s kind=%s status=%s msg=%s",
                     order.id, kind, status, body.get("message"))
        return False, _SEND_FAILED, 502
    return False, str(body.get("message") or body.get("error") or _SEND_FAILED), status


@partner_channel_push_bp.route("/orders/<int:order_id>/channel-push", methods=["GET"])
@partner_required
def preview_channel_push(order_id: int):
    """변환 — 보낼 글과 영발 · 발주 버튼 상태(보낸 적 · 시각 · 열림)."""
    db = get_db()
    order = _own_order(db, order_id)
    if order is None:
        return _fail("주문을 찾을 수 없습니다.", 404)
    return jsonify({"success": True, "data": {"text": build_partner_push_text(order), "state": push_state(order)},
                    "error": None})


@partner_channel_push_bp.route("/orders/<int:order_id>/channel-push", methods=["POST"])
@partner_required
def send_channel_push(order_id: int):
    """영발 · 발주 PUSH. 보낸 적 있으면 ``change_note``(바뀐 내용)가 있어야 한다."""
    db = get_db()
    order = _own_order(db, order_id)
    if order is None:
        return _fail("주문을 찾을 수 없습니다.", 404)
    payload = request.get_json(silent=True) or {}
    kind = str(payload.get("kind") or "")
    if kind not in KINDS:
        return _fail("보낼 곳(영발/발주)을 골라 주세요.", 400)
    state = push_state(order)[kind]
    if not state["open"]:
        return _fail(state["reason"], 409)
    ok, message, status = _send(db, g.current_user, order, kind, str(payload.get("change_note") or "").strip())
    if not ok:
        return _fail(message, status)
    db.refresh(order)
    return jsonify({"success": True, "data": {"state": push_state(order)}, "error": None})


def auto_drawing_push(db, user: Any, order_id: int) -> str | None:
    """"이대로 만들어 주세요" 직후 발주 PUSH 한 번(이미 보냈으면 안 보낸다). 승인은 이미 commit 됐다 —
    여기서 실패해도 승인을 되돌리지 않고 협력사에게 다시 보내라고 알린다. 반환: 화면에 보일 한 줄(없으면 None).
    """
    try:
        order = db.query(Order).filter(Order.id == order_id, Order.active_filter()).first()
        if order is None:
            return None
        state = push_state(order)["drawing"]
        if state["pushed"] or not state["open"]:
            return None
        ok, _message, _status = _send(db, user, order, "drawing", "")
        return AUTO_SENT_NOTE if ok else AUTO_FAILED_NOTE
    except Exception:  # noqa: BLE001 - 승인은 끝났다, 전송 실패만 알린다
        db.rollback()
        log_handled_exception("partner auto drawing push")
        return AUTO_FAILED_NOTE
