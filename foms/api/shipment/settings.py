"""
ERP 출고 설정 페이지 및 API. (Phase 4-2)
erp.py에서 분리. 서비스는 foms/services/erp_shipment_settings 사용.
"""

import datetime
import logging

from flask import Blueprint, g, jsonify, make_response, render_template, request
from sqlalchemy.orm.attributes import flag_modified

from foms.web.auth import login_required, role_required
from db import get_db
from foms.services.channel_event_payloads import build_shipment_update_payload
from foms.services.erp_permissions import can_edit_erp, erp_edit_required
from foms.services.erp_shipment_settings import (
    load_erp_shipment_settings,
    normalize_erp_shipment_workers,
    normalize_measurement_managers,
    save_erp_shipment_settings,
)
from foms.services.jobs.queue import enqueue_channeltalk_push
from models import Order

from foms.services.common.erp_shell_http import apply_erp_shell_fragment_headers, wants_erp_shell_tab_body

logger = logging.getLogger(__name__)
erp_shipment_bp = Blueprint("erp_shipment", __name__)


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
            can_edit_erp=can_edit_erp(current_user),
        )
    )
    apply_erp_shell_fragment_headers(response, request)
    return response


@erp_shipment_bp.route("/api/erp/shipment-settings", methods=["GET"])
@login_required
def api_erp_shipment_settings_get():
    """출고 설정 목록 조회."""
    settings = load_erp_shipment_settings()
    return jsonify({"success": True, "settings": settings})


@erp_shipment_bp.route("/api/erp/shipment-settings", methods=["POST"])
@login_required
@erp_edit_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def api_erp_shipment_settings_save():
    """출고 설정 저장."""
    try:
        payload = request.get_json(silent=True) or {}
        current = load_erp_shipment_settings()
        for key in ("construction_time", "drawing_manager", "measurement_manager", "construction_workers", "site_extra"):
            if key in payload and isinstance(payload[key], list):
                if key == "construction_workers":
                    current[key] = normalize_erp_shipment_workers(payload[key])
                elif key == "measurement_manager":
                    current[key] = normalize_measurement_managers(payload[key])
                elif key == "site_extra":
                    cleaned = []
                    for value in payload[key]:
                        if isinstance(value, dict):
                            text_value = str(value.get("text", "")).strip()
                        else:
                            text_value = str(value).strip()
                        if text_value:
                            cleaned.append(text_value)
                    current[key] = cleaned
                else:
                    current[key] = [str(value).strip() for value in payload[key] if str(value).strip()]
        if save_erp_shipment_settings(current):
            return jsonify({"success": True})
        return jsonify({"success": False, "message": "저장 실패"}), 500
    except Exception as exc:
        return jsonify({"success": False, "message": str(exc)}), 500


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
        before_shipment = dict(structured_data.get("shipment") or {})
        actor = getattr(g, "current_user", None)
        actor_name = getattr(actor, "name", None) or getattr(actor, "username", None)

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

        structured_data["shipment"] = shipment
        setattr(order, "structured_data", structured_data)
        setattr(order, "structured_updated_at", datetime.datetime.now())
        flag_modified(order, "structured_data")

        from foms.services.channel_delivery import mark_order_updated_for_channel

        delivery_payload = build_shipment_update_payload(before_shipment, shipment, actor_name=actor_name)
        delivery_id = mark_order_updated_for_channel(
            order,
            delivery_payload.get("event_type", "shipment_updated"),
            payload=delivery_payload,
        )

        db.commit()
        if delivery_id:
            enqueue_channeltalk_push(delivery_id)
        return jsonify({"success": True})
    except Exception as exc:
        db.rollback()
        logger.exception("[ERP_SHIPMENT] 업데이트 오류: %s", exc)
        return jsonify({"success": False, "message": str(exc)}), 500
