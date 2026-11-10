"""시공일 정하기 API — 출고 화면 협력사 희망 판 [확정] · 출고팀 주문 화면 시공일 칸.

설계서 ``docs/specs/2026-11-04-shipment-partner-request-board_SPEC.md`` §2.3 · §2.3-b.

* ``POST /api/erp/shipment/partner-requests/<order_id>/confirm`` ``{date, time}`` — 확정 대기 협력사 주문의 첫 시공일.
* ``POST /api/erp/shipment/partner-requests/<order_id>/revert`` — 정한 시공일을 지워 확정 대기로 돌린다.
* ``POST /api/orders/<order_id>/construction-schedule`` ``{date, time}`` — 시공일 · 시공시간을 정하거나 바꾼다.

권한은 §2.1 ``CONSTRUCTION_SCHEDULE_EDIT``(ERP 편집 팀 + 출고팀)를 handler 안에서 다시 본다 — before_request 가드가
꺼진 컨텍스트에서도 우회되지 않게. 협력사 "시공일 안내" 푸시 · 일정 줄 · 캐시 비우기는 전역 훅이 한다.
"""
from __future__ import annotations

import logging
from typing import Any

from flask import jsonify, request, session

from db import get_db
from foms.api.shipment.settings import erp_shipment_bp
from foms.services.audit_message_display import describe_field_change
from foms.services.orders.audit_order_context import order_audit_context
from foms.services.orders.construction_schedule import (
    ScheduleConflict,
    ScheduleInputError,
    confirm_partner_request,
    finalize_schedule_notifications,
    revert_to_partner_request,
    validate_schedule_input,
    write_construction_schedule,
)
from foms.services.orders.order_mutation_policy import POLICY_REGISTRY, evaluate_policy
from foms.services.orders.revision import lock_order_row
from foms.web.auth import get_user_by_id, log_access

logger = logging.getLogger(__name__)

_SOURCE_BOARD = "shipment_partner_board"
_SOURCE_ORDER = "order_construction_schedule"
_SOURCE_REVERT = "shipment_partner_board_revert"


def _error(message: str, status: int, code: str = "") -> tuple[Any, int]:
    return jsonify({"success": False, "data": None, "error": message, "message": message, "code": code}), status


def _gate():
    user = get_user_by_id(session.get("user_id")) if session.get("user_id") else None
    decision = evaluate_policy(POLICY_REGISTRY["CONSTRUCTION_SCHEDULE_EDIT"], user)
    if not decision.allowed:
        return user, _error(decision.reason, decision.status, decision.code)
    return user, None


def _save(order_id: int, source: str, *, partner_only: bool, revert: bool = False):
    user, denied = _gate()
    if denied is not None:
        return denied
    body = request.get_json(silent=True) or {}
    db = get_db()
    try:
        order = lock_order_row(db, order_id)
        if order is None or getattr(order, "deleted_at", None) is not None:
            db.rollback()
            return _error("주문을 찾을 수 없습니다.", 404, "NOT_FOUND")
        if partner_only and not getattr(order, "partner_org_id", None):
            db.rollback()
            return _error("주문을 찾을 수 없습니다.", 404, "NOT_FOUND")
        if revert:
            result = revert_to_partner_request(db, order, user)
        elif partner_only:
            result = confirm_partner_request(db, order, user, date=body.get("date"), time=body.get("time"))
        else:
            date, time = validate_schedule_input(body.get("date"), body.get("time"))
            result = write_construction_schedule(db, order, user, date=date, time=time)
        hope = ((order.structured_data or {}).get("partner_intake") or {}).get("requested_construction") or {}
        context = order_audit_context(order)
        log_access(
            describe_field_change(order_id=order.id, field="scheduled_date", before=result.before_date,
                                  after=result.date, has_before=True, **context),
            getattr(user, "id", None),
            auto_commit=False,
            action="ORDER_FIELD_UPDATED", target_type="order", target_id=int(order.id),
            detail={"field": "scheduled_date", "before": result.before_date, "after": result.date,
                    "time": result.time, "source": source, "change_set": result.change_set_id,
                    "change_count": result.change_count, **context},
        )
        db.commit()
    except ScheduleInputError as exc:
        db.rollback()
        return _error(str(exc), 400, "INVALID")
    except ScheduleConflict as exc:
        db.rollback()
        return _error(str(exc), 409, "NOT_SCHEDULED" if revert else "ALREADY_SCHEDULED")
    except Exception:  # noqa: BLE001 — 롤백 뒤 500
        db.rollback()
        logger.exception("[CONSTRUCTION_SCHEDULE] 저장 실패 order=%s", order_id)
        return _error("시공일을 저장하지 못했어요. 잠시 뒤 다시 해 주세요.", 500, "SERVER_ERROR")

    finalize_schedule_notifications(db, result)
    hope_date = str((hope if isinstance(hope, dict) else {}).get("date") or "")
    return jsonify({"success": True, "error": None, "data": {
        "order_id": int(order_id), "date": result.date, "time": result.time,
        "before_date": result.before_date, "moved": bool(hope_date) and hope_date != result.date,
        "change_reason_required": result.reason_required, "change_set": result.change_set_id,
    }})


@erp_shipment_bp.route("/api/erp/shipment/partner-requests/<int:order_id>/confirm", methods=["POST"])
def api_confirm_partner_request(order_id: int):
    """협력사 희망 판 [확정] — 확정 대기 협력사 주문에 첫 시공일을 쓴다(이미 있으면 409)."""
    return _save(order_id, _SOURCE_BOARD, partner_only=True)


@erp_shipment_bp.route("/api/orders/<int:order_id>/construction-schedule", methods=["POST"])
def api_set_construction_schedule(order_id: int):
    """시공일 · 시공시간 정하기 · 바꾸기(출고팀 주문 화면). 바꾸면 응답의 ``change_reason_required`` 로 사유를 받는다."""
    return _save(order_id, _SOURCE_ORDER, partner_only=False)


@erp_shipment_bp.route("/api/erp/shipment/partner-requests/<int:order_id>/revert", methods=["POST"])
def api_revert_partner_request(order_id: int):
    """'최근 정한 기록' [되돌리기] — 협력사 주문의 시공일을 지워 희망 판(확정 대기)으로 돌린다."""
    return _save(order_id, _SOURCE_REVERT, partner_only=True, revert=True)
