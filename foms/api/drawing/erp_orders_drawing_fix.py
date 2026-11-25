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
"""

from __future__ import annotations

import copy
import logging
from typing import Any

from flask import Blueprint, g, jsonify, request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm.attributes import flag_modified

from db import get_db
# 감사 = log_access(대신 로그인 impersonated_by · detail 정규화 · 감사 행만 되감는 savepoint). api → web 새 import 는 레이어 래칫이
# 막으므로 같은 패키지에서 이미 그 길을 쓰는 전달 API 모듈에서 가져온다(공장 완료 API factory_done.py 가 _audit_production 을 쓰는 길).
from foms.api.drawing.erp_orders_drawing import log_access
from foms.services.audit_message_display import describe_order_action
from foms.services.common.dashboard_cache import (
    DASHBOARD_FAMILY_DRAWING,
    DASHBOARD_FAMILY_PRODUCTION,
    invalidate_order_dashboard_families,
)
from foms.services.datetime_kst import now_utc_naive
from foms.services.erp_display import _ensure_dict
from foms.services.orders.audit_order_context import order_audit_context
from foms.services.orders.drawing_fix_marks import (
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
from foms.services.orders.revision import RevisionError, execute_single_order_write, lock_order_row
from models import OrderEvent

logger = logging.getLogger(__name__)

#: REV-00 영수증 정책 id(시작 · 취소를 다른 도면 일과 섞지 않게 따로 둔다). 앞문 정책은 매니페스트의 ``DRAWING_TEAM``.
FIX_START_POLICY_ID = "DRAWING_FIX_START"
FIX_STOP_POLICY_ID = "DRAWING_FIX_STOP"
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


__all__ = ["FIX_START_POLICY_ID", "FIX_STOP_POLICY_ID", "api_drawing_fix_start", "api_drawing_fix_stop", "erp_orders_drawing_fix_bp"]
