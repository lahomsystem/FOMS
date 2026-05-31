"""OrderDraft autosave API for mobile new-order wizard (P1-03)."""

from __future__ import annotations

import copy
import datetime
from typing import Any

from flask import Blueprint, jsonify, request, session

from db import get_db
from foms.services.feature_flags import env_bool
from foms.services.order_draft_service import (
    OrderDraftConflictError,
    delete_draft,
    draft_to_api_dict,
    format_updated_at,
    get_draft,
    upsert_draft,
    validate_draft_payload,
)
from foms.services.erp_sync_columns import sync_erp_flat_columns
from foms.services.jobs.queue import enqueue_geocode_order_address
from foms.services.orders.estimate_defaults import (
    ERP_DRAFT_PLACEHOLDER_CUSTOMER,
    ERP_DRAFT_PLACEHOLDER_PHONE,
    ERP_DRAFT_PLACEHOLDER_PRODUCT,
)
from foms.web.auth import login_required, role_required
from models import Order

erp_order_draft_bp = Blueprint("erp_order_draft", __name__, url_prefix="/api/erp")


def _wizard_enabled() -> bool:
    return env_bool("FOMS_WIZARD_NEW_ORDER_ENABLED")


def _require_wizard() -> tuple[Any, int] | None:
    if not _wizard_enabled():
        return jsonify({"success": False, "error": "WIZARD_DISABLED"}), 403
    return None


def _user_id() -> int | None:
    raw = session.get("user_id")
    return int(raw) if raw is not None else None


def _draft_payload_to_structured(data: dict[str, Any]) -> dict[str, Any]:
    """Map draft_v1.data to ERP structured_data for order creation."""
    items_in = data.get("items") if isinstance(data.get("items"), list) else []
    items: list[dict[str, Any]] = []
    for raw in items_in:
        if not isinstance(raw, dict):
            continue
        spec_rows = raw.get("spec_rows") if isinstance(raw.get("spec_rows"), list) else []
        normalized_specs: list[dict[str, str]] = []
        for spec in spec_rows:
            if not isinstance(spec, dict):
                continue
            normalized_specs.append(
                {
                    "spec_width": str(spec.get("spec_width") or "").strip(),
                    "spec_depth": str(spec.get("spec_depth") or "").strip(),
                    "spec_height": str(spec.get("spec_height") or "").strip(),
                }
            )
        items.append(
            {
                "product_name": str(raw.get("product_name") or "").strip(),
                "spec_rows": normalized_specs,
                "internal": str(raw.get("internal") or "").strip(),
                "color": str(raw.get("color") or "").strip(),
                "option_detail": str(raw.get("option_detail") or "").strip(),
                "handle": str(raw.get("handle") or "").strip(),
                "misc": str(raw.get("misc") or "").strip(),
                "price": str(raw.get("price") or "").strip(),
                "measurement_date": str(raw.get("measurement_date") or "").strip(),
                "construction_date": str(raw.get("construction_date") or "").strip(),
                "extra_input": str(raw.get("extra_input") or "").strip(),
                "attachments": raw.get("attachments") if isinstance(raw.get("attachments"), list) else [],
            }
        )

    schedule_in = data.get("schedule") if isinstance(data.get("schedule"), dict) else {}
    structured: dict[str, Any] = {
        "parties": {
            "customer": {
                "name": str(data.get("customer_name") or "").strip(),
                "phone": str(data.get("phone") or "").strip(),
            }
        },
        "site": {
            "address_full": str(data.get("address") or "").strip(),
        },
        "items": items,
        "workflow": {
            "stage": "RECEIVED",
            "stage_updated_at": datetime.datetime.now().isoformat(),
        },
        "schedule": {},
        "meta": {"wizard_v1": True},
    }
    if data.get("orderer"):
        structured.setdefault("parties", {})["orderer"] = str(data.get("orderer")).strip()
    meas = str(schedule_in.get("measurement_date") or "").strip()
    cons = str(schedule_in.get("construction_date") or "").strip()
    if meas:
        structured["schedule"]["measurement"] = {"date": meas}
        if schedule_in.get("measurement_time"):
            structured["schedule"]["measurement"]["time"] = str(schedule_in.get("measurement_time")).strip()
    if cons:
        structured["schedule"]["construction"] = {"date": cons}
        if schedule_in.get("construction_time"):
            structured["schedule"]["construction"]["time"] = str(schedule_in.get("construction_time")).strip()
    return structured


def _first_product_name(structured_data: dict[str, Any]) -> str:
    items = structured_data.get("items") or []
    if not isinstance(items, list):
        return ""
    for item in items:
        if isinstance(item, dict):
            name = (item.get("product_name") or "").strip()
            if name:
                return name
    return ""


@erp_order_draft_bp.route("/order-draft", methods=["GET"])
@login_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def api_get_order_draft() -> tuple[Any, int]:
    """Return saved draft for recovery toast on re-entry."""
    blocked = _require_wizard()
    if blocked is not None:
        return blocked

    draft_key = (request.args.get("key") or "").strip()
    if not draft_key:
        return jsonify({"success": False, "error": "MISSING_KEY"}), 400

    uid = _user_id()
    if uid is None:
        return jsonify({"success": False, "error": "UNAUTHORIZED"}), 401

    db = get_db()
    row = get_draft(db, uid, draft_key)
    if row is None:
        return jsonify({"success": True, "draft": None}), 200
    return jsonify({"success": True, "draft": draft_to_api_dict(row)}), 200


@erp_order_draft_bp.route("/order-draft", methods=["PUT"])
@login_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def api_put_order_draft() -> tuple[Any, int]:
    """Idempotent autosave with optional X-If-Match optimistic lock."""
    blocked = _require_wizard()
    if blocked is not None:
        return blocked

    body = request.get_json(silent=True) or {}
    draft_key = str(body.get("draft_key") or body.get("key") or "").strip()
    if not draft_key:
        return jsonify({"success": False, "error": "MISSING_KEY"}), 400

    uid = _user_id()
    if uid is None:
        return jsonify({"success": False, "error": "UNAUTHORIZED"}), 401

    try:
        step = int(body.get("step") or 1)
        payload = validate_draft_payload(body.get("payload") or body)
    except (TypeError, ValueError) as exc:
        return jsonify({"success": False, "error": str(exc)}), 400

    if_match = request.headers.get("X-If-Match")
    order_id = body.get("order_id")
    order_id_int = int(order_id) if order_id is not None and str(order_id).isdigit() else None

    db = get_db()
    try:
        row = upsert_draft(
            db,
            user_id=uid,
            draft_key=draft_key,
            step=step,
            payload=payload,
            if_match=if_match,
            order_id=order_id_int,
        )
        db.commit()
    except OrderDraftConflictError as exc:
        db.rollback()
        return (
            jsonify(
                {
                    "success": False,
                    "error": "CONFLICT",
                    "current": exc.current,
                }
            ),
            409,
        )
    except ValueError as exc:
        db.rollback()
        return jsonify({"success": False, "error": str(exc)}), 400

    return (
        jsonify(
            {
                "success": True,
                "updated_at": format_updated_at(row.updated_at),
                "step": row.step,
            }
        ),
        200,
    )


@erp_order_draft_bp.route("/order-draft", methods=["DELETE"])
@login_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def api_delete_order_draft() -> tuple[Any, int]:
    """Discard draft after successful order save."""
    blocked = _require_wizard()
    if blocked is not None:
        return blocked

    draft_key = (request.args.get("key") or "").strip()
    if not draft_key:
        return jsonify({"success": False, "error": "MISSING_KEY"}), 400

    uid = _user_id()
    if uid is None:
        return jsonify({"success": False, "error": "UNAUTHORIZED"}), 401

    db = get_db()
    delete_draft(db, uid, draft_key)
    db.commit()
    return jsonify({"success": True}), 200


@erp_order_draft_bp.route("/order-draft/submit", methods=["POST"])
@login_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def api_submit_order_draft() -> tuple[Any, int]:
    """Create ERP order from wizard draft payload and delete draft."""
    blocked = _require_wizard()
    if blocked is not None:
        return blocked

    body = request.get_json(silent=True) or {}
    draft_key = str(body.get("draft_key") or body.get("key") or "").strip()
    if not draft_key:
        return jsonify({"success": False, "error": "MISSING_KEY"}), 400

    uid = _user_id()
    if uid is None:
        return jsonify({"success": False, "error": "UNAUTHORIZED"}), 401

    db = get_db()
    row = get_draft(db, uid, draft_key)
    payload = row.payload if row and isinstance(row.payload, dict) else body.get("payload")
    if not isinstance(payload, dict):
        return jsonify({"success": False, "error": "NO_DRAFT"}), 400

    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    structured_data = _draft_payload_to_structured(data)
    cust_name = (
        ((structured_data.get("parties") or {}).get("customer") or {}).get("name") or ""
    ).strip()
    cust_phone = (
        ((structured_data.get("parties") or {}).get("customer") or {}).get("phone") or ""
    ).strip()
    addr = (
        (structured_data.get("site") or {}).get("address_full") or ""
    ).strip()
    prod = _first_product_name(structured_data)

    missing: list[str] = []
    if not cust_name or cust_name == ERP_DRAFT_PLACEHOLDER_CUSTOMER:
        missing.append("고객명")
    if not cust_phone or cust_phone == ERP_DRAFT_PLACEHOLDER_PHONE:
        missing.append("전화번호")
    if not addr or addr == "-":
        missing.append("주소")
    if not prod or prod == ERP_DRAFT_PLACEHOLDER_PRODUCT:
        missing.append("제품명")
    if missing:
        return jsonify({"success": False, "error": "VALIDATION", "fields": missing}), 400

    received_date = str(data.get("received_date") or datetime.datetime.now().strftime("%Y-%m-%d"))
    received_time = datetime.datetime.now().strftime("%H:%M")

    new_order = Order(
        received_date=received_date,
        received_time=received_time,
        customer_name=cust_name,
        phone=cust_phone,
        address=addr,
        product=prod,
        options=None,
        notes=None,
        status="RECEIVED",
        is_erp_order=True,
        raw_order_text="",
        structured_data=copy.deepcopy(structured_data),
        structured_schema_version=1,
        structured_confidence=None,
        structured_updated_at=datetime.datetime.now(),
    )
    db.add(new_order)
    db.flush()
    sync_erp_flat_columns(new_order, structured_data)
    delete_draft(db, uid, draft_key)
    db.commit()
    enqueue_geocode_order_address(new_order.id)
    return jsonify({"success": True, "data": {"order_id": new_order.id}}), 200
