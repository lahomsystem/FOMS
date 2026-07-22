"""OrderDraft autosave API for mobile new-order wizard (P1-03)."""

from __future__ import annotations

import copy
import datetime
from foms.services.datetime_kst import now_utc_naive
import re
from typing import Any

from flask import Blueprint, jsonify, request, session

from db import get_db
from foms.services.feature_flags import env_bool, wizard_new_order_enabled
from foms.api.files.routes import build_file_view_url
from foms.services.order_draft_attachments import (
    draft_attachment_folder,
    promote_draft_attachments,
    validate_draft_attachment_upload,
)
from foms.services.order_draft_service import (
    OrderDraftConflictError,
    delete_draft,
    draft_to_api_dict,
    format_updated_at,
    get_draft,
    upsert_draft,
    validate_draft_payload,
)
from foms.services.storage import get_storage
from foms.services.datetime_kst import get_today_kst, now_kst
from foms.services.erp_sync_columns import sync_erp_flat_columns
from foms.services.jobs.queue import enqueue_geocode_order_address
from foms.services.orders.estimate_defaults import (
    ERP_DRAFT_PLACEHOLDER_CUSTOMER,
    ERP_DRAFT_PLACEHOLDER_PHONE,
    ERP_DRAFT_PLACEHOLDER_PRODUCT,
)
from foms.services.orders.initial_workflow_stage import resolve_initial_workflow_stage
from foms.services.orders.status_constants import STATUS
from foms.web.auth import login_required, role_required
from models import Order

erp_order_draft_bp = Blueprint("erp_order_draft", __name__, url_prefix="/api/erp")


def _wizard_enabled() -> bool:
    # 렌더 게이트(order_pages.add_order)와 동일 기준: 전역 플래그 OR 모바일 v2 코호트.
    return wizard_new_order_enabled(_user_id())


def _require_wizard() -> tuple[Any, int] | None:
    if not _wizard_enabled():
        return jsonify({"success": False, "error": "WIZARD_DISABLED"}), 403
    return None


def _user_id() -> int | None:
    raw = session.get("user_id")
    return int(raw) if raw is not None else None


def _parse_money_amount(value: Any) -> int:
    """Parse wizard/ERP money fields (digits-only, dict amount/raw, numeric)."""
    if value is None:
        return 0
    if isinstance(value, dict):
        return _parse_money_amount(value.get("amount") or value.get("raw"))
    if isinstance(value, (int, float)):
        return max(0, int(value))
    digits = re.sub(r"[^0-9]", "", str(value))
    return int(digits) if digits else 0


def _items_total_from_draft_items(items: list[dict[str, Any]]) -> int:
    """Sum item price fields from wizard draft items."""
    total = 0
    for raw in items:
        if isinstance(raw, dict):
            total += _parse_money_amount(raw.get("price"))
    return total


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
    orderer = str(data.get("orderer") or "").strip()
    initial_stage = resolve_initial_workflow_stage(
        orderer=orderer,
        schedule=schedule_in,
        items=items_in if isinstance(items_in, list) else [],
    )
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
            "stage": initial_stage,
            "stage_updated_at": now_utc_naive().isoformat(),
        },
        "schedule": {},
        "meta": {"wizard_v1": True},
    }
    if orderer:
        # canonical: parties.orderer = {"name": ...} (erp_display/listing이 .name으로 읽음).
        structured.setdefault("parties", {})["orderer"] = {"name": orderer}
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
    load_date = str(schedule_in.get("load_date") or "").strip()
    if load_date:
        structured["schedule"]["load"] = {"date": load_date}
    sales_mgr = str(schedule_in.get("sales_manager") or "").strip()
    if sales_mgr:
        # parties.manager.name → sync_erp_flat_columns가 order.manager_name으로 동기화.
        structured.setdefault("parties", {}).setdefault("manager", {})["name"] = sales_mgr
    cons_mgr = str(schedule_in.get("construction_manager") or "").strip()
    if cons_mgr:
        structured.setdefault("assignments", {})["construction_manager"] = cons_mgr
    notes = str(schedule_in.get("notes") or "").strip()
    if notes:
        structured["notes"] = notes

    deposit_amount = _parse_money_amount(data.get("deposit"))
    items_total = _items_total_from_draft_items(items)
    deposit_amount = min(deposit_amount, items_total)
    balance_amount = max(0, items_total - deposit_amount)
    structured["payment"] = {"deposit": deposit_amount}
    structured["totals"] = {
        "items_total": items_total,
        "deposit_amount": deposit_amount,
        "discount_amount": 0,
        "balance_amount": balance_amount,
        "final_amount": balance_amount,
    }
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


@erp_order_draft_bp.route("/order-draft/attachments", methods=["POST"])
@login_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def api_upload_order_draft_attachment() -> tuple[Any, int]:
    """Upload a wizard draft attachment; returns tmp_key for draft payload."""
    blocked = _require_wizard()
    if blocked is not None:
        return blocked

    draft_key = str(request.form.get("draft_key") or "").strip()
    if not draft_key:
        return jsonify({"success": False, "error": "MISSING_KEY"}), 400

    uid = _user_id()
    if uid is None:
        return jsonify({"success": False, "error": "UNAUTHORIZED"}), 401

    if "file" not in request.files:
        return jsonify({"success": False, "error": "NO_FILE"}), 400
    file = request.files["file"]
    if not file or not file.filename:
        return jsonify({"success": False, "error": "NO_FILE"}), 400

    import os

    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)
    err = validate_draft_attachment_upload(file.filename, file_size)
    if err:
        return jsonify({"success": False, "error": err}), 400

    folder = draft_attachment_folder(uid, draft_key)
    storage = get_storage()
    result = storage.upload_file(file, file.filename, folder)
    if not result.get("success"):
        return (
            jsonify({"success": False, "error": result.get("message") or "UPLOAD_FAILED"}),
            500,
        )

    tmp_key = str(result.get("key") or "").strip()
    if not tmp_key:
        return jsonify({"success": False, "error": "UPLOAD_FAILED"}), 500

    return (
        jsonify(
            {
                "success": True,
                "data": {
                    "tmp_key": tmp_key,
                    "filename": file.filename,
                    "view_url": build_file_view_url(tmp_key),
                },
            }
        ),
        200,
    )


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
    # 사용자가 step4에서 확인한 현재 클라이언트 상태(body.payload)를 우선 사용한다.
    # debounce된 autosave가 아직 flush되지 않았어도 최신 입력이 유실되지 않도록 보장.
    # body.payload가 없거나 형식이 아니면 서버 저장 draft(row.payload)로 폴백.
    body_payload = body.get("payload")
    if isinstance(body_payload, dict) and isinstance(body_payload.get("data"), dict):
        payload = body_payload
    elif row and isinstance(row.payload, dict):
        payload = row.payload
    else:
        payload = None
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

    received_date = str(data.get("received_date") or get_today_kst().strftime("%Y-%m-%d"))
    received_time = now_kst().strftime("%H:%M")
    workflow_stage = (
        ((structured_data.get("workflow") or {}).get("stage") or "RECEIVED").strip()
    )
    order_status = workflow_stage if workflow_stage in STATUS else "RECEIVED"

    new_order = Order(
        received_date=received_date,
        received_time=received_time,
        customer_name=cust_name,
        phone=cust_phone,
        address=addr,
        product=prod,
        options=None,
        notes=(structured_data.get("notes") or None),
        status=order_status,
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
    items_in = data.get("items") if isinstance(data.get("items"), list) else []
    promote_draft_attachments(
        db,
        order_id=new_order.id,
        items=items_in,
        user_id=uid,
    )
    delete_draft(db, uid, draft_key)
    db.commit()
    enqueue_geocode_order_address(new_order.id)
    return jsonify({"success": True, "data": {"order_id": new_order.id}}), 200
