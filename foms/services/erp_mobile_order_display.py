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
from foms.services.order_event_display import (
    format_timeline_meta,
    translate_event_type_to_korean,
)

__all__ = [
    "stage_badge_modifier",
    "stage_badge_label",
    "product_subtitle_from_sd",
    "build_mobile_queue_order_row",
    "mobile_timeline_events",
    "mobile_attachment_items",
    "batch_resolve_queue_attachment_urls",
    "mobile_product_items",
    "mobile_amount_summary",
]

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


def mobile_product_items(sd: dict, *, limit: int = 8) -> list[dict[str, Any]]:
    """Product accordion rows for mobile order detail (C14 markup)."""
    items = sd.get("items") or []
    if not isinstance(items, list):
        return []
    rows: list[dict[str, Any]] = []
    for idx, raw in enumerate(items[:limit]):
        if not isinstance(raw, dict):
            continue
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
        rows.append(
            {
                "index": idx + 1,
                "title": str(name),
                "internal": raw.get("internal") or raw.get("interior") or "-",
                "color": raw.get("color") or "-",
                "option_detail": raw.get("option_detail") or raw.get("option") or "-",
                "handle": raw.get("handle") or "-",
                "misc": raw.get("misc") or raw.get("install_notes") or "-",
                "price_label": price_label,
                "summary": " · ".join(summary_bits) if summary_bits else str(name),
                "collapsed_default": idx > 0,
            }
        )
    return rows


def mobile_amount_summary(sd: dict) -> dict[str, Any]:
    """Amount KV block for mobile detail (items total + deposit when present)."""
    totals = sd.get("totals") if isinstance(sd.get("totals"), dict) else {}
    pricing = sd.get("pricing") if isinstance(sd.get("pricing"), dict) else {}
    items_total = erp_payment_amount_from_structured(sd)
    contract = pricing.get("contract_total") or pricing.get("total") or sd.get("contract_amount")
    deposit = totals.get("deposit_amount") or totals.get("deposit") or pricing.get("deposit")
    balance = pricing.get("balance") or totals.get("balance") or sd.get("balance")

    def _fmt(value) -> str | None:
        if value in (None, ""):
            return None
        try:
            return f"{int(float(value)):,}원"
        except (TypeError, ValueError):
            return str(value)

    items_label = f"{items_total:,}원" if items_total is not None else _fmt(contract) or "-"
    deposit_label = _fmt(deposit)
    balance_label = _fmt(balance)
    if balance_label is None and items_total is not None and deposit_label:
        try:
            dep_val = int(float(deposit))
            balance_label = f"{max(0, items_total - dep_val):,}원"
        except (TypeError, ValueError):
            balance_label = None
    return {
        "items_total_label": items_label,
        "deposit_label": deposit_label,
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


def build_mobile_queue_order_row(db, order) -> dict[str, Any]:
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
    quests = sd.get("quests") or []
    current_quest = None
    for q in quests:
        if isinstance(q, dict) and (q.get("status") or "").upper() != "DONE":
            current_quest = q
            break
    previews = batch_resolve_queue_attachment_urls(db, [order.id]).get(order.id, [])
    received = schedule.get("received") or {}

    return {
        "id": order.id,
        "customer_name": (parties.get("customer") or {}).get("name") or "-",
        "phone": (parties.get("customer") or {}).get("phone") or "-",
        "address": site.get("address_full") or site.get("address_main") or "-",
        "measurement_date": (schedule.get("measurement") or {}).get("date"),
        "construction_date": (schedule.get("construction") or {}).get("date"),
        "received_date": received.get("date") or getattr(order, "received_date", None),
        "manager_name": (parties.get("manager") or {}).get("name") or "-",
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
        "attachments": mobile_attachment_items(db, order.id),
        "timeline_events": mobile_timeline_events(db, order.id),
        "product_items": mobile_product_items(sd),
        "amount_summary": mobile_amount_summary(sd),
        "structured_data": sd,
        "current_quest": {"title": current_quest.get("title", "")} if current_quest else None,
    }
