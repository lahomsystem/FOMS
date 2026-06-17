"""ERP mobile v2 display helpers — mockup queue cards & order detail."""

from __future__ import annotations

from typing import Any

from foms.api.files.routes import build_file_download_url, build_file_view_url
from foms.services.erp_display import (
    _ensure_dict,
    _erp_alerts,
    _erp_get_stage,
    _erp_has_media,
    erp_payment_amount_from_structured,
)
from foms.services.erp_policy import STAGE_LABELS, STAGE_NAME_TO_CODE
from foms.services.erp_quest_display import build_current_quest_payload, load_assignee_user_map
from foms.services.estimate_service import (
    _balance_after_payments,
    _extract_deposit_amount,
    _extract_discount_amount,
    resolve_manager_phone_from_measurement_settings,
)
from foms.services.order_event_display import (
    format_timeline_meta,
    translate_event_type_to_korean,
)

__all__ = [
    "stage_badge_modifier",
    "stage_badge_label",
    "resolve_queue_card_schedule",
    "format_queue_card_schedule_summary",
    "product_subtitle_from_sd",
    "build_mobile_queue_order_row",
    "resolve_manager_phone_for_queue",
    "mobile_timeline_events",
    "mobile_attachment_items",
    "mobile_attachment_categories",
    "batch_resolve_queue_attachment_urls",
    "mobile_product_items",
    "mobile_amount_summary",
]

_MEASUREMENT_PRIORITY_STAGE_CODES = frozenset(
    {"RECEIVED", "HAPPYCALL", "MEASURE", "DRAWING", "CONFIRM"}
)
_CONSTRUCTION_PRIORITY_STAGE_CODES = frozenset(
    {"PRODUCTION", "CONSTRUCTION", "CONSTRUCTING", "SHIPMENT"}
)

_MOBILE_ATTACHMENT_CATEGORY_ORDER: tuple[tuple[str, str], ...] = (
    ("measurement", "실측"),
    ("drawing", "도면"),
    ("construction", "시공"),
    ("as", "AS"),
)

_IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")
_MAX_QUEUE_PREVIEW_COUNT = 3



def mobile_timeline_events(db, order_id: int, *, limit: int = 12) -> list[dict[str, Any]]:
    """Recent OrderEvent rows for mobile detail timeline (newest first)."""
    try:
        from models import OrderEvent

        rows = (
            db.query(OrderEvent)
            .filter(OrderEvent.order_id == order_id)
            .order_by(OrderEvent.created_at.desc())
            .limit(limit)
            .all()
        )
    except Exception:
        return []

    items: list[dict[str, Any]] = []
    for ev in rows:
        payload = ev.payload if isinstance(ev.payload, dict) else {}
        event_type = ev.event_type or ""
        created_by = getattr(ev, "created_by", None)
        actor_name = str(created_by.name) if created_by and getattr(created_by, "name", None) else None
        items.append(
            {
                "title": translate_event_type_to_korean(event_type),
                "meta": format_timeline_meta(
                    event_type,
                    payload,
                    actor_name=actor_name,
                    created_at=getattr(ev, "created_at", None),
                ),
                "done": True,
            }
        )
    return items


def _is_image_filename(filename: str | None) -> bool:
    name = (filename or "").strip().lower()
    return bool(name) and name.endswith(_IMAGE_SUFFIXES)


def _attachment_thumbnail_url(attachment) -> str | None:
    """Small generated thumb (typically max 300px) — queue cards only."""
    thumb_key = (getattr(attachment, "thumbnail_key", None) or "").strip()
    if thumb_key:
        return build_file_view_url(thumb_key)
    return None


def _attachment_full_view_url(attachment) -> str | None:
    """Full-resolution image view URL for grid tiles and modal preview."""
    storage_key = (getattr(attachment, "storage_key", None) or "").strip()
    if not storage_key:
        return None
    file_type = (getattr(attachment, "file_type", None) or "").strip().lower()
    filename = getattr(attachment, "filename", None)
    if file_type == "image" or _is_image_filename(filename):
        return build_file_view_url(storage_key)
    return None


def _attachment_image_url(attachment) -> str | None:
    """Resolve preview URL for queue cards (prefer thumbnail for bandwidth)."""
    return _attachment_thumbnail_url(attachment) or _attachment_full_view_url(attachment)


def batch_resolve_queue_attachment_urls(
    db,
    order_ids: list[int],
    *,
    limit_per_order: int = _MAX_QUEUE_PREVIEW_COUNT,
) -> dict[int, list[str]]:
    """Batch-resolve image preview URLs for mobile v2 queue cards."""
    if not order_ids:
        return {}
    try:
        from models import OrderAttachment

        rows = (
            db.query(OrderAttachment)
            .filter(OrderAttachment.order_id.in_(order_ids))
            .order_by(OrderAttachment.order_id.asc(), OrderAttachment.created_at.desc())
            .all()
        )
    except Exception:
        return {}

    out: dict[int, list[str]] = {oid: [] for oid in order_ids}
    for att in rows:
        oid = int(att.order_id)
        bucket = out.get(oid)
        if bucket is None or len(bucket) >= limit_per_order:
            continue
        url = _attachment_image_url(att)
        if url:
            bucket.append(url)
    return out


def _group_attachments_by_item_index(
    attachments: list[dict[str, Any]],
    *,
    item_count: int,
) -> tuple[dict[int, list[dict[str, Any]]], list[dict[str, Any]]]:
    """Split attachment rows into per-item buckets and common (unlinked) rows."""
    by_index: dict[int, list[dict[str, Any]]] = {}
    common: list[dict[str, Any]] = []
    for att in attachments:
        raw_idx = att.get("item_index")
        if raw_idx is None:
            common.append(att)
            continue
        try:
            idx = int(raw_idx)
        except (TypeError, ValueError):
            common.append(att)
            continue
        if idx < 0 or idx >= item_count:
            common.append(att)
            continue
        by_index.setdefault(idx, []).append(att)
    if item_count == 1:
        by_index.setdefault(0, []).extend(common)
        common = []
    return by_index, common


def mobile_attachment_categories(attachments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Non-empty attachment buckets by ERP category (mobile detail tabs)."""
    buckets: dict[str, list[dict[str, Any]]] = {key: [] for key, _ in _MOBILE_ATTACHMENT_CATEGORY_ORDER}
    for att in attachments:
        cat = str(att.get("category") or "measurement").strip().lower()
        if cat not in buckets:
            cat = "measurement"
        buckets[cat].append(att)
    return [
        {"key": key, "label": label, "items": buckets[key]}
        for key, label in _MOBILE_ATTACHMENT_CATEGORY_ORDER
        if buckets[key]
    ]


def mobile_product_items(
    sd: dict,
    attachments: list[dict[str, Any]] | None = None,
    *,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """Product accordion rows for mobile order detail (C14 markup)."""
    items = sd.get("items") or []
    if not isinstance(items, list):
        return []
    raw_items = [raw for raw in items[:limit] if isinstance(raw, dict)]
    item_count = len(raw_items)
    collapse_all = item_count > 1
    att_by_index, _common = _group_attachments_by_item_index(
        attachments or [],
        item_count=item_count,
    )
    rows: list[dict[str, Any]] = []
    for idx, raw in enumerate(raw_items):
        name = raw.get("product_name") or raw.get("name") or f"항목 {idx + 1}"
        spec = " × ".join(
            str(raw.get(k) or "").strip()
            for k in ("spec_width", "spec_depth", "spec_height", "width", "depth", "height")
            if raw.get(k)
        )
        price_raw = raw.get("price")
        price_label = "-"
        if price_raw not in (None, ""):
            try:
                price_label = f"{int(float(price_raw)):,}원"
            except (TypeError, ValueError):
                price_label = str(price_raw)
        summary_bits = [p for p in (spec, price_label if price_label != "-" else None) if p]
        size_label = spec or str(
            raw.get("standard") or raw.get("spec") or raw.get("규격") or ""
        ).strip()
        rows.append(
            {
                "index": idx + 1,
                "title": str(name),
                "size": size_label or "-",
                "internal": raw.get("internal") or raw.get("interior") or "-",
                "color": raw.get("color") or "-",
                "option_detail": raw.get("option_detail") or raw.get("option") or "-",
                "handle": raw.get("handle") or "-",
                "misc": raw.get("misc") or raw.get("install_notes") or "-",
                "price_label": price_label,
                "summary": " · ".join(summary_bits) if summary_bits else str(name),
                "collapsed_default": collapse_all,
                "attachments": att_by_index.get(idx, []),
                "attachment_categories": mobile_attachment_categories(att_by_index.get(idx, [])),
            }
        )
    return rows


def mobile_amount_summary(sd: dict) -> dict[str, Any]:
    """Amount KV block for mobile detail (items total, deposit, discount, balance)."""
    totals = sd.get("totals") if isinstance(sd.get("totals"), dict) else {}
    pricing = sd.get("pricing") if isinstance(sd.get("pricing"), dict) else {}
    items_total = erp_payment_amount_from_structured(sd)
    contract = pricing.get("contract_total") or pricing.get("total") or sd.get("contract_amount")
    deposit_val = _extract_deposit_amount(sd)
    discount_val = _extract_discount_amount(sd)
    final_raw = totals.get("final_amount")
    if final_raw is None:
        final_raw = totals.get("balance_amount")
    legacy_deposit = totals.get("deposit_amount") or totals.get("deposit") or pricing.get("deposit")
    legacy_balance = pricing.get("balance") or totals.get("balance") or sd.get("balance")

    def _fmt(value) -> str | None:
        if value in (None, ""):
            return None
        try:
            return f"{int(float(value)):,}원"
        except (TypeError, ValueError):
            return str(value)

    items_label = f"{items_total:,}원" if items_total is not None else _fmt(contract) or "-"
    deposit_label = _fmt(deposit_val) if deposit_val else _fmt(legacy_deposit)
    discount_label = _fmt(discount_val) if discount_val else None
    balance_label = _fmt(final_raw)
    if balance_label is None and items_total is not None:
        balance_label = f"{_balance_after_payments(items_total, deposit_val, discount_val):,}원"
    elif balance_label is None:
        balance_label = _fmt(legacy_balance)
    return {
        "items_total_label": items_label,
        "deposit_label": deposit_label,
        "discount_label": discount_label,
        "balance_label": balance_label,
    }


def mobile_attachment_items(db, order_id: int, *, limit: int = 8) -> list[dict[str, Any]]:
    """Attachment summary rows for mobile detail attach grid."""
    try:
        from models import OrderAttachment

        rows = (
            db.query(OrderAttachment)
            .filter(OrderAttachment.order_id == order_id)
            .order_by(OrderAttachment.created_at.desc())
            .limit(limit)
            .all()
        )
    except Exception:
        return []

    category_labels = {
        "measurement": "실측",
        "drawing": "도면",
        "construction": "시공",
        "as": "AS",
    }
    items: list[dict[str, Any]] = []
    for att in rows:
        cat = (att.category or "measurement").lower()
        label = att.filename or category_labels.get(cat, cat)
        thumb_url = _attachment_thumbnail_url(att)
        view_url = _attachment_full_view_url(att)
        storage_key = (getattr(att, "storage_key", None) or "").strip()
        download_url = build_file_download_url(storage_key) if storage_key else None
        items.append(
            {
                "label": label,
                "category": cat,
                "id": att.id,
                "item_index": getattr(att, "item_index", None),
                "thumb_url": thumb_url,
                "view_url": view_url,
                "download_url": download_url,
            }
        )
    return items


def stage_badge_modifier(stage: str | None) -> str:
    """Map ERP stage label/code to foms-stage-badge BEM modifier suffix."""
    if not stage:
        return "--received"
    code = STAGE_NAME_TO_CODE.get(stage, stage)
    mapping = {
        "RECEIVED": "--received",
        "HAPPYCALL": "--happycall",
        "MEASURE": "--measure",
        "DRAWING": "--drawing",
        "CONFIRM": "--confirm",
        "PRODUCTION": "--production",
        "SHIPMENT": "--shipment",
        "CONSTRUCTION": "--construction",
        "CS": "--cs",
        "COMPLETED": "--completed",
    }
    return mapping.get(code, "--received")


def stage_badge_label(stage: str | None) -> str:
    """Short badge label for queue card header."""
    if not stage:
        return "-"
    code = STAGE_NAME_TO_CODE.get(stage, stage)
    short = {
        "RECEIVED": "접수",
        "HAPPYCALL": "해피콜",
        "MEASURE": "실측",
        "DRAWING": "도면",
        "CONFIRM": "컨펌",
        "PRODUCTION": "생산",
        "SHIPMENT": "출고",
        "CONSTRUCTION": "시공",
        "CS": "AS",
        "COMPLETED": "완료",
    }
    return short.get(code, STAGE_LABELS.get(code, stage))


def _normalize_queue_stage_code(stage: str | None, stage_code: str | None) -> str:
    """
    Resolve canonical workflow code for queue-card schedule priority.

    Supports ERP codes, Korean stage labels, and sub-stages (시공대기, 제작중).
    Display sub-stage prefixes win over canonical ``stage_code`` so production/
    construction queue cards and search summaries stay aligned.
    """
    raw_stage = str(stage or "").strip()
    if raw_stage.startswith("시공"):
        return "CONSTRUCTION"
    if raw_stage.startswith("제작"):
        return "PRODUCTION"
    if raw_stage.startswith("출고"):
        return "SHIPMENT"

    raw_code = str(stage_code or "").strip()
    if raw_code and raw_code.upper() not in {"", "ERPORDER", "ERPBETA"}:
        return raw_code.upper()

    if not raw_stage:
        return ""

    mapped = STAGE_NAME_TO_CODE.get(raw_stage)
    if mapped:
        return mapped

    upper_stage = raw_stage.upper()
    if upper_stage in STAGE_LABELS:
        return upper_stage

    return upper_stage


def _normalize_schedule_date(value: str | None) -> str | None:
    """Return trimmed schedule text or None when empty/placeholder."""
    text = str(value or "").strip()
    if not text or text in {"-", "상담"}:
        return None
    return text


def resolve_queue_card_schedule(
    *,
    stage: str | None = None,
    stage_code: str | None = None,
    measurement_date: str | None = None,
    construction_date: str | None = None,
) -> dict[str, str | None]:
    """
    Pick one schedule row for mobile v2 queue cards (SSOT).

    Production/construction stages prefer 시공일; measure/confirm prefer 실측일.
    Falls back to whichever date exists. Matches legacy v1 card intent with
    Korean sub-stage labels (시공대기, 제작대기).
    """
    code = _normalize_queue_stage_code(stage, stage_code)
    meas = _normalize_schedule_date(measurement_date)
    cons = _normalize_schedule_date(construction_date)

    if code in _CONSTRUCTION_PRIORITY_STAGE_CODES:
        if cons:
            return {"label": "시공", "value": cons}
        if meas:
            return {"label": "실측", "value": meas}
    if code in _MEASUREMENT_PRIORITY_STAGE_CODES:
        if meas:
            return {"label": "실측", "value": meas}
        if cons:
            return {"label": "시공", "value": cons}

    if meas:
        return {"label": "실측", "value": meas}
    if cons:
        return {"label": "시공", "value": cons}
    return {"label": None, "value": None}


def format_queue_card_schedule_summary(schedule: dict[str, str | None]) -> str:
    """Compact ``실측 2026-06-16`` string for search overlay subtitles."""
    label = schedule.get("label")
    value = schedule.get("value")
    if label and value:
        return f"{label} {value}"
    return ""


def product_subtitle_from_sd(sd: dict) -> str | None:
    """First product line summary for queue card subtitle."""
    items = sd.get("items") or []
    if not items:
        return None
    first = items[0] if isinstance(items[0], dict) else {}
    name = first.get("product_name") or first.get("name") or ""
    if not name:
        return None
    if len(items) > 1:
        return f"{name} 외 {len(items) - 1}건"
    return str(name)


def _attachment_count(db, order_id: int) -> int:
    """Count attachments for a single order."""
    try:
        from models import OrderAttachment
        from sqlalchemy import func

        row = (
            db.query(func.count(OrderAttachment.id))
            .filter(OrderAttachment.order_id == order_id)
            .scalar()
        )
        return int(row or 0)
    except Exception:
        return 0


def resolve_manager_phone_for_queue(
    parties: dict[str, Any] | None,
    *,
    manager_name: str = "",
    order=None,
) -> str:
    """Resolve manager tel: target — structured_data phone, then 출고 설정 실측담당자 목록."""
    parties = parties or {}
    manager = parties.get("manager") or {}
    name = (
        (manager_name if manager_name and manager_name != "-" else "")
        or manager.get("name")
        or getattr(order, "manager_name", None)
        or ""
    )
    phone = str(manager.get("phone") or "").strip()
    resolved = resolve_manager_phone_from_measurement_settings(str(name).strip())
    return resolved or phone


def build_mobile_queue_order_row(db, order, current_user=None) -> dict[str, Any]:
    """Build a dashboard-compatible dict for mobile v2 queue/detail templates."""
    sd = _ensure_dict(getattr(order, "structured_data", None))
    cnt = _attachment_count(db, order.id)
    stage = _erp_get_stage(order, sd)
    stage_key = stage if isinstance(stage, str) else ""
    stage_code = STAGE_NAME_TO_CODE.get(stage_key, stage_key)
    alerts = _erp_alerts(order, sd, cnt)
    parties = sd.get("parties") or {}
    site = sd.get("site") or {}
    schedule = sd.get("schedule") or {}
    user_map = load_assignee_user_map(db, sd)
    current_quest_payload = build_current_quest_payload(
        sd=sd,
        stage=stage,
        stage_code=stage_code,
        order=order,
        current_user=current_user,
        user_map=user_map,
    )
    previews = batch_resolve_queue_attachment_urls(db, [order.id]).get(order.id, [])
    received = schedule.get("received") or {}
    attachments = mobile_attachment_items(db, order.id, limit=50)
    product_items = mobile_product_items(sd, attachments)
    _, common_attachments = _group_attachments_by_item_index(
        attachments,
        item_count=len([i for i in (sd.get("items") or []) if isinstance(i, dict)]),
    )
    common_attachment_categories = mobile_attachment_categories(common_attachments)

    return {
        "id": order.id,
        "customer_name": (parties.get("customer") or {}).get("name") or "-",
        "phone": (parties.get("customer") or {}).get("phone") or "-",
        "address": site.get("address_full") or site.get("address_main") or "-",
        "measurement_date": (schedule.get("measurement") or {}).get("date"),
        "construction_date": (schedule.get("construction") or {}).get("date"),
        "received_date": received.get("date") or getattr(order, "received_date", None),
        "manager_name": (parties.get("manager") or {}).get("name") or getattr(order, "manager_name", None) or "-",
        "manager_phone": resolve_manager_phone_for_queue(parties, order=order),
        "orderer_name": (parties.get("orderer") or {}).get("name") or None,
        "stage": stage,
        "stage_code": stage_code,
        "stage_badge_modifier": stage_badge_modifier(stage),
        "stage_badge_label": stage_badge_label(stage),
        "product_subtitle": product_subtitle_from_sd(sd),
        "alerts": alerts,
        "has_media": _erp_has_media(order, cnt),
        "attachments_count": cnt,
        "attachment_previews": previews,
        "attachments": attachments,
        "common_attachments": common_attachments,
        "common_attachment_categories": common_attachment_categories,
        "timeline_events": mobile_timeline_events(db, order.id),
        "product_items": product_items,
        "amount_summary": mobile_amount_summary(sd),
        "structured_data": sd,
        "current_quest": current_quest_payload,
    }
