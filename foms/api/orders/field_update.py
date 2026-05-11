"""Field update handlers for the legacy orders blueprint."""

from __future__ import annotations

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
from foms.services.erp_sync_columns import sync_erp_flat_columns
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

        is_erp_order = is_erp_order_record(order)
        structured_data: dict[str, Any] = {}
        structured_changed = False
        if field == "as_completed_date" or is_erp_order or field in STRUCTURED_SYNC_FIELDS:
            structured_data = _load_order_structured_data_for_update(order)

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
            elif field in ("as_content", "as_content_2"):
                shipment = ensure_path(structured_data, "shipment")
                shipment[field] = value
                structured_changed = True

        if structured_changed:
            setattr(order, "structured_data", structured_data)
            flag_modified(order, "structured_data")
            sync_erp_flat_columns(order, structured_data)

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

        inv_fields = {
            "as_visit_date",
            "status",
            "address",
            "manager_name",
            "as_content",
            "as_content_2",
            "sales_delivery",
            "construction_workers",
        }
        if field in inv_fields or status_snapshot in ("AS", "AS_RECEIVED", "AS_COMPLETED"):
            try:
                from foms.services.common.dashboard_cache import invalidate_all_dashboard_slice_caches
                from foms.services.shipment_as_recommendation_cache import (
                    invalidate_shipment_as_recommendation_cache,
                )

                invalidate_all_dashboard_slice_caches()
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
