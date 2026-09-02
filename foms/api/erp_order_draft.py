"""OrderDraft autosave API for mobile new-order wizard (P1-03)."""

from __future__ import annotations

from foms.services.datetime_kst import now_utc_naive
import copy
import re
from typing import Any

from flask import Blueprint, jsonify, request, session
from sqlalchemy.orm import Session

from db import get_db
from foms.services.feature_flags import env_bool, wizard_new_order_enabled
from foms.api.files.routes import build_file_view_url
from foms.services.order_draft_attachments import (
    draft_attachment_folder,
    promote_draft_attachments,
    validate_draft_attachment_upload,
)
from foms.services.order_draft_service import (
    SEND_KIND_ALIMTALK,
    SEND_KIND_CHANNEL_MEASURE,
    OrderDraftConflictError,
    delete_draft,
    draft_to_api_dict,
    format_updated_at,
    get_draft,
    get_draft_send_history,
    upsert_draft,
    validate_draft_payload,
)
from foms.services.storage import get_storage
from foms.services.datetime_kst import get_today_kst, now_kst
from foms.services.orders.estimate_defaults import (
    ERP_DRAFT_PLACEHOLDER_CUSTOMER,
    ERP_DRAFT_PLACEHOLDER_PHONE,
    ERP_DRAFT_PLACEHOLDER_PRODUCT,
)
from foms.services.orders.construction_type import normalize_regional_construction_type
from foms.services.orders.initial_workflow_stage import resolve_initial_workflow_stage
from foms.services.orders.order_create import create_order
from foms.services.orders.status_constants import STATUS
from foms.services.sidefx_outbox import enqueue_side_effect
from foms.web.auth import log_access, login_required, role_required
from foms.services.audit_message_display import describe_order_action
from foms.services.orders.audit_order_context import order_audit_context

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


def _draft_flags(data: dict[str, Any]) -> dict[str, Any]:
    """draft_v1.data.flags 를 정규화한다(주문 구분: 지방주문·라홈시스템·긴급).

    Args:
        data: draft_v1 payload 의 data 객체.

    Returns:
        {"regional_order": bool, "regional_construction_type": str,
         "factory2": bool, "urgent": bool, "urgent_reason": str}
        — 지방주문이 아니면 구분은 빈 문자열, 긴급이 아니면 사유는 빈 문자열.
    """
    raw = data.get("flags") if isinstance(data.get("flags"), dict) else {}
    regional = bool(raw.get("regional_order"))
    urgent = bool(raw.get("urgent"))
    return {
        "regional_order": regional,
        "regional_construction_type": (
            normalize_regional_construction_type(raw.get("regional_construction_type")) or ""
        )
        if regional
        else "",
        "factory2": bool(raw.get("factory2")),
        "urgent": urgent,
        "urgent_reason": str(raw.get("urgent_reason") or "").strip() if urgent else "",
    }


def _draft_load_date(data: dict[str, Any], flags: dict[str, Any]) -> str:
    """지방주문 상차일(YYYY-MM-DD)을 뽑는다.

    Args:
        data: draft_v1 payload 의 data 객체.
        flags: :func:`_draft_flags` 결과.

    Returns:
        지방주문이고 값이 있으면 상차일 문자열, 아니면 빈 문자열.
    """
    if not flags.get("regional_order"):
        return ""
    schedule = data.get("schedule") if isinstance(data.get("schedule"), dict) else {}
    return str(schedule.get("load_date") or "").strip()


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
    # 상차일은 지방주문 전용 — 비지방 주문에 남은 값이 흘러들지 않게 여기서 잘라낸다.
    load_date = (
        str(schedule_in.get("load_date") or "").strip()
        if bool((data.get("flags") or {}).get("regional_order"))
        else ""
    )
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

    # flags.urgent 는 sync_erp_flat_columns 가 order.erp_urgent 로, factory2 는
    # 대시보드 배지(라홈시스템)가 읽는 canonical 키다. 지방주문은 Order 컬럼이라 여기 없다.
    flags = _draft_flags(data)
    structured["flags"] = {
        "urgent": flags["urgent"],
        "urgent_reason": flags["urgent_reason"],
        "factory2": flags["factory2"],
    }

    deposit_amount = _parse_money_amount(data.get("deposit"))
    items_total = _items_total_from_draft_items(items)
    # 제품 가격 미입력(items_total=0) 단계에서 clamp 하면 예약금이 0으로 증발한다.
    if items_total > 0:
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


def _draft_attachment_tmp_keys(payload: Any, folder_prefix: str) -> list[str]:
    """Collect this draft's own uploaded attachment object keys from its payload.

    Only keys under ``folder_prefix`` (this draft's storage folder) are returned, so
    discard never targets a finalized order's or another draft's files.

    Args:
        payload: draft_v1 payload dict (``{"data": {"items": [...]}}``).
        folder_prefix: this draft's storage folder path plus trailing slash.

    Returns:
        List of draft-scoped tmp_key object keys (possibly empty).
    """
    data = payload.get("data") if isinstance(payload, dict) else None
    items = data.get("items") if isinstance(data, dict) else None
    keys: list[str] = []
    if not isinstance(items, list):
        return keys
    for item in items:
        if not isinstance(item, dict):
            continue
        attachments = item.get("attachments")
        if not isinstance(attachments, list):
            continue
        for raw in attachments:
            if not isinstance(raw, dict):
                continue
            tmp_key = str(raw.get("tmp_key") or "").strip()
            if tmp_key and tmp_key.startswith(folder_prefix):
                keys.append(tmp_key)
    return keys


def _enqueue_draft_attachment_cleanup(db: Any, uid: int, draft_key: str, row: Any) -> int:
    """Enqueue one STORAGE_DELETE outbox row per orphaned draft attachment (enqueue only).

    The wizard draft is a WIZARD_PENDING side-effect source; the actual R2 delete is
    performed by the SIDEFX worker's STORAGE_DELETE handler (not here).

    Args:
        db: business transaction session (caller owns commit).
        uid: owning user id (draft storage folder scope).
        draft_key: draft key (storage folder scope).
        row: the OrderDraft row being discarded.

    Returns:
        Number of STORAGE_DELETE rows enqueued.
    """
    folder_prefix = draft_attachment_folder(uid, draft_key) + "/"
    keys = _draft_attachment_tmp_keys(row.payload, folder_prefix)
    for index, object_key in enumerate(keys):
        enqueue_side_effect(
            db,
            source_domain="WIZARD_PENDING",
            source_id=row.id,
            effect_type="STORAGE_DELETE",
            payload={"object_key": object_key, "order_id": row.order_id},
            dedupe_key=f"order_draft:{row.id}:{index}",
            provider_idempotency_key=f"order_draft:{row.id}:{index}",
        )
    return len(keys)


@erp_order_draft_bp.route("/order-draft", methods=["DELETE"])
@login_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def api_delete_order_draft() -> tuple[Any, int]:
    """Discard a wizard draft: clean up its orphaned attachments and hard-delete the row.

    Enqueues a STORAGE_DELETE outbox row per draft-scoped attachment tmp_key, then
    hard-deletes only the draft row (finalized Orders are never touched) — all in one tx.
    """
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
    if row is not None:
        _enqueue_draft_attachment_cleanup(db, uid, draft_key, row)
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


def _inherit_draft_send_history(
    db: Session, *, draft_key: str, user_id: int, structured_data: dict[str, Any]
) -> dict[str, Any]:
    """초안 발송 이력을 **새 주문 sd 로 병합한 새 dict 를 돌려준다**(WIZ-SEND-01 D4').

    초안 행은 제출 끝에서 삭제되므로 여기서 옮기지 않으면 "등록 전에 보낸 안내"의 흔적이
    통째로 사라진다(화면 발송 흔적 칩·중복 발송 차단이 둘 다 이 키를 읽는다).

    **ORM 을 만지지 않는다.** ``create_order`` 앞에서 순수 dict 병합으로 끝내는 이유는
    두 가지다. (1) ``create_order`` 뒤에서 ``flag_modified(order, 'structured_data')`` 를
    하면 새 EXTERNAL order-mutation writer 로 잡혀 REV-99 릴리스 게이트가 red 가 된다.
    (2) ``_prepare_structured`` 는 sd 를 deepcopy 후 **가산만** 하므로 여기서 얹은 미지의
    최상위 키가 그대로 보존된다(foms/services/orders/order_create.py).

    이력은 성공·실패 구분 없이 **무변환 복사**한다. 멱등키를 새 주문 id 로 재작성하던
    옛 D4 는 폐기됐다 — 중복 차단은 이제 이력의 ``draft_schedule`` 서명이 담당한다
    (:func:`kakao_alimtalk._already_sent`).

    Args:
        db: 활성 세션(초안 이력 조회 전용 — 쓰기 없음).
        draft_key: 제출된 초안 키.
        user_id: 초안 소유자(= 제출자).
        structured_data: ``create_order`` 에 넘길 새 주문 structured_data.

    Returns:
        승계 키가 얹힌 structured_data. 승계할 이력이 없으면 인자를 그대로 돌려준다.
    """
    history = get_draft_send_history(db, draft_key=draft_key, user_id=user_id)
    if not history:
        return structured_data

    merged = copy.deepcopy(structured_data)
    for kind in (SEND_KIND_ALIMTALK, SEND_KIND_CHANNEL_MEASURE):
        entry = history.get(kind)
        if isinstance(entry, dict):
            merged[kind] = copy.deepcopy(entry)
    return merged


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

    # 지방주문은 구분(하우드/협력사)이 필수 — ERP 저장 경로(PUT /structured)와 동일 semantics.
    submit_flags = _draft_flags(data)
    if submit_flags["regional_order"] and not submit_flags["regional_construction_type"]:
        return (
            jsonify(
                {
                    "success": False,
                    "error": "VALIDATION",
                    "fields": ["지방주문 구분 (하우드/협력사)"],
                }
            ),
            400,
        )

    received_date = str(data.get("received_date") or get_today_kst().strftime("%Y-%m-%d"))
    received_time = now_kst().strftime("%H:%M")
    workflow_stage = (
        ((structured_data.get("workflow") or {}).get("stage") or "RECEIVED").strip()
    )
    order_status = workflow_stage if workflow_stage in STATUS else "RECEIVED"

    # 정본 승격: raw Order 조립 대신 ORDER-CREATE-01 create_order 를 경유한다 —
    # version=1·SALES owner 배정·ORDER_CREATED event·quest seed·item identity·server totals·
    # GEOCODE outbox 를 한 tx 에 원자 조립하고(호출자가 commit), postcommit 직접 지오코드는
    # 하지 않는다. self-service wizard 이므로 생성자(uid)가 owner 다.
    # WIZ-SEND-01 D4': 등록 전 초안에서 나간 발송 흔적을 새 주문 sd 에 미리 얹는다.
    # create_order 뒤 ORM 쓰기가 아니라 앞선 dict 병합이어야 REV-99 인벤토리가 안 흔들리고,
    # 초안 행을 삭제(delete_draft)하기 전에 이력을 읽는 순서도 여기서 보장된다.
    structured_data = _inherit_draft_send_history(
        db, draft_key=draft_key, user_id=uid, structured_data=structured_data
    )
    new_order = create_order(
        db,
        actor_user_id=uid,
        owner_user_id=uid,
        order_fields=dict(
            received_date=received_date,
            received_time=received_time,
            customer_name=cust_name,
            phone=cust_phone,
            address=addr,
            product=prod,
            options=None,
            notes=(structured_data.get("notes") or None),
            status=order_status,
            raw_order_text="",
            structured_confidence=None,
            is_regional=submit_flags["regional_order"],
            construction_type=submit_flags["regional_construction_type"] or None,
            # 지방 대시보드 "상차 예정 알림"이 읽는 SSOT 는 이 flat 컬럼이다.
            shipping_scheduled_date=_draft_load_date(data, submit_flags) or None,
        ),
        structured_data=structured_data,
        is_erp_order=True,
    )
    items_in = data.get("items") if isinstance(data.get("items"), list) else []
    promote_draft_attachments(
        db,
        order_id=new_order.id,
        items=items_in,
        user_id=uid,
    )
    delete_draft(db, uid, draft_key)
    submit_context = order_audit_context(new_order)
    log_access(
        describe_order_action(order_id=new_order.id, action="ORDER_DRAFT_SUBMITTED",
                              **submit_context),
        uid,
        auto_commit=False,
        action="ORDER_DRAFT_SUBMITTED", target_type="order", target_id=int(new_order.id),
        detail={"draft_key": draft_key, "items": len(items_in), **submit_context},
    )
    db.commit()
    return jsonify({"success": True, "data": {"order_id": new_order.id}}), 200
