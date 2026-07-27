"""ERP 주문 AS(사후관리) API — canonical AS cycle 전이(STATE-AS-01).

erp.py 에서 분리된 as/start·as/complete·as/register·as/schedule 을 canonical
``as_lifecycle`` cycle 상태기계(:mod:`foms.services.orders.as_cycle_service`)로 이관한다.
전이는 orthogonal AS 축(cycle transition history)만 쓰고 ``workflow.stage`` 를 AS_* 로
덮지 않는다(AS main stage 복구/오염 금지). ``order.status`` 는 legacy projection 으로
재계산되는 overlay 이며, version bump·idempotency receipt·``OrderEvent`` parity 는 REV-00
:func:`execute_order_mutation` 이 원자 보장한다(commit 은 이 route 소유).
"""
import copy
import datetime
import hashlib
import json
import logging
from typing import Any, Optional

from flask import Blueprint, jsonify, request, session
from sqlalchemy.orm.attributes import flag_modified

from foms.web.auth import get_user_by_id, login_required
from db import get_db
from foms.services.as_content_safety import sanitize_as_content_html
from foms.services.erp_display import get_today_kst
from foms.services.erp_permissions import erp_construction_edit_required, erp_edit_required
from foms.services.orders.as_cycle_service import (
    ASCycleError,
    complete_as_cycle,
    register_as_cycle,
    reopen_as_cycle,
    schedule_as_cycle,
    set_as_classification,
    start_as_cycle,
    unschedule_as_cycle,
)
from foms.services.orders.revision import RevisionError
from models import Order, SecurityLog

logger = logging.getLogger(__name__)

erp_orders_as_bp = Blueprint(
    "erp_orders_as",
    __name__,
    url_prefix="/api/orders",
)


def _invalidate_shipment_asrec_caches(reason: str) -> None:
    """Dashboard + shipment AS recommendation cache bust (commit-after, best-effort).

    Tier A(broad): AS 전이는 order.status(AS↔CS↔AS_RECEIVED)와 stage projection 을 바꿔
    여러 탭(주문/시공/완료/출고 추천) 사이 이동을 유발하므로 전체 무효화를 유지한다.
    """
    try:
        from foms.services.common.dashboard_cache import invalidate_all_dashboard_slice_caches

        invalidate_all_dashboard_slice_caches()
    except Exception:
        logger.warning("[AS-REC] dashboard cache invalidate failed (%s)", reason, exc_info=True)
    try:
        from foms.services.shipment_as_recommendation_cache import (
            invalidate_shipment_as_recommendation_cache,
        )

        invalidate_shipment_as_recommendation_cache(reason=reason)
    except Exception:
        logger.warning("[AS-REC] shipment asrec cache invalidate failed (%s)", reason, exc_info=True)


def _confirmed_construction_worker_name(user) -> str:
    """Return the construction worker name confirmed by the AS register actor."""
    if not user:
        return ""
    return str(
        getattr(user, "name", None) or getattr(user, "username", None) or ""
    ).strip()


def _scope_hash(command_id: str, order_id: int) -> str:
    """전이 scope 의 sha256 hex(REV-00 receipt 저장용)."""
    return hashlib.sha256(f"{command_id}:{order_id}".encode("utf-8")).hexdigest()


def _request_hash(body: dict[str, Any]) -> str:
    """요청 payload 의 sha256 hex(same-key/different-hash 감지용)."""
    canonical = json.dumps(body, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _idempotency_key(body: dict[str, Any]) -> Optional[str]:
    """요청 idempotency key(헤더 우선, body fallback, ≤64자). 없으면 None."""
    key = request.headers.get("Idempotency-Key") or body.get("idempotency_key")
    key = str(key).strip() if key is not None else ""
    return key[:64] if key else None


def _load_active_order(db, order_id):
    """활성 주문을 로드하고, 없거나 삭제됐으면 404 JSON 튜플을 돌려준다."""
    order = db.get(Order, order_id)
    if not order or order.status == "DELETED" or order.deleted_at is not None:
        return None, (jsonify({"success": False, "message": "주문을 찾을 수 없습니다."}), 404)
    return order, None


def _as_error_response(db, exc: Exception):
    """AS cycle/REV 계약 위반을 409 로, 그 외는 500 으로 매핑하고 rollback 한다."""
    db.rollback()
    if isinstance(exc, (ASCycleError, RevisionError)):
        return jsonify({"success": False, "message": str(exc)}), 409
    logger.error("AS command failed", exc_info=True)
    return jsonify({"success": False, "message": str(exc)}), 500


@erp_orders_as_bp.route("/<int:order_id>/as/register", methods=["POST"])
@login_required
@erp_construction_edit_required
def api_as_register(order_id):
    """AS 접수 등록: 새 RECEIVED cycle 발급 + 접수일 스탬프 + draft finalize(DRAFT-LIFECYCLE)."""
    db = get_db()
    order, err = _load_active_order(db, order_id)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    as_content = sanitize_as_content_html(data.get("as_content"))
    source_screen = str(data.get("source_screen") or "").strip()
    shipping = str(data.get("shipping_scheduled_date") or "").strip() or None

    user_id = session.get("user_id")
    user = get_user_by_id(user_id)
    today = get_today_kst().strftime("%Y-%m-%d")
    cw_name = (
        _confirmed_construction_worker_name(user)
        if source_screen == "erp_construction_dashboard"
        else ""
    )
    old_sd = copy.deepcopy(order.structured_data or {})
    now = datetime.datetime.now()

    # /add draft 주문은 structured PUT 없이 AS 모달만 완료하므로 draft meta 를 먼저 정리한다
    # (남으면 Order.active_filter 에서 제외돼 AS 탭에 안 보임). 이후 register 의 projection 이
    # order.status 를 AS_RECEIVED overlay 로 최종 확정한다(finalize 의 stage 배정을 덮어씀).
    from foms.api.erp_orders_structured import _finalize_draft_state

    draft_cleared = _finalize_draft_state(order, order.structured_data, now, old_sd)
    if draft_cleared:
        flag_modified(order, "structured_data")

    try:
        register_as_cycle(
            db, order_id=order_id, actor_user_id=user_id, as_content=as_content,
            shipping_scheduled_date=shipping, source_screen=source_screen or None,
            received_date=today, construction_worker_name=cw_name or None,
            scope_hash=_scope_hash("AS_REGISTER", order_id), request_hash=_request_hash(data),
            idempotency_key=_idempotency_key(data),
        )
    except Exception as exc:  # noqa: BLE001 — 계약 위반은 409, 그 외 500 으로 분기
        return _as_error_response(db, exc)

    db.add(SecurityLog(user_id=user_id, message=f"주문 #{order_id} AS 접수 등록 (접수일: {today})"))
    db.commit()
    _invalidate_shipment_asrec_caches("api_as_register")

    shipment = (order.structured_data or {}).get("shipment") or {}
    return jsonify({
        "success": True,
        "message": "AS 접수가 등록되었습니다.",
        "as_received_date": today,
        "new_status": order.status,
        "shipping_scheduled_date": getattr(order, "shipping_scheduled_date", None) or "",
        "construction_workers": shipment.get("construction_workers") or [],
        "draft_cleared": draft_cleared,
    })


@erp_orders_as_bp.route("/<int:order_id>/as/schedule", methods=["POST"])
@login_required
@erp_edit_required
def api_as_schedule(order_id):
    """AS 방문일 확정: current cycle 에 방문 날짜/시각 transition 기록(빈 날짜는 unschedule)."""
    db = get_db()
    order, err = _load_active_order(db, order_id)
    if err:
        return err
    data = request.get_json() or {}
    visit_date = str(data.get("visit_date") or "").strip()
    visit_time = data.get("visit_time", "")
    user_id = session.get("user_id")

    try:
        if not visit_date:
            unschedule_as_cycle(
                db, order_id=order_id, actor_user_id=user_id,
                reason=str(data.get("reason") or "방문일 취소"),
                cycle_id=data.get("cycle_id"),
                scope_hash=_scope_hash("AS_UNSCHEDULE", order_id),
                request_hash=_request_hash(data), idempotency_key=_idempotency_key(data),
            )
            message, result_date = "AS 방문일이 취소되었습니다.", ""
        else:
            schedule_as_cycle(
                db, order_id=order_id, actor_user_id=user_id, visit_date=visit_date,
                visit_time=visit_time, cycle_id=data.get("cycle_id"),
                scope_hash=_scope_hash("AS_SCHEDULE", order_id),
                request_hash=_request_hash(data), idempotency_key=_idempotency_key(data),
            )
            message, result_date = f"AS 방문일이 {visit_date}로 확정되었습니다.", visit_date
    except Exception as exc:  # noqa: BLE001
        return _as_error_response(db, exc)

    db.add(SecurityLog(user_id=user_id, message=f"주문 #{order_id} AS 방문일: {result_date or '취소'}"))
    db.commit()
    _invalidate_shipment_asrec_caches("api_as_schedule")
    return jsonify({"success": True, "message": message, "visit_date": result_date})


@erp_orders_as_bp.route("/<int:order_id>/as/unschedule", methods=["POST"])
@login_required
@erp_edit_required
def api_as_unschedule(order_id):
    """AS 방문일 취소: current cycle 방문 날짜/시각을 명시 transition 으로 clear(상태 불변)."""
    db = get_db()
    order, err = _load_active_order(db, order_id)
    if err:
        return err
    data = request.get_json() or {}
    user_id = session.get("user_id")
    try:
        unschedule_as_cycle(
            db, order_id=order_id, actor_user_id=user_id,
            reason=str(data.get("reason") or "방문일 취소"), cycle_id=data.get("cycle_id"),
            scope_hash=_scope_hash("AS_UNSCHEDULE", order_id),
            request_hash=_request_hash(data), idempotency_key=_idempotency_key(data),
        )
    except Exception as exc:  # noqa: BLE001
        return _as_error_response(db, exc)
    db.add(SecurityLog(user_id=user_id, message=f"주문 #{order_id} AS 방문일 취소"))
    db.commit()
    _invalidate_shipment_asrec_caches("api_as_unschedule")
    return jsonify({"success": True, "message": "AS 방문일이 취소되었습니다."})


@erp_orders_as_bp.route("/<int:order_id>/as/start", methods=["POST"])
@login_required
@erp_edit_required
def api_as_start(order_id):
    """AS 시작: current RECEIVED cycle 을 IN_PROGRESS 로 전이(사유/설명 기록)."""
    db = get_db()
    order, err = _load_active_order(db, order_id)
    if err:
        return err
    data = request.get_json() or {}
    user_id = session.get("user_id")
    try:
        start_as_cycle(
            db, order_id=order_id, actor_user_id=user_id,
            reason=str(data.get("reason") or ""), description=str(data.get("description") or ""),
            cycle_id=data.get("cycle_id"), scope_hash=_scope_hash("AS_START", order_id),
            request_hash=_request_hash(data), idempotency_key=_idempotency_key(data),
        )
    except Exception as exc:  # noqa: BLE001
        return _as_error_response(db, exc)
    db.add(SecurityLog(user_id=user_id, message=f"주문 #{order_id} AS 시작"))
    db.commit()
    _invalidate_shipment_asrec_caches("api_as_start")
    return jsonify({"success": True, "message": "AS가 시작되었습니다.", "new_status": order.status})


@erp_orders_as_bp.route("/<int:order_id>/as/complete", methods=["POST"])
@login_required
@erp_edit_required
def api_as_complete(order_id):
    """AS 완료: current IN_PROGRESS cycle 을 COMPLETED 로 종결(완료 메모·완료일 기록)."""
    db = get_db()
    order, err = _load_active_order(db, order_id)
    if err:
        return err
    data = request.get_json() or {}
    user_id = session.get("user_id")
    try:
        complete_as_cycle(
            db, order_id=order_id, actor_user_id=user_id, note=str(data.get("note") or ""),
            cycle_id=data.get("cycle_id"), scope_hash=_scope_hash("AS_COMPLETE", order_id),
            request_hash=_request_hash(data), idempotency_key=_idempotency_key(data),
        )
    except Exception as exc:  # noqa: BLE001
        return _as_error_response(db, exc)
    db.add(SecurityLog(user_id=user_id, message=f"주문 #{order_id} AS 완료"))
    db.commit()
    _invalidate_shipment_asrec_caches("api_as_complete")
    return jsonify({"success": True, "message": "AS가 완료되었습니다.", "new_status": order.status})


@erp_orders_as_bp.route("/<int:order_id>/as/reopen", methods=["POST"])
@login_required
@erp_edit_required
def api_as_reopen(order_id):
    """AS 재개봉: 오완료된 current COMPLETED cycle 을 같은 cycle 로 RECEIVED 로 되돌린다."""
    db = get_db()
    order, err = _load_active_order(db, order_id)
    if err:
        return err
    data = request.get_json() or {}
    user_id = session.get("user_id")
    try:
        reopen_as_cycle(
            db, order_id=order_id, actor_user_id=user_id,
            reason=str(data.get("reason") or ""), cycle_id=data.get("cycle_id"),
            scope_hash=_scope_hash("AS_REOPEN", order_id),
            request_hash=_request_hash(data), idempotency_key=_idempotency_key(data),
        )
    except Exception as exc:  # noqa: BLE001
        return _as_error_response(db, exc)
    db.add(SecurityLog(user_id=user_id, message=f"주문 #{order_id} AS 재개봉"))
    db.commit()
    _invalidate_shipment_asrec_caches("api_as_reopen")
    return jsonify({"success": True, "message": "AS가 재개봉되었습니다.", "new_status": order.status})


@erp_orders_as_bp.route("/<int:order_id>/as/classification", methods=["POST"])
@login_required
@erp_edit_required
def api_as_classification(order_id):
    """AS 분류 토글: current cycle 의 as_pending/as_blueprint/sales_delivery 를 갱신(상태·main 불변)."""
    db = get_db()
    order, err = _load_active_order(db, order_id)
    if err:
        return err
    data = request.get_json() or {}
    user_id = session.get("user_id")
    field = str(data.get("field") or "")
    value = bool(data.get("value"))
    try:
        set_as_classification(
            db, order_id=order_id, actor_user_id=user_id, field=field, value=value,
            cycle_id=data.get("cycle_id"), scope_hash=_scope_hash("SET_AS_CLASSIFICATION", order_id),
            request_hash=_request_hash(data), idempotency_key=_idempotency_key(data),
        )
    except Exception as exc:  # noqa: BLE001
        return _as_error_response(db, exc)
    db.add(SecurityLog(user_id=user_id, message=f"주문 #{order_id} AS 분류 {field}={value}"))
    db.commit()
    _invalidate_shipment_asrec_caches("api_as_classification")
    shipment = (order.structured_data or {}).get("shipment") or {}
    return jsonify({
        "success": True,
        "message": "AS 분류가 업데이트되었습니다.",
        "field": field,
        "value": value,
        "as_pending": shipment.get("as_pending") is True,
        "as_blueprint": shipment.get("as_blueprint") is True,
        "sales_delivery": shipment.get("sales_delivery") is True,
    })


__all__ = [
    "erp_orders_as_bp",
    "api_as_start",
    "api_as_complete",
    "api_as_register",
    "api_as_schedule",
    "api_as_unschedule",
    "api_as_reopen",
    "api_as_classification",
    "get_today_kst",
]
