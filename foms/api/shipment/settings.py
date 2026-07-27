"""
ERP 출고 설정 페이지 및 API. (Phase 4-2)
erp.py에서 분리. 서비스는 foms/services/erp_shipment_settings 사용.
"""

import hashlib
import json
import logging
from typing import Any, Optional

from flask import Blueprint, g, jsonify, make_response, render_template, request, session
from sqlalchemy.orm.attributes import flag_modified

from foms.web.auth import get_user_by_id, login_required, role_required
from db import get_db
from foms.services.datetime_kst import now_utc_naive
from foms.services.erp_permissions import can_edit_erp, erp_edit_required
from foms.services.erp_shipment_settings import (
    ERP_SHIPMENT_SETTINGS_KEY,
    load_erp_shipment_settings,
)
from foms.services.orders.order_mutation_policy import POLICY_REGISTRY, evaluate_policy
from foms.services.orders.revision import RevisionError, execute_order_mutation
from foms.services.shipment.writer import apply_shipment_settings
from foms.services.shipment_reference import (
    SHIPMENT_REFERENCE_POLICY_ID,
    ShipmentReferenceError,
    update_shipment_reference_lists,
)
from models import Order, OrderEvent, SystemSetting

from foms.services.common.erp_shell_http import apply_erp_shell_fragment_headers, wants_erp_shell_tab_body

logger = logging.getLogger(__name__)
erp_shipment_bp = Blueprint("erp_shipment", __name__)


def _current_settings_version() -> int:
    """현재 reference collection 의 optimistic-lock version(없으면 0)."""
    setting = (
        get_db()
        .query(SystemSetting)
        .filter(SystemSetting.setting_key == ERP_SHIPMENT_SETTINGS_KEY)
        .first()
    )
    return int(getattr(setting, "version", 0) or 0) if setting is not None else 0


def _reference_policy_decision():
    """SHIPMENT_REFERENCE(§2.1) 권한을 payload 파싱 전에 강제(가드 off 컨텍스트 우회 차단)."""
    user = get_user_by_id(session.get("user_id"))
    return user, evaluate_policy(POLICY_REGISTRY[SHIPMENT_REFERENCE_POLICY_ID], user)


def _if_match_from_request(payload: dict) -> Optional[int]:
    """If-Match 헤더 또는 body ``settings_version`` 에서 정수 version 을 읽는다(형식 오류=None)."""
    raw = (request.headers.get("If-Match") or "").strip().strip('"')
    if not raw and isinstance(payload, dict) and payload.get("settings_version") is not None:
        raw = str(payload.get("settings_version")).strip()
    if not raw:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


@erp_shipment_bp.route("/erp/shipment-settings")
@login_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def erp_shipment_settings():
    """ERP 출고 설정 페이지."""
    settings = load_erp_shipment_settings()
    current_user = getattr(g, "current_user", None)
    template_name = (
        "shipment/settings_fragment.html"
        if wants_erp_shell_tab_body(request)
        else "shipment/settings.html"
    )
    response = make_response(
        render_template(
            template_name,
            settings=settings,
            settings_version=_current_settings_version(),
            can_edit_erp=can_edit_erp(current_user),
        )
    )
    apply_erp_shell_fragment_headers(response, request)
    return response


@erp_shipment_bp.route("/api/erp/shipment-settings", methods=["GET"])
@login_required
def api_erp_shipment_settings_get():
    """출고 설정 목록 조회(optimistic-lock version 동봉 — 저장 시 If-Match 로 되보냄)."""
    settings = load_erp_shipment_settings()
    return jsonify({"success": True, "settings": settings, "version": _current_settings_version()})


@erp_shipment_bp.route("/api/erp/shipment-settings", methods=["POST"])
@login_required
def api_erp_shipment_settings_save():
    """출고 reference 리스트 저장(UPDATE_SHIPMENT_REFERENCE_LISTS command).

    exact four-list schema(construction_time/drawing_managers/measurement_managers/site_extra)
    를 SHIPMENT_REFERENCE 정책(STAFF+SHIPMENT 또는 ADMIN/MANAGER) 하에서 If-Match(version)+
    receipt/idempotency+audit 로 한 transaction 에 저장한다. ``construction_workers`` 는 이
    command 소관이 아니라 400 이고 기존 값은 보존된다(worker master 는 CREW-00).

    Body: four-list(+ ``settings_version``). optional 헤더 ``If-Match``·``Idempotency-Key``.
    """
    user, decision = _reference_policy_decision()
    if not decision.allowed:
        return jsonify({
            "success": False, "data": None,
            "error": decision.reason, "message": decision.reason, "code": decision.code,
        }), decision.status

    payload = request.get_json(silent=True) or {}
    if_match = _if_match_from_request(payload)
    body = {k: v for k, v in payload.items() if k != "settings_version"}
    idempotency_key = (request.headers.get("Idempotency-Key") or "").strip() or None

    db = get_db()
    try:
        result = update_shipment_reference_lists(
            db,
            actor_user_id=getattr(user, "id", None),
            payload=body,
            if_match_version=if_match,
            idempotency_key=idempotency_key,
        )
        db.commit()
    except ShipmentReferenceError as err:
        db.rollback()
        return jsonify({
            "success": False, "data": None, "error": str(err),
            "message": str(err), "code": err.error_code,
        }), err.status_code
    except Exception as exc:  # noqa: BLE001 - 상위에서 롤백 후 500 반환
        db.rollback()
        logger.exception("[SHIPMENT_REFERENCE] save error: %s", exc)
        return jsonify({"success": False, "data": None, "error": str(exc)}), 500

    if not result.replayed:
        _invalidate_reference_caches()
    resp = jsonify({
        "success": True,
        "data": {"version": result.version, "mutation_receipt": result.receipt_id},
    })
    resp.headers["Cache-Control"] = "private, no-store"
    return resp


def _invalidate_reference_caches() -> None:
    """reference 저장 후 파생 캐시 무효화(실패는 로그만; 저장 자체는 이미 커밋)."""
    try:
        from foms.services.common.dashboard_cache import (
            DASHBOARD_FAMILY_ORDERS,
            DASHBOARD_FAMILY_SHIPMENT,
            invalidate_dashboard_families,
        )

        invalidate_dashboard_families(DASHBOARD_FAMILY_SHIPMENT, DASHBOARD_FAMILY_ORDERS)
    except Exception:
        logger.warning("[SHIPMENT_REFERENCE] cache invalidate failed", exc_info=True)


def _shipment_edit_decision() -> tuple[Any, Any]:
    """SHIPMENT_EDIT(per-order 출고 쓰기) 권한을 payload 파싱 전에 in-handler 강제한다.

    before_request 가드가 꺼진 컨텍스트(TESTING 등)에서도 CS/SALES/SHIPMENT 또는
    ADMIN/MANAGER 만 통과하도록 :func:`evaluate_policy` 를 직접 적용한다.

    Returns:
        ``(user, Decision)`` 튜플.
    """
    user = get_user_by_id(session.get("user_id"))
    return user, evaluate_policy(POLICY_REGISTRY["SHIPMENT_EDIT"], user)


@erp_shipment_bp.route("/api/erp/shipment/update/<int:order_id>", methods=["POST"])
@login_required
@erp_edit_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def api_erp_shipment_update(order_id: int):
    """per-order 출고 설정 저장(UPDATE_SHIPMENT_SETTINGS canonical).

    exact non-assignment schema ``{site_extra,construction_time,vehicle,trip}`` 만
    저장하고 ``site_extra`` color 는 고정 enum 으로 정규화한다. ``construction_workers``
    등 assignment/crew 이름 배열·도면/측정 담당자는 쓰지 않는다(crew IDs via
    ``SET_INSTALLATION_CREW`` · auth via ASSIGNMENT command — name-array/auth/AS info
    direct write 제거). 시공팀은 조회만 가능하다. If-Match(``settings_version``/헤더)로
    낙관적 concurrency 를 지키고 version/receipt/event 를 REV-00 로 한 tx 에 기록한다
    (blind overwrite 방지).

    Args:
        order_id: 대상 주문 id.

    Returns:
        성공 시 ``{success, data:{version, mutation_receipt}}``; 권한/충돌/부재는
        403/409/404 JSON.
    """
    current_user = getattr(g, "current_user", None)
    if current_user and getattr(current_user, "team", None) == "CONSTRUCTION":
        return jsonify({"success": False, "message": "시공팀은 출고 데이터를 수정할 수 없습니다."}), 403
    user, decision = _shipment_edit_decision()
    if not decision.allowed:
        return jsonify({
            "success": False, "data": None,
            "error": decision.reason, "message": decision.reason, "code": decision.code,
        }), decision.status

    payload = request.get_json(silent=True) or {}
    if_match = _if_match_from_request(payload)
    idempotency_key = (request.headers.get("Idempotency-Key") or "").strip() or None

    db = get_db()
    order = db.query(Order).filter(Order.id == order_id, Order.active_filter()).first()
    if not order:
        return jsonify({"success": False, "message": "주문을 찾을 수 없습니다."}), 404

    actor_id = getattr(user, "id", None)

    def _mutate(session_, orders):
        target = orders[0]
        target.structured_data = apply_shipment_settings(
            getattr(target, "structured_data", None), payload
        )
        flag_modified(target, "structured_data")
        target.structured_updated_at = now_utc_naive()
        session_.add(OrderEvent(
            order_id=target.id, event_type="SHIPMENT_SETTINGS_UPDATED",
            payload={"domain": "SHIPMENT_DOMAIN", "action": "UPDATE_SHIPMENT_SETTINGS",
                     "change_method": "API", "source_screen": "erp_shipment_dashboard"},
            created_by_user_id=actor_id,
        ))
        return {target.id: [f"ORDER_DETAIL:{target.id}", "ORDERS_INDEX"]}

    try:
        result = execute_order_mutation(
            db, actor_user_id=actor_id, policy_id="SHIPMENT_EDIT", order_ids=[order_id],
            expected_versions=({order_id: if_match} if if_match is not None else None),
            idempotency_key=idempotency_key,
            scope_hash=hashlib.sha256(f"shipment_update:{order_id}".encode()).hexdigest(),
            request_hash=hashlib.sha256(
                json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()
            ).hexdigest(),
            mutation=_mutate,
        )
        db.commit()
    except RevisionError as err:
        db.rollback()
        return jsonify({"success": False, "data": None, "error": str(err),
                        "message": str(err), "code": err.error_code}), err.status_code
    except Exception as exc:
        db.rollback()
        logger.exception("[ERP_SHIPMENT] 업데이트 오류: %s", exc)
        return jsonify({"success": False, "message": str(exc)}), 500

    resource = (result.body.get("resources") or [{}])[0]
    resp = jsonify({"success": True, "data": {
        "version": resource.get("resulting_version"),
        "mutation_receipt": result.read_receipt_id,
    }})
    resp.headers["Cache-Control"] = "private, no-store"
    return resp
