"""ERP mobile v2 display helpers — mockup queue cards & order detail."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from foms.api.files.routes import build_file_download_url, build_file_view_url
from foms.services.erp_display import (
    _ensure_dict,
    _erp_alerts,
    _erp_get_stage,
    _erp_has_media,
    erp_payment_amount_from_structured,
    erp_shipping_price_from_structured,
)
from foms.services.erp_policy import STAGE_LABELS, STAGE_NAME_TO_CODE
from foms.services.erp_quest_display import (
    build_current_quest_payload,
    load_assignee_user_map,
    load_assignee_user_map_batch,
    resolve_order_role_assignees,
)
from foms.services.estimate_service import (
    _balance_after_payments,
    _extract_deposit_amount,
    _extract_discount_amount,
    _extract_free_input_amount,
    build_measurement_manager_phone_map,
    resolve_manager_phone_from_map,
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
    "MobileQueueBatchContext",
    "build_mobile_queue_batch_context",
    "resolve_manager_phone_for_queue",
    "mobile_timeline_events",
    "mobile_attachment_items",
    "mobile_attachment_categories",
    "batch_resolve_queue_attachment_urls",
    "batch_resolve_queue_attachment_preview_items",
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
# Soft cap: gallery must hydrate all previewable images (card chrome still shows 5+N).
# Align with detail `_batch_mobile_attachment_items` default (50).
_MAX_QUEUE_PREVIEW_COUNT = 50
_QUEUE_DRAWING_CATEGORIES = frozenset({"drawing"})



def _mobile_timeline_event_dict(ev) -> dict[str, Any]:
    """OrderEvent → 모바일 타임라인 항목 dict (per-row·batch 공용)."""
    payload = ev.payload if isinstance(ev.payload, dict) else {}
    event_type = ev.event_type or ""
    created_by = getattr(ev, "created_by", None)
    actor_name = str(created_by.name) if created_by and getattr(created_by, "name", None) else None
    return {
        "title": translate_event_type_to_korean(event_type),
        "meta": format_timeline_meta(
            event_type,
            payload,
            actor_name=actor_name,
            created_at=getattr(ev, "created_at", None),
        ),
        "done": True,
    }


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

    return [_mobile_timeline_event_dict(ev) for ev in rows]


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


def _queue_preview_item_from_attachment(att) -> dict[str, str] | None:
    """Thumb + full view + download for one queue-card attachment."""
    view_url = _attachment_full_view_url(att)
    if not view_url:
        return None
    thumb_url = _attachment_thumbnail_url(att) or view_url
    filename = (getattr(att, "filename", None) or "").strip()
    cat = (getattr(att, "category", None) or "measurement").strip().lower()
    category_labels = {
        "measurement": "실측",
        "drawing": "도면",
        "construction": "시공",
        "as": "AS",
    }
    label = filename or category_labels.get(cat, "첨부")
    storage_key = (getattr(att, "storage_key", None) or "").strip()
    download_url = build_file_download_url(storage_key) if storage_key else view_url
    return {
        "thumb": thumb_url,
        "view": view_url,
        "download": download_url,
        "label": label,
    }


def batch_resolve_queue_attachment_preview_items(
    db,
    order_ids: list[int],
    *,
    limit_per_order: int = _MAX_QUEUE_PREVIEW_COUNT,
    categories: frozenset[str] | None = None,
) -> dict[int, list[dict[str, str]]]:
    """Batch-resolve thumb + full-view preview items for mobile v2 queue cards.

    Args:
        categories: When set, only include attachments whose category is in the set
            (e.g. ``frozenset({\"drawing\"})`` for 시공/출고 도면 전용 미리보기).
    """
    if not order_ids:
        return {}
    try:
        from models import OrderAttachment
        from sqlalchemy import func

        q = db.query(OrderAttachment).filter(OrderAttachment.order_id.in_(order_ids))
        if categories is not None:
            q = q.filter(
                func.lower(OrderAttachment.category).in_(sorted(categories))
            )
        rows = q.order_by(
            OrderAttachment.order_id.asc(), OrderAttachment.created_at.desc()
        ).all()
    except Exception:
        return {}

    out: dict[int, list[dict[str, str]]] = {oid: [] for oid in order_ids}
    for att in rows:
        if categories is not None:
            cat = (getattr(att, "category", None) or "").strip().lower()
            if cat not in categories:
                continue
        oid = int(att.order_id)
        bucket = out.get(oid)
        if bucket is None or len(bucket) >= limit_per_order:
            continue
        item = _queue_preview_item_from_attachment(att)
        if item:
            bucket.append(item)
    return out


def batch_resolve_queue_attachment_urls(
    db,
    order_ids: list[int],
    *,
    limit_per_order: int = _MAX_QUEUE_PREVIEW_COUNT,
) -> dict[int, list[str]]:
    """Batch-resolve full-view image URLs for mobile v2 queue cards (legacy list API)."""
    items_by_order = batch_resolve_queue_attachment_preview_items(
        db, order_ids, limit_per_order=limit_per_order
    )
    return {
        oid: [item["view"] for item in items if item.get("view")]
        for oid, items in items_by_order.items()
    }


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
    """Amount KV block for mobile detail (출고가, deposit, balance).

    읽기전용 요약이므로 표시 금액은 출고가(shipping_price = 품목합 + 자유입력 - 할인)로
    통일하고, 별도 '할인' 라인은 출고가에 흡수해 숨긴다(discount_label=None). 잔금은
    기존 SSOT 계산을 그대로 유지한다(품목합 기준 재파생, 값 불변).

    잔금 표시는 서버 파생식(orders/structured_form_projection.recompute_totals 의
    ``max(0, ...)``)과 **같은 클램프 규칙**으로 0 에서 자른다 — 품목금액 0 · 예약금만 있는
    주문(네이버 승격)에서 저장 totals 나 legacy 값이 음수여도 화면에 음수 잔금을 내보내지
    않는다.

    **다만 파생 소스는 완료 대시보드·이력 시트와 다르다.** 그 둘은 저장 totals 를 무시하고
    매번 재파생하는데, 여기서는 저장된 ``totals.final_amount``/``balance_amount`` 를 먼저
    쓰고 없을 때만 재파생한다. totals 가 낡은 주문에서는 두 화면의 잔금이 갈릴 수 있다 —
    같아진 것은 클램프 규칙뿐이다.

    Args:
        sd: 주문 structured_data(JSONB) 딕셔너리.

    Returns:
        모바일 상세 금액 KV 블록 dict(출고가/예약금/할인/잔금 라벨).
    """
    totals = sd.get("totals") if isinstance(sd.get("totals"), dict) else {}
    pricing = sd.get("pricing") if isinstance(sd.get("pricing"), dict) else {}
    items_total = erp_payment_amount_from_structured(sd)
    shipping_price = erp_shipping_price_from_structured(sd)
    contract = pricing.get("contract_total") or pricing.get("total") or sd.get("contract_amount")
    deposit_val = _extract_deposit_amount(sd)
    discount_val = _extract_discount_amount(sd)
    free_input_val = _extract_free_input_amount(sd)
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

    def _fmt_balance(value) -> str | None:
        """잔금 라벨: 숫자로 읽히면 0 에서 클램프해 포맷한다(음수 잔금 표기 차단)."""
        if value in (None, ""):
            return None
        try:
            return f"{max(0, int(float(value))):,}원"
        except (TypeError, ValueError):
            return str(value)

    # 출고가(shipping_price) 우선; 품목합만 구해지면 품목합, 그마저 없으면 계약금액 폴백.
    if shipping_price is not None:
        items_label = f"{shipping_price:,}원"
    elif items_total is not None:
        items_label = f"{items_total:,}원"
    else:
        items_label = _fmt(contract) or "-"
    deposit_label = _fmt(deposit_val) if deposit_val else _fmt(legacy_deposit)
    # 읽기전용 요약: 할인은 출고가에 흡수 — 별도 라인 숨김.
    discount_label = None
    balance_label = _fmt_balance(final_raw)
    if balance_label is None and items_total is not None:
        effective_total = int(items_total or 0) + int(free_input_val or 0)
        balance_label = f"{_balance_after_payments(effective_total, deposit_val, discount_val):,}원"
    elif balance_label is None:
        balance_label = _fmt_balance(legacy_balance)
    return {
        "items_total_label": items_label,
        "deposit_label": deposit_label,
        "discount_label": discount_label,
        "balance_label": balance_label,
    }


def _mobile_attachment_item_dict(att) -> dict[str, Any]:
    """OrderAttachment → 모바일 첨부 그리드 항목 dict (per-row·batch 공용)."""
    category_labels = {
        "measurement": "실측",
        "drawing": "도면",
        "construction": "시공",
        "as": "AS",
    }
    cat = (att.category or "measurement").lower()
    label = att.filename or category_labels.get(cat, cat)
    thumb_url = _attachment_thumbnail_url(att)
    view_url = _attachment_full_view_url(att)
    storage_key = (getattr(att, "storage_key", None) or "").strip()
    download_url = build_file_download_url(storage_key) if storage_key else None
    return {
        "label": label,
        "category": cat,
        "id": att.id,
        "item_index": getattr(att, "item_index", None),
        "thumb_url": thumb_url,
        "view_url": view_url,
        "download_url": download_url,
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

    return [_mobile_attachment_item_dict(att) for att in rows]


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
    manager_phone_map: dict[str, str] | None = None,
) -> str:
    """Resolve manager tel: target — structured_data phone, then 출고 설정 실측담당자 목록.

    manager_phone_map(사전 구축된 이름→연락처)이 주어지면 설정 재조회 없이 사용한다(N+1 제거).
    """
    parties = parties or {}
    manager = parties.get("manager") or {}
    name = (
        (manager_name if manager_name and manager_name != "-" else "")
        or manager.get("name")
        or getattr(order, "manager_name", None)
        or ""
    )
    phone = str(manager.get("phone") or "").strip()
    if manager_phone_map is not None:
        resolved = resolve_manager_phone_from_map(str(name).strip(), manager_phone_map)
    else:
        resolved = resolve_manager_phone_from_measurement_settings(str(name).strip())
    return resolved or phone


@dataclass
class MobileQueueBatchContext:
    """모바일 v2 큐 행을 N+1 없이 만들기 위한 사전 일괄 조회 데이터.

    build_mobile_queue_order_row에 전달하면 주문별 단건 조회 대신 이 사전조회 결과를
    쓴다. None이면 기존(주문별) 경로를 그대로 사용한다.
    """
    attachment_counts: dict[int, int] = field(default_factory=dict)
    attachments_by_order: dict[int, list[dict[str, Any]]] = field(default_factory=dict)
    preview_items_by_order: dict[int, list[dict[str, str]]] = field(default_factory=dict)
    timeline_by_order: dict[int, list[dict[str, Any]]] = field(default_factory=dict)
    user_map: dict[int, str] = field(default_factory=dict)
    manager_phone_map: dict[str, str] = field(default_factory=dict)
    drawing_preview_only: bool = False


def _batch_attachment_counts(
    db, order_ids: list[int], *, categories: frozenset[str] | None = None
) -> dict[int, int]:
    """주문별 첨부 총 개수(1회 GROUP BY) — _attachment_count의 배치판.

    Args:
        categories: When set, count only attachments in those categories.
    """
    counts: dict[int, int] = {}
    if not order_ids:
        return counts
    try:
        from models import OrderAttachment
        from sqlalchemy import func

        q = db.query(OrderAttachment.order_id, func.count(OrderAttachment.id)).filter(
            OrderAttachment.order_id.in_(order_ids)
        )
        if categories is not None:
            q = q.filter(func.lower(OrderAttachment.category).in_(sorted(categories)))
        rows = q.group_by(OrderAttachment.order_id).all()
    except Exception:
        return counts
    for oid, cnt in rows:
        counts[int(oid)] = int(cnt or 0)
    return counts


def _batch_mobile_attachment_items(
    db, order_ids: list[int], *, limit_per_order: int = 50
) -> dict[int, list[dict[str, Any]]]:
    """주문별 첨부 그리드 항목(1회 in_ 조회) — mobile_attachment_items의 배치판.

    주문 내 정렬(created_at desc)·항목당 limit을 per-row 경로와 동일하게 유지한다.
    """
    out: dict[int, list[dict[str, Any]]] = {oid: [] for oid in order_ids}
    if not order_ids:
        return out
    try:
        from models import OrderAttachment

        rows = (
            db.query(OrderAttachment)
            .filter(OrderAttachment.order_id.in_(order_ids))
            .order_by(OrderAttachment.order_id.asc(), OrderAttachment.created_at.desc())
            .all()
        )
    except Exception:
        return out
    for att in rows:
        bucket = out.get(int(att.order_id))
        if bucket is None or len(bucket) >= limit_per_order:
            continue
        bucket.append(_mobile_attachment_item_dict(att))
    return out


def _batch_mobile_timeline_events(
    db, order_ids: list[int], *, limit_per_order: int = 12
) -> dict[int, list[dict[str, Any]]]:
    """주문별 타임라인(1회 in_ 조회 + created_by selectinload) — mobile_timeline_events 배치판."""
    out: dict[int, list[dict[str, Any]]] = {oid: [] for oid in order_ids}
    if not order_ids:
        return out
    try:
        from models import OrderEvent
        from sqlalchemy.orm import selectinload

        rows = (
            db.query(OrderEvent)
            .options(selectinload(OrderEvent.created_by))
            .filter(OrderEvent.order_id.in_(order_ids))
            .order_by(OrderEvent.order_id.asc(), OrderEvent.created_at.desc())
            .all()
        )
    except Exception:
        return out
    for ev in rows:
        bucket = out.get(int(ev.order_id))
        if bucket is None or len(bucket) >= limit_per_order:
            continue
        bucket.append(_mobile_timeline_event_dict(ev))
    return out


def build_mobile_queue_batch_context(
    db, orders: list[Any], *, drawing_preview_only: bool = False
) -> MobileQueueBatchContext:
    """모바일 v2 큐 주문 목록의 첨부/미리보기/타임라인/담당자명을 일괄 사전조회한다.

    주문 수 N과 무관하게 고정 수의 쿼리만 발생시켜 build_mobile_queue_order_row의
    주문별 N+1을 제거한다(각 주문 결과는 per-row 경로와 동일).

    Args:
        drawing_preview_only: When True, queue-card preview/count use drawing category only
            (시공·출고 대시보드). Detail attachment grids still load all categories.
    """
    order_ids = [o.id for o in orders]
    sds = [_ensure_dict(getattr(o, "structured_data", None)) for o in orders]
    preview_categories = _QUEUE_DRAWING_CATEGORIES if drawing_preview_only else None
    return MobileQueueBatchContext(
        attachment_counts=_batch_attachment_counts(
            db, order_ids, categories=preview_categories
        ),
        attachments_by_order=_batch_mobile_attachment_items(db, order_ids, limit_per_order=50),
        preview_items_by_order=batch_resolve_queue_attachment_preview_items(
            db, order_ids, categories=preview_categories
        ),
        timeline_by_order=_batch_mobile_timeline_events(db, order_ids),
        user_map=load_assignee_user_map_batch(db, sds),
        manager_phone_map=build_measurement_manager_phone_map(),
        drawing_preview_only=drawing_preview_only,
    )


def build_mobile_queue_order_row(db, order, current_user=None, *, batch_ctx=None) -> dict[str, Any]:
    """Build a dashboard-compatible dict for mobile v2 queue/detail templates.

    batch_ctx(MobileQueueBatchContext)가 주어지면 주문별 단건 조회 대신 사전 일괄조회
    결과를 사용한다(N+1 제거). None이면 기존 동작과 100% 동일.
    """
    sd = _ensure_dict(getattr(order, "structured_data", None))
    cnt = (
        batch_ctx.attachment_counts.get(order.id, 0)
        if batch_ctx is not None
        else _attachment_count(db, order.id)
    )
    stage = _erp_get_stage(order, sd)
    stage_key = stage if isinstance(stage, str) else ""
    stage_code = STAGE_NAME_TO_CODE.get(stage_key, stage_key)
    alerts = _erp_alerts(order, sd, cnt)
    parties = sd.get("parties") or {}
    site = sd.get("site") or {}
    schedule = sd.get("schedule") or {}
    user_map = batch_ctx.user_map if batch_ctx is not None else load_assignee_user_map(db, sd)
    current_quest_payload = build_current_quest_payload(
        sd=sd,
        stage=stage,
        stage_code=stage_code,
        order=order,
        current_user=current_user,
        user_map=user_map,
    )
    preview_items = (
        batch_ctx.preview_items_by_order.get(order.id, [])
        if batch_ctx is not None
        else batch_resolve_queue_attachment_preview_items(db, [order.id]).get(order.id, [])
    )
    previews = [item["view"] for item in preview_items if item.get("view")]
    received = schedule.get("received") or {}
    attachments = (
        batch_ctx.attachments_by_order.get(order.id, [])
        if batch_ctx is not None
        else mobile_attachment_items(db, order.id, limit=50)
    )
    product_items = mobile_product_items(sd, attachments)
    _, common_attachments = _group_attachments_by_item_index(
        attachments,
        item_count=len([i for i in (sd.get("items") or []) if isinstance(i, dict)]),
    )
    common_attachment_categories = mobile_attachment_categories(common_attachments)
    timeline_events = (
        batch_ctx.timeline_by_order.get(order.id, [])
        if batch_ctx is not None
        else mobile_timeline_events(db, order.id)
    )

    return {
        "id": order.id,
        # 오늘 동선 히어로/스트립용 파생(N+1 없음 — flat 컬럼 직접 읽기).
        "measurement_completed": bool(getattr(order, "measurement_completed", False)),
        "lat": getattr(order, "lat", None),
        "lng": getattr(order, "lng", None),
        "customer_name": (parties.get("customer") or {}).get("name") or "-",
        "phone": (parties.get("customer") or {}).get("phone") or "-",
        "address": site.get("address_full") or site.get("address_main") or "-",
        "measurement_date": (schedule.get("measurement") or {}).get("date"),
        "construction_date": (schedule.get("construction") or {}).get("date"),
        "received_date": received.get("date") or getattr(order, "received_date", None),
        "manager_name": (parties.get("manager") or {}).get("name") or getattr(order, "manager_name", None) or "-",
        "manager_phone": resolve_manager_phone_for_queue(
            parties,
            order=order,
            manager_phone_map=(batch_ctx.manager_phone_map if batch_ctx is not None else None),
        ),
        "orderer_name": (parties.get("orderer") or {}).get("name") or None,
        # ORDERER-AXIS-01: 발주사(orderer)와 주문한 사람(buyer)은 다른 축이다.
        "buyer_name": (parties.get("buyer") or {}).get("name") or None,
        "buyer_phone": (parties.get("buyer") or {}).get("phone") or None,
        "stage": stage,
        "stage_code": stage_code,
        "stage_badge_modifier": stage_badge_modifier(stage),
        "stage_badge_label": stage_badge_label(stage),
        "product_subtitle": product_subtitle_from_sd(sd),
        "alerts": alerts,
        "has_media": _erp_has_media(order, cnt),
        "attachments_count": cnt,
        "attachment_preview_items": preview_items,
        "attachment_previews": previews,
        "attachments": attachments,
        "common_attachments": common_attachments,
        "common_attachment_categories": common_attachment_categories,
        "timeline_events": timeline_events,
        "product_items": product_items,
        "amount_summary": mobile_amount_summary(sd),
        "structured_data": sd,
        "role_assignees": resolve_order_role_assignees(sd, order=order, user_map=user_map),
        "current_quest": current_quest_payload,
        "drawing_preview_only": bool(
            batch_ctx is not None and batch_ctx.drawing_preview_only
        ),
    }
