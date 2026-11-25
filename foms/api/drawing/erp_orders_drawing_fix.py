"""생산 넘어간 주문의 도면 수정 — [수정 시작] · [수정 취소] API(설계서 2026-11-25 N1 · N2, D3).

``POST /api/orders/<id>/drawing/fix/start`` · ``POST /api/orders/<id>/drawing/fix/stop`` 몸 ``{targets: [{sheet_id} | {key}]}``.
응답 ``{success, data: {changed, fixing: [{no, ident, by_name, at}], mutation_version}, error}``.

* 누가 · 언제 · 글: :mod:`foms.services.orders.drawing_fix_marks`(앞문 정책 ``DRAWING_TEAM`` 은 MANAGER 를 팀과 상관없이 지나보내므로
  처리기가 도면팀 STAFF · MANAGER + 관리자만 남긴다 — 403 ``FIX_FORBIDDEN``). [수정 시작]은 생산 단계만(409 ``FIX_STAGE``).
* 한 tx: 행 잠금(:func:`~foms.services.orders.revision.lock_order_row`) → 판정 → deepcopy 사본 고침 →
  :func:`~foms.services.orders.revision.execute_single_order_write`(재대입 · ``flag_modified`` · 버전 +1) → ``OrderEvent``
  (``DRAWING_FIX_STARTED`` · ``DRAWING_FIX_STOPPED`` — 생산 '바뀐 것' 한 줄, 폰 알림 없음) → 감사(``log_access`` — 대신 로그인 표지 ·
  detail 정규화 그대로) → 커밋.
* 멱등: 바뀐 장이 없으면(이미 그 상태) 쓰지 않고 200 ``changed:false`` — 버전 · 이벤트 · 감사 0.
* 쓴 뒤 도면 · 생산 캐시 무효화(작업실 목록 · 생산 화면이 새 막힘을 본다).

공장 요청 [요청 반려] · [반영 완료](설계서 2026-11-25 N4 · N5, D4) — ``POST …/drawing/fix/requests/<rid>/reject`` 몸 ``{note}`` ·
``POST …/drawing/fix/requests/<rid>/check`` 몸 ``{checked: bool}``. 응답 ``{success, data: {changed, request, mutation_version}, error}``.

* 누가: ``can_fix_production_drawing``(도면팀 누구나 + 관리자, 생산 · 시공 단계 — 시공 대기 상세에서도 된다) — 그 밖 403 ``FIX_FORBIDDEN``.
* 반려: 사유 빈 글 400 ``REJECT_NOTE_REQUIRED`` · 이미 반려 200 ``changed:false`` · 반영(수정본)으로 닫힌 요청 409 ``REQUEST_CLOSED`` →
  ``rejected``(막힘 풀림) + 이벤트 ``DRAWING_FIX_REQUEST_REJECTED``(생산 '바뀐 것' "도면 수정 요청 반려" 한 줄) + 감사 + 요청한 사람에게
  알림(종 + 폰, 확인 창 없음).
* 반영 완료 · 해제: 같은 값 200 ``changed:false`` · 닫힌 요청 409 ``REQUEST_CLOSED`` → ``checked`` 만(막힘 그대로 — 수정본이 가야 풀린다)
  + 이벤트 ``DRAWING_FIX_REQUEST_CHECKED`` + 감사. 알림 없음.
"""

from __future__ import annotations

import copy
import logging
from typing import Any, Optional

from flask import Blueprint, g, jsonify, request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm.attributes import flag_modified

from db import get_db
# 감사 = log_access(대신 로그인 impersonated_by · detail 정규화 · 감사 행만 되감는 savepoint). api → web 새 import 는 레이어 래칫이
# 막으므로 같은 패키지에서 이미 그 길을 쓰는 전달 API 모듈에서 가져온다(공장 완료 API factory_done.py 가 _audit_production 을 쓰는 길).
from foms.api.drawing.erp_orders_drawing import log_access
from foms.api.notifications import invalidate_badge_cache_for_user_ids
from foms.services.audit_message_display import describe_order_action
from foms.services.common.dashboard_cache import (
    DASHBOARD_FAMILY_DRAWING,
    DASHBOARD_FAMILY_PRODUCTION,
    invalidate_order_dashboard_families,
)
from foms.services.datetime_kst import now_utc_naive
from foms.services.erp_display import _ensure_dict
from foms.services.notifications.drawing_factory_request_push import REJECTED_TITLE, REJECTED_TYPE
from foms.services.notifications.push_sender import enqueue_push_for_notification
from foms.services.notifications.realtime_notifications import emit_erp_notification_to_users
from foms.services.notifications.recipients import fan_out_new_notification
from foms.services.orders.audit_order_context import order_audit_context
from foms.services.orders.drawing_fix import REQUEST_OPEN, request_checked
from foms.services.orders.drawing_fix_marks import (
    FIX_FORBIDDEN,
    FIX_STARTED_EVENT,
    FIX_STOPPED_EVENT,
    FixRefusal,
    fixing_rows,
    numbers_note,
    refusal_for,
    resolve_targets,
    start_fixing,
    stop_fixing,
)
from foms.services.orders.drawing_fix_requests import (
    CHECK_EVENT,
    REJECT_EVENT,
    REJECT_NOTE_REQUIRED,
    REQUEST_CLOSED,
    REQUEST_NOT_FOUND,
    STATE_REJECTED,
    RequestRefusal,
    check_request,
    clean_note,
    find_request,
    left_numbers,
    numbers_label,
    reject_message,
    reject_request,
)
from foms.services.orders.drawing_fix_transfer import can_fix_production_drawing
from foms.services.orders.revision import RevisionError, execute_single_order_write, lock_order_row
from models import Notification, OrderEvent, User

logger = logging.getLogger(__name__)

#: REV-00 영수증 정책 id(시작 · 취소를 다른 도면 일과 섞지 않게 따로 둔다). 앞문 정책은 매니페스트의 ``DRAWING_TEAM``.
FIX_START_POLICY_ID = "DRAWING_FIX_START"
FIX_STOP_POLICY_ID = "DRAWING_FIX_STOP"
REJECT_POLICY_ID = "DRAWING_FIX_REJECT"
CHECK_POLICY_ID = "DRAWING_FIX_CHECK"
_SAVE_FAILED = "저장하지 못했어요. 잠시 뒤 다시 해 주세요."
_NOT_FOUND = "주문을 찾을 수 없어요."

erp_orders_drawing_fix_bp = Blueprint("erp_orders_drawing_fix", __name__, url_prefix="/api/orders")


def _fail(status: int, code: str, message: str):
    return jsonify({"success": False, "data": {"code": code}, "error": message}), status


def _actor_name(user: Any) -> str:
    return getattr(user, "name", None) or getattr(user, "username", None) or ""


def _record(db: Any, order: Any, user: Any, rows: list[dict[str, Any]], *, starting: bool) -> None:
    """이벤트 1 + 감사 1(같은 tx) — '바뀐 것' 줄은 이벤트 ``numbers`` · ``by_name`` 을 읽는다."""
    event_type = FIX_STARTED_EVENT if starting else FIX_STOPPED_EVENT
    payload = {"numbers": [r["no"] for r in rows], "idents": [r["ident"] for r in rows], "by_name": _actor_name(user)}
    db.add(OrderEvent(order_id=order.id, event_type=event_type, created_by_user_id=user.id, payload=payload))
    context = order_audit_context(order)
    log_access(describe_order_action(order_id=order.id, action=event_type, note=numbers_note(rows), **context), user.id,
               auto_commit=False, action=event_type, target_type="order", target_id=int(order.id),
               detail={**payload, **context}, db=db)  # 호출자 세션 — get_db() 를 새로 붙이지 않게


def _write(db: Any, user: Any, order_id: int, payload: Any, *, starting: bool) -> dict[str, Any]:
    """잠근 주문 위에서 판정 → 쓰기(바뀐 장이 없으면 쓰지 않음). 커밋 · 되감기는 부르는 쪽.

    Raises:
        FixRefusal: 권한 · 단계 · 지금 도면에 없는 장.
        LookupError: 주문 없음 · 지움 · ERP 아님.
    """
    order = lock_order_row(db, order_id)
    if order is None or order.status == "DELETED" or order.deleted_at is not None or not order.is_erp_order:
        raise LookupError(order_id)
    refusal = refusal_for(user, order, starting=starting)
    if refusal is not None:
        raise refusal
    sd = copy.deepcopy(_ensure_dict(order.structured_data))
    picked = resolve_targets(sd, payload.get("targets") if isinstance(payload, dict) else None)
    at = now_utc_naive().replace(microsecond=0).isoformat() + "Z"
    if starting:
        rows = start_fixing(sd, picked, by_user_id=user.id, by_name=_actor_name(user), at=at)
    else:
        rows = stop_fixing(sd, picked, by_name=_actor_name(user), at=at)
    if not rows:
        return {"changed": False, "fixing": fixing_rows(sd), "order": order}

    def _assign(locked: Any) -> None:
        locked.structured_data = sd
        flag_modified(locked, "structured_data")

    execute_single_order_write(db, order_id=order_id, actor_user_id=user.id,
                               policy_id=FIX_START_POLICY_ID if starting else FIX_STOP_POLICY_ID, payload=payload, write=_assign)
    _record(db, order, user, rows, starting=starting)
    return {"changed": True, "fixing": fixing_rows(sd), "order": order}


def _handle(order_id: int, *, starting: bool):
    """시작 · 취소 공통 — 로그인 없음 401 · 권한 403 · 단계 · 지금 도면 아님 409 · 없는 주문 404."""
    user = getattr(g, "current_user", None)  # before_request(_set_current_user) — 비활성 · 끊긴 세션은 이미 비웠다
    if user is None:
        return _fail(401, "AUTH_REQUIRED", "다시 로그인해 주세요.")
    db = get_db()
    payload = request.get_json(silent=True) or {}
    try:
        result = _write(db, user, order_id, payload, starting=starting)
        if result["changed"]:
            db.commit()
        else:
            db.rollback()  # 잠금만 풀고 쓰기 · 버전 · 이벤트 0(멱등)
    except FixRefusal as refusal:
        db.rollback()
        return _fail(refusal.status, refusal.code, refusal.message)
    except LookupError:
        db.rollback()
        return _fail(404, "NOT_FOUND", _NOT_FOUND)
    except (RevisionError, SQLAlchemyError) as exc:
        db.rollback()
        logger.exception("[DRAWING_FIX] order %s start=%s: %s", order_id, starting, exc)
        return _fail(500, "SAVE_FAILED", _SAVE_FAILED)
    order = result["order"]
    if result["changed"]:
        invalidate_order_dashboard_families(order, extra=(DASHBOARD_FAMILY_DRAWING, DASHBOARD_FAMILY_PRODUCTION))
    data = {"changed": result["changed"], "fixing": result["fixing"], "mutation_version": int(order.mutation_version or 0)}
    return jsonify({"success": True, "data": data, "error": None})


@erp_orders_drawing_fix_bp.route("/<int:order_id>/drawing/fix/start", methods=["POST"])
def api_drawing_fix_start(order_id: int):
    """[수정 시작] — 고른 도면을 고치는 중으로 표시(공장에서 그 도면만 막힘)."""
    return _handle(order_id, starting=True)


@erp_orders_drawing_fix_bp.route("/<int:order_id>/drawing/fix/stop", methods=["POST"])
def api_drawing_fix_stop(order_id: int):
    """[수정 취소] — 고른 도면의 고치는 중 표시를 지움(공장에서 다시 작업 가능)."""
    return _handle(order_id, starting=False)


# --------------------------------------------------------------------------- #
# 공장 요청 [요청 반려] · [반영 완료](N4 · N5, D4)
# --------------------------------------------------------------------------- #
def _customer(order: Any) -> str:
    sd = _ensure_dict(order.structured_data)
    name = ((sd.get("parties") or {}).get("customer") or {}).get("name") or getattr(order, "customer_name", None) or ""
    return str(name).strip()


def _record_request(db: Any, order: Any, user: Any, req: dict[str, Any], numbers: list[int], *, rejecting: bool) -> None:
    """이벤트 1 + 감사 1(같은 tx) — 반려 줄은 '바뀐 것'이 이벤트 ``numbers`` · ``note`` · ``by_name`` 을 읽는다."""
    event_type = REJECT_EVENT if rejecting else CHECK_EVENT
    payload = {"request_id": req.get("id"), "numbers": numbers, "idents": list(req.get("targets") or []),
               "by_name": _actor_name(user)}
    payload.update({"note": req.get("reject_note") or ""} if rejecting else {"checked": bool(req.get("checked"))})
    db.add(OrderEvent(order_id=order.id, event_type=event_type, created_by_user_id=user.id, payload=payload))
    context = order_audit_context(order)
    log_access(describe_order_action(order_id=order.id, action=event_type, note=numbers_label(numbers), **context), user.id,
               auto_commit=False, action=event_type, target_type="order", target_id=int(order.id),
               detail={**payload, **context}, db=db)


def _reject_notification(db: Any, order: Any, user: Any, req: dict[str, Any], numbers: list[int]) -> Any:
    """요청한 사람 한 명에게 반려 알림 줄(종 — 받는 사람 state 까지, 같은 tx).

    만들지 않는 경우(None): 요청한 사람 번호가 없음 · 반려한 사람이 요청한 사람 본인(제가 닫은 일을 저에게 알리지 않는다) · 요청한 사람
    계정이 없거나 꺼짐(받을 사람이 없다). 공장 '바뀐 것' 줄(이벤트)은 어느 경우든 그대로 남는다.
    """
    uid = req.get("by_user_id")
    if not isinstance(uid, int) or isinstance(uid, bool) or uid == getattr(user, "id", None):
        return None
    requester = db.get(User, uid)
    if requester is None or not requester.is_active:
        return None
    notification = Notification(order_id=order.id, notification_type=REJECTED_TYPE, target_type="USER", target_user_id=uid,
                                title=REJECTED_TITLE,
                                message=reject_message(int(order.id), _customer(order), numbers, req.get("reject_note") or ""),
                                created_by_user_id=user.id, created_by_name=_actor_name(user))
    db.add(notification)
    db.flush()
    fan_out_new_notification(db, notification, actor_user_id=user.id)
    return notification


def _apply_request(sd: dict[str, Any], req: dict[str, Any], payload: Any, user: Any, *, note: str,
                   rejecting: bool) -> Optional[list[int]]:
    """사본 안 요청 한 건을 반려 · 반영 완료로 고친다 — 이미 그 상태면 None(쓰지 않음). 닫힌 요청이면 409 ``REQUEST_CLOSED``."""
    at = now_utc_naive().replace(microsecond=0).isoformat() + "Z"
    if rejecting:
        if req.get("state") == STATE_REJECTED:
            return None
        if req.get("state") != REQUEST_OPEN:
            raise RequestRefusal(409, REQUEST_CLOSED)
        return reject_request(sd, req, note=note, user_id=user.id, by_name=_actor_name(user), at=at)
    checked = isinstance(payload, dict) and payload.get("checked") is True
    if request_checked(req) == checked:
        return None
    if req.get("state") != REQUEST_OPEN:
        raise RequestRefusal(409, REQUEST_CLOSED)
    check_request(req, checked, by_name=_actor_name(user), at=at)
    return left_numbers(sd, req)


def _request_write(db: Any, user: Any, order_id: int, rid: str, payload: Any, *, rejecting: bool) -> dict[str, Any]:
    """잠근 주문 위에서 판정 → 쓰기(이미 그 상태면 쓰지 않음). 커밋 · 되감기는 부르는 쪽.

    Raises:
        FixRefusal: 권한(403). RequestRefusal: 사유 · 없는 요청 · 닫힌 요청. LookupError: 주문 없음.
    """
    order = lock_order_row(db, order_id)
    if order is None or order.status == "DELETED" or order.deleted_at is not None or not order.is_erp_order:
        raise LookupError(order_id)
    if not can_fix_production_drawing(user, order):
        raise FixRefusal(403, FIX_FORBIDDEN)
    note = clean_note(payload.get("note")) if rejecting and isinstance(payload, dict) else ""
    if rejecting and not note:
        raise RequestRefusal(400, REJECT_NOTE_REQUIRED)
    sd = copy.deepcopy(_ensure_dict(order.structured_data))
    req = find_request(sd, rid)
    if req is None:
        raise RequestRefusal(404, REQUEST_NOT_FOUND)
    numbers = _apply_request(sd, req, payload, user, note=note, rejecting=rejecting)
    if numbers is None:
        return {"changed": False, "request": req, "order": order, "notification": None}

    def _assign(locked: Any) -> None:
        locked.structured_data = sd
        flag_modified(locked, "structured_data")

    execute_single_order_write(db, order_id=order_id, actor_user_id=user.id,
                               policy_id=REJECT_POLICY_ID if rejecting else CHECK_POLICY_ID, payload=payload, write=_assign)
    _record_request(db, order, user, req, numbers, rejecting=rejecting)
    notification = _reject_notification(db, order, user, req, numbers) if rejecting else None
    return {"changed": True, "request": req, "order": order, "notification": notification}


def _announce_reject(db: Any, order: Any, user: Any, notification: Any) -> None:
    """커밋 뒤 — 요청한 사람 폰 알림 enqueue · 종 배지 · 종 새로 읽기(확인 창 등급은 없다)."""
    enqueue_push_for_notification(notification.id, db=db)
    recipients = {int(notification.target_user_id)}
    invalidate_badge_cache_for_user_ids(recipients)
    emit_erp_notification_to_users(recipients, {
        "notification_id": notification.id, "order_id": int(order.id), "notification_type": REJECTED_TYPE,
        "title": notification.title, "message": notification.message, "created_by_name": _actor_name(user),
        "customer_name": _customer(order),
    })


def _handle_request(order_id: int, rid: str, *, rejecting: bool):
    """반려 · 반영 완료 공통 — 로그인 없음 401 · 권한 403 · 사유 400 · 없는 요청 404 · 닫힌 요청 409 · 없는 주문 404."""
    user = getattr(g, "current_user", None)
    if user is None:
        return _fail(401, "AUTH_REQUIRED", "다시 로그인해 주세요.")
    db = get_db()
    payload = request.get_json(silent=True) or {}
    try:
        result = _request_write(db, user, order_id, rid, payload, rejecting=rejecting)
        if result["changed"]:
            db.commit()
        else:
            db.rollback()  # 잠금만 풀고 쓰기 · 버전 · 이벤트 0(멱등)
    except (FixRefusal, RequestRefusal) as refusal:
        db.rollback()
        return _fail(refusal.status, refusal.code, refusal.message)
    except LookupError:
        db.rollback()
        return _fail(404, "NOT_FOUND", _NOT_FOUND)
    except (RevisionError, SQLAlchemyError) as exc:
        db.rollback()
        logger.exception("[DRAWING_FIX] order %s request %s reject=%s: %s", order_id, rid, rejecting, exc)
        return _fail(500, "SAVE_FAILED", _SAVE_FAILED)
    order = result["order"]
    if result["notification"] is not None:
        _announce_reject(db, order, user, result["notification"])
    if result["changed"]:
        invalidate_order_dashboard_families(order, extra=(DASHBOARD_FAMILY_DRAWING, DASHBOARD_FAMILY_PRODUCTION))
    data = {"changed": result["changed"], "request": result["request"], "mutation_version": int(order.mutation_version or 0)}
    return jsonify({"success": True, "data": data, "error": None})


@erp_orders_drawing_fix_bp.route("/<int:order_id>/drawing/fix/requests/<rid>/reject", methods=["POST"])
def api_drawing_fix_request_reject(order_id: int, rid: str):
    """공장 요청 [요청 반려] — 사유를 적고 닫는다(그 도면 막힘이 풀리고 요청한 사람에게 알림)."""
    return _handle_request(order_id, rid, rejecting=True)


@erp_orders_drawing_fix_bp.route("/<int:order_id>/drawing/fix/requests/<rid>/check", methods=["POST"])
def api_drawing_fix_request_check(order_id: int, rid: str):
    """공장 요청 [반영 완료] · [완료 해제] — 수정본을 보낼 수 있게 표시만(막힘은 수정본이 갈 때까지 그대로)."""
    return _handle_request(order_id, rid, rejecting=False)


__all__ = [
    "CHECK_POLICY_ID", "FIX_START_POLICY_ID", "FIX_STOP_POLICY_ID", "REJECT_POLICY_ID", "api_drawing_fix_request_check",
    "api_drawing_fix_request_reject", "api_drawing_fix_start", "api_drawing_fix_stop", "erp_orders_drawing_fix_bp",
]
