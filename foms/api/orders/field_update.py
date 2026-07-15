"""Field update handlers for the legacy orders blueprint."""

from __future__ import annotations

import copy
import datetime
from typing import Any, Callable

from flask import current_app, jsonify, request, session
from sqlalchemy.orm.attributes import flag_modified

from foms.web.auth import get_user_by_id, log_access
from foms.services.orders.status_constants import STATUS
from db import get_db
from foms.services.as_content_safety import (
    load_structured_data_dict_or_raise,
    sanitize_as_content_html,
)
from foms.services.erp_order_flags import is_erp_order_record
from foms.services.erp_permissions import can_edit_erp
from foms.services.erp_display import _normalize_date_to_yyyymmdd
from foms.services.erp_sync_columns import sync_erp_flat_columns
from foms.services.orders.construction_type import normalize_regional_construction_type
from models import Order

ORDER_UPDATE_ALLOWED_FIELDS = [
    "manager_name",
    "scheduled_date",
    "status",
    "shipping_scheduled_date",
    "completion_date",
    "measurement_completed",
    "regional_sales_order_upload",
    "regional_blueprint_sent",
    "regional_order_upload",
    "regional_cargo_sent",
    "regional_construction_info_sent",
    "as_received_date",
    "as_completed_date",
    "as_visit_date",
    "as_content",
    "as_content_2",
    "as_pending",
    "as_blueprint",
    "sales_delivery",
    "measurement_date",
    "regional_memo",
    "construction_type",
    "is_cabinet",
    "cabinet_status",
    "shipping_fee",
    "construction_workers",
]

STRUCTURED_SYNC_FIELDS = {
    "as_visit_date",
    "as_content",
    "as_content_2",
    "as_pending",
    "as_blueprint",
    "sales_delivery",
    "construction_workers",
}


def ensure_path(parent: dict[str, Any], key: str) -> dict[str, Any]:
    """Return a mutable child mapping, creating it when missing."""
    if key not in parent or not isinstance(parent.get(key), dict):
        parent[key] = {}
    child = parent[key]
    if not isinstance(child, dict):
        parent[key] = {}
        child = parent[key]
    return child


def _clear_as_pending_if_both_as_dates_empty(order: Order, structured_data: dict[str, Any]) -> bool:
    """접수일과 schedule.as_visit.date가 모두 비면 미결 플래그를 끈다.

    미결 버튼이 방문일 기준이지만, 접수·방문이 모두 소거되면 AS 접수 화면으로
    원상복구해야 하므로 JSONB 진실값(shipment.as_pending)을 직접 정리한다.
    """
    shipment = structured_data.get("shipment") or {}
    if not isinstance(shipment, dict) or shipment.get("as_pending") is not True:
        return False
    received = getattr(order, "as_received_date", None)
    if str(received or "").strip():
        return False
    schedule = structured_data.get("schedule")
    visit_raw = ""
    if isinstance(schedule, dict):
        visit_block = schedule.get("as_visit")
        if isinstance(visit_block, dict):
            visit_raw = visit_block.get("date")
    if str(visit_raw or "").strip():
        return False
    if str(getattr(order, "as_visit_date", None) or "").strip():
        return False
    ensure_path(structured_data, "shipment")["as_pending"] = False
    return True


def _coerce_bool_value(value: Any) -> bool:
    """Interpret form and JSON boolean values consistently."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in ("1", "true", "yes", "y", "on")


def _normalize_construction_workers_value(value: Any) -> list[str]:
    """Normalize comma/newline/list construction worker input into unique names."""
    if isinstance(value, list):
        raw_values = value
    else:
        raw_values = str(value or "").replace("\n", ",").split(",")

    workers: list[str] = []
    for item in raw_values:
        if isinstance(item, dict):
            raw_name = item.get("name") or item.get("text") or item.get("value") or ""
        else:
            raw_name = item
        name = str(raw_name or "").strip()
        if name and name not in workers:
            workers.append(name)
    return workers


def _load_order_structured_data_for_update(order: Order) -> dict[str, Any]:
    """Load order.structured_data without silently dropping malformed content."""
    try:
        return load_structured_data_dict_or_raise(getattr(order, "structured_data", None))
    except ValueError as exc:
        raise ValueError(
            f"structured_data를 안전하게 불러올 수 없어 저장을 중단했습니다: {exc}"
        ) from exc


def _build_order_update_response(
    order: Order,
    field: str,
    fallback_value: Any,
    structured_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the legacy response payload for update_order_field."""
    shipment = (structured_data.get("shipment") or {}) if structured_data else {}
    schedule = (structured_data.get("schedule") or {}) if structured_data else {}
    as_visit = (schedule.get("as_visit") or {}) if isinstance(schedule, dict) else {}

    if field in ("as_content", "as_content_2"):
        normalized_value = shipment.get(field) or ""
    elif field == "as_pending":
        normalized_value = shipment.get("as_pending") is True
    elif field == "as_blueprint":
        normalized_value = shipment.get("as_blueprint") is True
    elif field == "sales_delivery":
        normalized_value = shipment.get("sales_delivery") is True
    elif field == "construction_workers":
        normalized_value = _normalize_construction_workers_value(
            shipment.get("construction_workers")
        )
    elif field == "as_visit_date":
        normalized_value = as_visit.get("date") or ""
    else:
        normalized_value = getattr(order, field, fallback_value)

    status = getattr(order, "status", None)
    status_label = STATUS.get(status, status) if isinstance(status, str) else status
    return {
        "success": True,
        "message": "정보가 업데이트되었습니다.",
        "normalized_value": normalized_value if normalized_value is not None else "",
        "status": status,
        "status_label": status_label,
        "as_completed_date": getattr(order, "as_completed_date", None) or "",
        "as_visit_date": getattr(order, "as_visit_date", None) or "",
        "as_pending": shipment.get("as_pending") is True,
        "as_blueprint": shipment.get("as_blueprint") is True,
        "sales_delivery": shipment.get("sales_delivery") is True,
        "construction_workers": _normalize_construction_workers_value(
            shipment.get("construction_workers")
        ),
    }


def update_order_field_response(
    *,
    clean_dict_like_name: Callable[[Any], str],
):
    """Update legacy order fields while keeping the ERP Beta sync contract intact."""
    db = get_db()
    data = request.get_json() or {}

    order_id = data.get("order_id")
    field = data["field"] if "field" in data else data.get("field_name")
    value = data["value"] if "value" in data else data.get("new_value")

    order = db.query(Order).filter_by(id=order_id).first()
    if not order:
        return jsonify({"success": False, "message": "유효하지 않은 주문입니다."}), 404

    status_snapshot = getattr(order, "status", None)

    user = get_user_by_id(session.get("user_id")) if session.get("user_id") else None
    if not user:
        return jsonify({"success": False, "message": "로그인이 필요합니다."}), 401

    date_fields = ("measurement_date", "scheduled_date")
    if field in date_fields:
        if not can_edit_erp(user):
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "실측일/시공일 수정 권한이 없습니다. (영업, 라홈, 하우드, CS팀만 가능)",
                    }
                ),
                403,
            )
    elif user.role not in ("ADMIN", "MANAGER", "STAFF"):
        return jsonify({"success": False, "message": "이 작업을 수행할 권한이 없습니다."}), 403

    if field not in ORDER_UPDATE_ALLOWED_FIELDS:
        return (
            jsonify({"success": False, "message": f"허용되지 않은 필드입니다: {field}"}),
            400,
        )

    try:
        if field in ("as_content", "as_content_2"):
            value = sanitize_as_content_html(value)
        if field == "construction_type":
            normalized_construction_type = normalize_regional_construction_type(value)
            if str(value or "").strip() and not normalized_construction_type:
                raise ValueError("시공 구분은 하우드 시공 또는 협력사 시공만 가능합니다.")
            if not getattr(order, "is_regional", False) and normalized_construction_type:
                raise ValueError("비지방 주문에는 지방주문 구분을 저장할 수 없습니다.")
            if getattr(order, "is_regional", False) and not normalized_construction_type:
                raise ValueError("지방주문 구분(하우드/협력사)을 선택해주세요.")
            value = normalized_construction_type or None

        is_erp_order = is_erp_order_record(order)
        structured_data: dict[str, Any] = {}
        structured_changed = False
        old_sd_snapshot: dict[str, Any] = {}
        if field == "as_completed_date" or is_erp_order or field in STRUCTURED_SYNC_FIELDS:
            structured_data = _load_order_structured_data_for_update(order)
            old_sd_snapshot = copy.deepcopy(structured_data)

        old_value = getattr(order, field, None)
        if field == "as_visit_date":
            pass
        elif field in (
            "as_content",
            "as_content_2",
            "as_pending",
            "as_blueprint",
            "sales_delivery",
            "construction_workers",
        ):
            pass
        else:
            setattr(order, field, value)

        if field == "as_completed_date":
            shipment = ensure_path(structured_data, "shipment")
            if value:
                setattr(order, "status", "AS_COMPLETED")
                if is_erp_order:
                    workflow = ensure_path(structured_data, "workflow")
                    workflow["stage"] = "AS_COMPLETED"
                    workflow["stage_updated_at"] = datetime.datetime.now().isoformat()
                    structured_changed = True
                if shipment.get("as_pending"):
                    shipment["as_pending"] = False
                    structured_changed = True
            else:
                setattr(order, "status", "AS_RECEIVED")
                if is_erp_order:
                    workflow = ensure_path(structured_data, "workflow")
                    workflow["stage"] = "AS_RECEIVED"
                    workflow["stage_updated_at"] = datetime.datetime.now().isoformat()
                    structured_changed = True

        if is_erp_order or field in (
            "as_content",
            "as_content_2",
            "as_visit_date",
            "as_pending",
            "as_blueprint",
            "sales_delivery",
        ):
            if field == "as_pending":
                shipment = ensure_path(structured_data, "shipment")
                shipment["as_pending"] = _coerce_bool_value(value)
                structured_changed = True
            elif field == "as_blueprint":
                shipment = ensure_path(structured_data, "shipment")
                shipment["as_blueprint"] = _coerce_bool_value(value)
                structured_changed = True
            elif field == "sales_delivery":
                shipment = ensure_path(structured_data, "shipment")
                shipment["sales_delivery"] = _coerce_bool_value(value)
                structured_changed = True
            elif field == "construction_workers":
                shipment = ensure_path(structured_data, "shipment")
                shipment["construction_workers"] = _normalize_construction_workers_value(value)
                structured_changed = True
            elif field == "manager_name":
                clean_value = clean_dict_like_name(value)
                setattr(order, "manager_name", clean_value)
                parties = ensure_path(structured_data, "parties")
                manager = ensure_path(parties, "manager")
                manager["name"] = clean_value
                structured_changed = True
            elif field == "measurement_date":
                schedule = ensure_path(structured_data, "schedule")
                measurement = ensure_path(schedule, "measurement")
                measurement["date"] = value
                structured_changed = True
            elif field == "scheduled_date":
                schedule = ensure_path(structured_data, "schedule")
                construction = ensure_path(schedule, "construction")
                construction["date"] = value
                structured_changed = True
            elif field == "as_visit_date":
                schedule = ensure_path(structured_data, "schedule")
                as_visit = ensure_path(schedule, "as_visit")
                as_visit["date"] = value
                structured_changed = True
                trimmed = str(value or "").strip()
                if trimmed:
                    setattr(order, "as_visit_date", _normalize_date_to_yyyymmdd(trimmed))
                else:
                    setattr(order, "as_visit_date", None)
            elif field in ("as_content", "as_content_2"):
                shipment = ensure_path(structured_data, "shipment")
                shipment[field] = value
                structured_changed = True

        if is_erp_order and field in ("as_received_date", "as_visit_date"):
            if _clear_as_pending_if_both_as_dates_empty(order, structured_data):
                structured_changed = True

        if structured_changed:
            drawing_notif = None
            drawing_notif_created = False
            if field in ("measurement_date", "scheduled_date", "construction_type") or field == "address":
                try:
                    from foms.services.notifications.drawing_order_change import (
                        apply_drawing_order_change_alert,
                    )
                    drawing_notif, drawing_notif_created = apply_drawing_order_change_alert(
                        db,
                        order,
                        old_sd_snapshot,
                        structured_data,
                        actor_user_id=getattr(user, "id", None),
                        actor_name=getattr(user, "name", None) or session.get("username") or "SYSTEM",
                        old_notes=getattr(order, "notes", None),
                        new_notes=getattr(order, "notes", None),
                        old_is_regional=getattr(order, "is_regional", None),
                        new_is_regional=getattr(order, "is_regional", None),
                        old_construction_type=(
                            old_value if field == "construction_type" else getattr(order, "construction_type", None)
                        ),
                        new_construction_type=getattr(order, "construction_type", None),
                    )
                except Exception:
                    current_app.logger.warning(
                        "drawing order-change alert failed on field_update",
                        exc_info=True,
                    )
            setattr(order, "structured_data", structured_data)
            flag_modified(order, "structured_data")
            sync_erp_flat_columns(order, structured_data)
        else:
            drawing_notif = None
            drawing_notif_created = False

        if field == "status":
            log_access(
                f"자가실측 주문 #{order.id} 상태 변경: '{old_value}' → '{value}'",
                session["user_id"],
                auto_commit=False,
            )
        else:
            log_access(
                f"주문 #{order.id}의 '{field}' 필드를 '{value}'(으)로 변경",
                session["user_id"],
                auto_commit=False,
            )

        db.commit()

        if structured_changed:
            try:
                from foms.services.notifications.drawing_order_change import (
                    finalize_drawing_order_change_alert,
                )
                finalize_drawing_order_change_alert(
                    db, drawing_notif, created_new=drawing_notif_created
                )
            except Exception:
                current_app.logger.warning(
                    "drawing order-change finalize failed on field_update",
                    exc_info=True,
                )

        inv_fields = {
            "as_visit_date",
            "status",
            "address",
            "manager_name",
            "as_content",
            "as_content_2",
            "sales_delivery",
            "construction_workers",
            "construction_type",
            # 날짜 필드: 캐시 DTO가 날짜 기준으로 구성되는 대시보드(실측 main_rows
            # order_ids, 출고/시공 버킷, 히스토리)가 있어 편집 시 무효화 필수.
            "measurement_date",
            "scheduled_date",
            "shipping_scheduled_date",
            "completion_date",
        }
        # AS 관련 상태에서의 편집은 status_snapshot 기준으로도 무효화가 걸린다.
        as_context = status_snapshot in ("AS", "AS_RECEIVED", "AS_COMPLETED")
        if field in inv_fields or as_context:
            try:
                from foms.services.common.dashboard_cache import (
                    DASHBOARD_FAMILY_CONSTRUCTION,
                    DASHBOARD_FAMILY_HISTORY,
                    DASHBOARD_FAMILY_MEASUREMENT,
                    DASHBOARD_FAMILY_SHIPMENT,
                    invalidate_all_dashboard_slice_caches,
                    invalidate_order_dashboard_families,
                )
                from foms.services.shipment_as_recommendation_cache import (
                    invalidate_shipment_as_recommendation_cache,
                )

                # Tier C(단일 필드): status 변경/AS 문맥은 탭 이동을 유발할 수 있어 broad.
                # 그 외 필드는 orders + 주문 현재 단계 family + 필드가 캐시 DTO에
                # 등장하는 family(extra)만 무효화한다(근거: 각 read-model DTO 정독).
                if field == "status" or as_context:
                    invalidate_all_dashboard_slice_caches()
                else:
                    extras_by_field = {
                        # 출고 대시보드 DTO(aggregates·AS 추천 행)가 읽는 필드
                        "as_visit_date": (DASHBOARD_FAMILY_SHIPMENT,),
                        "as_content": (DASHBOARD_FAMILY_SHIPMENT,),
                        "as_content_2": (DASHBOARD_FAMILY_SHIPMENT,),
                        "sales_delivery": (DASHBOARD_FAMILY_SHIPMENT,),
                        "construction_workers": (DASHBOARD_FAMILY_SHIPMENT,),
                        # 날짜 필드 → 날짜 기준 DTO를 가진 family
                        "measurement_date": (DASHBOARD_FAMILY_MEASUREMENT,),
                        "scheduled_date": (
                            DASHBOARD_FAMILY_SHIPMENT,
                            DASHBOARD_FAMILY_CONSTRUCTION,
                        ),
                        "shipping_scheduled_date": (DASHBOARD_FAMILY_SHIPMENT,),
                        "completion_date": (DASHBOARD_FAMILY_HISTORY,),
                    }
                    extra = extras_by_field.get(field, ())
                    invalidate_order_dashboard_families(order, extra=extra)
                invalidate_shipment_as_recommendation_cache(reason=f"field_update:{field}")
            except Exception:
                current_app.logger.warning(
                    "[AS-REC] post field_update cache invalidate failed",
                    exc_info=True,
                )

        return jsonify(_build_order_update_response(order, field, value, structured_data))
    except ValueError as exc:
        db.rollback()
        current_app.logger.warning(f"주문 #{order_id} 필드 업데이트 중단: {str(exc)}")
        return jsonify({"success": False, "message": str(exc)}), 409
    except Exception as exc:
        db.rollback()
        current_app.logger.error(f"주문 #{order_id} 필드 업데이트 실패: {str(exc)}")
        return (
            jsonify({"success": False, "message": f"오류 발생: {str(exc)}"}),
            500,
        )


__all__ = [
    "ORDER_UPDATE_ALLOWED_FIELDS",
    "STRUCTURED_SYNC_FIELDS",
    "ensure_path",
    "update_order_field_response",
]
