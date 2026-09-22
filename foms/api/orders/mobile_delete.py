"""모바일 주문 상세 단건 삭제(휴지통 이동)·되돌리기 API (MOBILE-DELETE-01).

정책 ``ORDER_SOFT_DELETE``(ADMIN/MANAGER 또는 STAFF+CS/SALES). PC 의 ``order_trash.delete_order``
와 같은 순서(생산 변경 알림 → canonical soft delete → 사유 기록 → commit → 캐시 무효화)를
JSON 응답으로 감싼다. PC 단건 삭제와 같이 ``order.status`` 는 직접 덮지 않는다(canonical
``deleted_at`` projection 만 — 휴지통 목록·복원은 ``deleted_at`` 술어를 쓴다). 이 모듈은
Order 컬럼을 직접 쓰지 않는다(REV-99·STATE-GUARD 스캔 대상 0).

단계 가드(서버가 강제, UI 는 같은 값을 표시):

- free    : RECEIVED · MEASURE · DRAWING — 사유 선택 → 삭제.
- warn    : CONFIRM · PRODUCTION · CONSTRUCTION — 경고 배너 + 사유 필수.
- blocked : CS · COMPLETED — 모바일 삭제 불가(409 ``MOBILE_DELETE_BLOCKED``), PC 에서만.
"""

from __future__ import annotations

import datetime
import logging
import uuid
from typing import Any

from flask import g, jsonify, request, session

from db import get_db
from foms.services.audit_message_display import describe_field_change
from foms.services.audit_writer import normalize_security_detail
from foms.services.common.dashboard_cache import invalidate_dashboard_caches_after_delete_transition
from foms.services.notifications.production_change import (
    apply_production_change_alert,
    finalize_production_change_alert,
)
from foms.services.orders.audit_order_context import order_audit_context
from foms.services.orders.change_reason import (
    REASON_OTHER,
    normalize_reason,
    reason_label,
    record_action_reason,
)
from foms.services.orders.mobile_delete_guard import (
    GUARD_BLOCKED,
    GUARD_FREE,
    GUARD_WARN,
    POLICY_ID,
    UNDO_WINDOW_SECONDS,
    build_mobile_delete_context,
    stage_guard_for_order,
)
from foms.services.orders.order_mutation_policy import user_can
from foms.services.orders.revision import RevisionError
from foms.services.orders.soft_delete import restore_order, soft_delete_order
from models import Order, SecurityLog

logger = logging.getLogger(__name__)

#: 모바일 사유 칩 → ORDER-REASON-00 코드. 새 코드를 만들지 않는다(집계 목록 유지).
MOBILE_REASON_CODES = ("customer_request", "input_correction", REASON_OTHER)


def _fail(code: str, message: str, status: int, **extra: Any):
    payload: dict[str, Any] = {"success": False, "code": code, "error": message, "message": message}
    payload.update(extra)
    return jsonify(payload), status


def _actor() -> tuple[Any, Any]:
    user = getattr(g, "current_user", None)
    return session.get("user_id"), user


def _invalidate_caches(reason: str) -> None:
    try:
        invalidate_dashboard_caches_after_delete_transition(reason)
    except Exception:
        logger.warning("post %s dashboard cache invalidate failed", reason, exc_info=True)


def _audit(db: Any, *, user_id: Any, message: str, action: str, order_id: int, detail: dict) -> None:
    """감사행을 본 트랜잭션에 싣는다(업무 변경이 되감기면 감사도 함께 되감긴다).

    web 계층 ``log_access`` 는 api 에서 새로 import 하지 않는다(레이어 방향 래칫).
    """
    db.add(SecurityLog(
        user_id=user_id, message=message, action=action, target_type="order",
        target_id=int(order_id), detail=normalize_security_detail(detail),
    ))


def mobile_delete_order_response(order_id: int):
    """``POST /api/orders/<id>/mobile-delete`` 본문.

    요청 JSON: ``{"reason_code", "reason_note", "mutation_version"}``.
    """
    actor_user_id, actor_user = _actor()
    if not user_can(POLICY_ID, actor_user):
        return _fail("FORBIDDEN", "주문 삭제 권한이 없어요.", 403)

    data = request.get_json(silent=True) or {}
    reason_code = str(data.get("reason_code") or "").strip()
    reason_note = str(data.get("reason_note") or "").strip()
    try:
        expected_version = int(data["mutation_version"]) if data.get("mutation_version") is not None else None
    except (TypeError, ValueError):
        expected_version = None

    db = get_db()
    order = db.query(Order).filter(Order.id == order_id, Order.active_filter()).first()
    if order is None:
        return _fail("NOT_FOUND", "주문을 찾을 수 없거나 이미 삭제되었어요.", 404)

    guard = stage_guard_for_order(order)
    if guard["level"] == GUARD_BLOCKED:
        return _fail("MOBILE_DELETE_BLOCKED", guard["label"], 409, guard=guard)

    if reason_code and reason_code not in MOBILE_REASON_CODES:
        return _fail("REASON_INVALID", "삭제 이유가 올바르지 않아요.", 400)
    if reason_code == REASON_OTHER and not reason_note:
        return _fail("REASON_NOTE_REQUIRED", "직접 입력 이유를 적어주세요.", 400)
    if guard["level"] == GUARD_WARN and not reason_code:
        return _fail("REASON_REQUIRED", "진행 중인 주문은 삭제 이유를 골라야 해요.", 400, guard=guard)
    if reason_code:
        try:
            normalize_reason(reason_code, reason_note)
        except ValueError as exc:
            return _fail("REASON_INVALID", str(exc), 400)

    customer_name = order.customer_name
    actor_name = getattr(actor_user, "name", None) or "Unknown user"

    prod_notif = None
    prod_notif_created = False
    try:
        prod_notif, prod_notif_created = apply_production_change_alert(
            db, order, "cancelled", "", actor_user_id=actor_user_id, actor_name=actor_name,
        )
    except Exception:
        logger.warning("production change alert (mobile delete) failed", exc_info=True)

    change_set = str(uuid.uuid4())
    try:
        result = soft_delete_order(
            db,
            order_id=order_id,
            actor_user_id=actor_user_id,
            reason=reason_label(reason_code) if reason_code else None,
            expected_version=expected_version,
        )
        order = db.get(Order, order_id)
        previous_status = getattr(order, "status", None)
        code, note = record_action_reason(
            db, order_id=order_id, change_set_id=change_set,
            code=reason_code, note=reason_note, actor_user_id=actor_user_id,
        )
        audit_ctx = order_audit_context(order)
        _audit(
            db, user_id=actor_user_id,
            message=describe_field_change(
                order_id=order_id, field="status", before=previous_status,
                after="DELETED", has_before=True, **audit_ctx,
            ) + f" · 사유: {reason_label(code)} · 담당자: {actor_name}",
            action="ORDER_SOFT_DELETED", order_id=order_id,
            detail={
                "change_set": change_set, "reason_code": code, "reason_note": note,
                "surface": "mobile", "guard": guard["level"], "customer_name": customer_name,
                **audit_ctx,
            },
        )
        db.commit()
    except RevisionError as exc:
        db.rollback()
        return _fail(exc.error_code, "다른 곳에서 바뀐 주문이에요. 새로고침 후 다시 해주세요.", exc.status_code)
    except Exception:
        db.rollback()
        logger.exception("mobile delete failed order=%s", order_id)
        return _fail("INTERNAL_ERROR", "삭제 중 오류가 났어요. 잠시 후 다시 해주세요.", 500)

    _invalidate_caches("order_delete")
    try:
        finalize_production_change_alert(db, prod_notif, created_new=prod_notif_created)
    except Exception:
        logger.warning("production change finalize (mobile delete) failed", exc_info=True)

    new_version = getattr(result, "mutation_version", None) if result is not None else None
    if new_version is None:
        new_version = int(getattr(order, "mutation_version", None) or 1)
    undo_until = (
        datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(seconds=UNDO_WINDOW_SECONDS)
    ).isoformat()
    return jsonify({
        "success": True,
        "data": {
            "order_id": int(order_id),
            "mutation_version": int(new_version),
            "undo_until": undo_until,
            "undo_seconds": UNDO_WINDOW_SECONDS,
            "customer_name": customer_name,
        },
    }), 200


def mobile_restore_order_response(order_id: int):
    """``POST /api/orders/<id>/mobile-restore`` 본문 — 되돌리기 전용."""
    actor_user_id, actor_user = _actor()
    if not user_can(POLICY_ID, actor_user):
        return _fail("FORBIDDEN", "주문 복원 권한이 없어요.", 403)

    db = get_db()
    order = db.query(Order).filter(Order.id == order_id, Order.deleted_at.isnot(None)).first()
    if order is None:
        return _fail("NOT_FOUND", "휴지통에 없는 주문이에요.", 404)

    if (order.status or "") == "DELETED":
        # legacy status 미러(PC bulk 삭제·cron)가 덮은 주문은 restore_order 만으로 ghost 가 된다
        # (status='DELETED' 잔존). 모바일 삭제는 status 를 안 덮으므로 여기 오면 모바일 건이 아니다.
        return _fail("LEGACY_DELETED", "PC 휴지통에서 복원해 주세요.", 409)

    try:
        restore_order(db, order_id=order_id, actor_user_id=actor_user_id)
        _audit(
            db, user_id=actor_user_id,
            message=f"주문 #{order_id} ({order.customer_name}) 모바일 되돌리기 복원",
            action="ORDER_RESTORED", order_id=order_id,
            detail={"surface": "mobile", "undo": True},
        )
        db.commit()
    except RevisionError as exc:
        db.rollback()
        return _fail(exc.error_code, str(exc), exc.status_code)
    except Exception:
        db.rollback()
        logger.exception("mobile restore failed order=%s", order_id)
        return _fail("INTERNAL_ERROR", "되돌리기 중 오류가 났어요.", 500)

    _invalidate_caches("order_restore")
    db.expire(order)
    return jsonify({
        "success": True,
        "data": {"order_id": int(order_id), "mutation_version": int(order.mutation_version or 1)},
    }), 200


__all__ = [
    "GUARD_BLOCKED",
    "GUARD_FREE",
    "GUARD_WARN",
    "MOBILE_REASON_CODES",
    "POLICY_ID",
    "UNDO_WINDOW_SECONDS",
    "build_mobile_delete_context",
    "mobile_delete_order_response",
    "mobile_restore_order_response",
    "stage_guard_for_order",
]
