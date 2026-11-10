"""협력사 주문 화면 영발 · 발주 PUSH JSON API(사용자 결정 2026-10-29).

* ``GET  /api/partner/orders/<id>/channel-push?kind=measurement|drawing`` — 변환(보낼 글 미리 보기) + 버튼 상태.
* ``POST /api/partner/orders/<id>/channel-push`` — ``kind`` · 재전송이면 ``change_note``.

글은 서버가 만든다(:func:`build_partner_push_text`) — 협력사가 고친 글을 보내지 않는다. 보내기는 ERP 와 같은
:func:`run_manual_push`(같은 방 · 같은 이력 칸 · 재전송 메모 · 동시 클릭 막기). 발주 PUSH 는 "이대로 만들어
주세요" 뒤에만 열고, 그 승인 직후 한 번은 :func:`auto_drawing_push` 가 자동으로 보낸다. 영발은 실측 예정(MEASURE)
에서 닫혀 있고 "실측 끝 · 도면 요청"(``POST .../request-drawing``) 직후 :func:`auto_measure_push` 가 한 번 보낸다
(사용자 2026-11-01 — docs/specs/2026-11-01-partner-measure-pending_SPEC.md).
5xx · 설정 오류 문구(환경변수 이름 · 예외 글)는 협력사에게 그대로 보이지 않는다.
스펙: docs/specs/2026-10-29-partner-channel-push_SPEC.md
"""
from __future__ import annotations

import logging
from typing import Any

from flask import Blueprint, g, jsonify, request

from db import get_db
from foms.api.channel.channel_integration import run_manual_push
from foms.api.notifications import invalidate_badge_cache_for_user_ids, resolve_notification_recipient_user_ids
from foms.services.auth.partner_scope import partner_can_read_order, partner_required
from foms.services.common.dashboard_cache import (
    DASHBOARD_FAMILY_DRAWING,
    DASHBOARD_FAMILY_ORDERS,
    invalidate_dashboard_families,
)
from foms.services.error_logging import log_handled_exception
from foms.services.orders.order_transition_service import TransitionError
from foms.services.orders.revision import RevisionError
from foms.services.partners.channel_push import (
    KINDS,
    MEASURE_DONE_NOTE,
    MEASURE_DONE_PREFIX,
    build_partner_push_text,
    push_state,
)
from foms.services.partners.drawing_request import PartnerDrawingRequestError, request_partner_drawing
from models import Order

logger = logging.getLogger(__name__)

partner_channel_push_bp = Blueprint("partner_channel_push", __name__, url_prefix="/api/partner")

_SEND_FAILED = "지금은 보내지 못했습니다. 잠시 뒤 다시 시도해 주세요."
AUTO_SENT_NOTE = "발주방에 도면을 보냈습니다."
AUTO_FAILED_NOTE = '발주방 전송은 실패했습니다. 주문 화면의 "발주 PUSH"로 다시 보내 주세요.'
AUTO_MEASURE_SENT_NOTE = "영발방에 보냈습니다."
AUTO_MEASURE_FAILED_NOTE = '영발방 전송은 실패했습니다. 주문 화면의 "영발 PUSH"로 다시 보내 주세요.'


def _fail(message: str, status: int):
    return jsonify({"success": False, "data": None, "error": message}), status


def _own_order(db, order_id: int) -> Order | None:
    order = db.query(Order).filter(Order.id == order_id, Order.active_filter()).first()
    return order if partner_can_read_order(g.current_user, order) else None


def _send(db, user: Any, order: Order, kind: str, change_note: str, prefix: str = "") -> tuple[bool, str, int]:
    """ERP 와 같은 보내기 한 건. 반환 (성공, 협력사에게 보일 문구, HTTP 상태)."""
    text = build_partner_push_text(order, prefix)
    body, status = run_manual_push(
        db,
        {"order_id": order.id, "text": text, "push_kind": kind, "change_note": change_note},
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


def _measure_before_drawing(db, user: Any, order: Order) -> str | None:
    """발주 전에 영발이 한 번도 안 나갔으면 영발방에 먼저 한 번(사용자 결정 2026-11-10 — 주문 5911 · 5891 은
    도면 단계로 바로 등록돼 영발 없이 발주만 나갔다). 실패해도 발주는 그대로 보낸다. 반환: 실패 안내(없으면 None)."""
    state = push_state(order)["measurement"]
    if state["pushed"] or not state["open"]:
        return None
    try:
        ok, _message, _status = _send(db, user, order, "measurement", "")
    except Exception:  # noqa: BLE001 - 발주는 그래도 보낸다
        db.rollback()
        log_handled_exception("partner auto measure before drawing push")
        ok = False
    if ok:
        db.refresh(order)
        return None
    return AUTO_MEASURE_FAILED_NOTE


def auto_drawing_push(db, user: Any, order_id: int) -> str | None:
    """"이대로 만들어 주세요" 직후 발주 PUSH 한 번(이미 보냈으면 안 보낸다). 영발이 한 번도 안 나간 주문이면
    영발방에 먼저 보낸다(:func:`_measure_before_drawing`). 승인은 이미 commit 됐다 — 여기서 실패해도 승인을
    되돌리지 않고 협력사에게 다시 보내라고 알린다. 반환: 화면에 보일 한 줄(없으면 None).
    """
    try:
        order = db.query(Order).filter(Order.id == order_id, Order.active_filter()).first()
        if order is None:
            return None
        state = push_state(order)["drawing"]
        if state["pushed"] or not state["open"]:
            return None
        measure_note = _measure_before_drawing(db, user, order)
        if measure_note:
            order = db.query(Order).filter(Order.id == order_id, Order.active_filter()).first()
            if order is None:
                return measure_note
        ok, _message, _status = _send(db, user, order, "drawing", "")
        note = AUTO_SENT_NOTE if ok else AUTO_FAILED_NOTE
        return f"{measure_note}\n{note}" if measure_note else note
    except Exception:  # noqa: BLE001 - 승인은 끝났다, 전송 실패만 알린다
        db.rollback()
        log_handled_exception("partner auto drawing push")
        return AUTO_FAILED_NOTE


def auto_measure_push(db, user: Any, order_id: int) -> str | None:
    """도면 요청 직후 영발 PUSH 한 번. 실측 예정 때 빈 영발이 먼저 나갔으면 재전송으로 — 첫 줄 "[실측 완료]" ·
    재전송 메모를 붙여 영발방에서 앞의 빈 글과 가른다. 실패해도 단계는 되돌리지 않는다. 반환: 화면에 보일 한 줄.
    """
    try:
        order = db.query(Order).filter(Order.id == order_id, Order.active_filter()).first()
        if order is None:
            return None
        state = push_state(order)["measurement"]
        if not state["open"]:
            return None
        resend = state["pushed"]
        ok, _message, _status = _send(db, user, order, "measurement", MEASURE_DONE_NOTE if resend else "",
                                      MEASURE_DONE_PREFIX if resend else "")
        return AUTO_MEASURE_SENT_NOTE if ok else AUTO_MEASURE_FAILED_NOTE
    except Exception:  # noqa: BLE001 - 도면 요청은 끝났다, 전송 실패만 알린다
        db.rollback()
        log_handled_exception("partner auto measure push")
        return AUTO_MEASURE_FAILED_NOTE


@partner_channel_push_bp.route("/orders/<int:order_id>/request-drawing", methods=["POST"])
@partner_required
def request_drawing(order_id: int):
    """"실측 끝 · 도면 요청" — 실측 예정 → 도면 단계(:func:`request_partner_drawing`), 그 뒤 영발 한 번."""
    db = get_db()
    try:
        request_partner_drawing(db, g.current_user, order_id)
        db.commit()
    except PartnerDrawingRequestError as exc:
        db.rollback()
        return jsonify({"success": False, "data": {"missing": exc.missing}, "error": str(exc)}), exc.status
    except (TransitionError, RevisionError):
        db.rollback()
        log_handled_exception("partner drawing request transition")
        return _fail("지금은 처리할 수 없습니다. 화면을 새로고침한 뒤 다시 시도해 주세요.", 409)
    invalidate_dashboard_families(DASHBOARD_FAMILY_ORDERS, DASHBOARD_FAMILY_DRAWING)
    for team in ("DRAWING", "CS"):
        invalidate_badge_cache_for_user_ids(resolve_notification_recipient_user_ids(
            db, target_team=team, target_manager_name=None, include_admin=False))
    push_note = auto_measure_push(db, g.current_user, order_id)
    return jsonify({"success": True, "data": {"order_id": order_id, "push_note": push_note}, "error": None})
