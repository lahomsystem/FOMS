"""
ERP 출고 설정 페이지 및 API. (Phase 4-2)
erp.py에서 분리. 서비스는 foms/services/erp_shipment_settings 사용.
"""

import datetime
import logging
from typing import Optional

from flask import Blueprint, g, jsonify, make_response, render_template, request, session
from sqlalchemy.orm.attributes import flag_modified

from foms.web.auth import get_user_by_id, login_required, role_required
from db import get_db
from foms.services.erp_permissions import can_edit_erp, erp_edit_required
from foms.services.erp_shipment_settings import (
    ERP_SHIPMENT_SETTINGS_KEY,
    load_erp_shipment_settings,
)
from foms.services.orders.order_mutation_policy import POLICY_REGISTRY, evaluate_policy
from foms.services.shipment_reference import (
    SHIPMENT_REFERENCE_POLICY_ID,
    ShipmentReferenceError,
    update_shipment_reference_lists,
)
from models import Order, SystemSetting

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


@erp_shipment_bp.route("/api/erp/shipment/update/<int:order_id>", methods=["POST"])
@login_required
@erp_edit_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def api_erp_shipment_update(order_id):
    """출고 대시보드 업데이트. 시공팀은 수정 불가(조회만)."""
    current_user = getattr(g, "current_user", None)
    if current_user and getattr(current_user, "team", None) == "CONSTRUCTION":
        return jsonify({"success": False, "message": "시공팀은 출고 데이터를 수정할 수 없습니다."}), 403
    try:
        db = get_db()
        order = db.query(Order).filter(Order.id == order_id, Order.active_filter()).first()
        if not order:
            return jsonify({"success": False, "message": "주문을 찾을 수 없습니다."}), 404

        payload = request.get_json(silent=True) or {}
        structured_data = dict(getattr(order, "structured_data", None) or {})

        if "shipment" not in structured_data:
            structured_data["shipment"] = {}
        shipment = structured_data["shipment"]

        if "site_extra" in payload:
            site_extra = payload.get("site_extra")
            if isinstance(site_extra, list):
                normalized = []
                for value in site_extra:
                    if isinstance(value, dict):
                        text_value = (value.get("text") or "").strip()
                        color_value = (value.get("color") or "black").strip() or "black"
                        if text_value:
                            normalized.append({"text": text_value, "color": color_value})
                    else:
                        text_value = str(value).strip()
                        if text_value:
                            normalized.append({"text": text_value, "color": "black"})
                shipment["site_extra"] = normalized
            else:
                shipment["site_extra"] = []
        if "construction_time" in payload:
            shipment["construction_time"] = str(payload.get("construction_time", "")).strip()
        if "drawing_manager" in payload:
            shipment["drawing_manager"] = str(payload.get("drawing_manager", "")).strip()
        if "drawing_managers" in payload:
            drawing_managers = payload.get("drawing_managers")
            shipment["drawing_managers"] = (
                [str(value).strip() for value in drawing_managers if str(value).strip()]
                if isinstance(drawing_managers, list)
                else []
            )
        if "construction_workers" in payload:
            workers = payload.get("construction_workers")
            shipment["construction_workers"] = (
                [str(value).strip() for value in workers if str(value).strip()]
                if isinstance(workers, list)
                else []
            )
        if "vehicle" in payload:
            shipment["vehicle"] = str(payload.get("vehicle", "")).strip()
        if "trip" in payload:
            shipment["trip"] = str(payload.get("trip", "")).strip()

        structured_data["shipment"] = shipment
        setattr(order, "structured_data", structured_data)
        setattr(order, "structured_updated_at", datetime.datetime.now())
        flag_modified(order, "structured_data")

        db.commit()
        return jsonify({"success": True})
    except Exception as exc:
        db.rollback()
        logger.exception("[ERP_SHIPMENT] 업데이트 오류: %s", exc)
        return jsonify({"success": False, "message": str(exc)}), 500
