"""ERP mobile v2 display helpers — mockup queue cards & order detail."""

from __future__ import annotations

from typing import Any

from foms.services.erp_display import (
    _ensure_dict,
    _erp_alerts,
    _erp_get_stage,
    _erp_has_media,
)
from foms.services.erp_policy import STAGE_LABELS, STAGE_NAME_TO_CODE

__all__ = [
    "stage_badge_modifier",
    "stage_badge_label",
    "product_subtitle_from_sd",
    "build_mobile_queue_order_row",
    "mobile_timeline_events",
    "mobile_attachment_items",
]


_EVENT_LABELS: dict[str, str] = {
    "STAGE_CHANGED": "단계 변경",
    "URGENT_CHANGED": "긴급 상태 변경",
    "MEASUREMENT_DATE_CHANGED": "실측 일정 변경",
    "CONSTRUCTION_DATE_CHANGED": "시공 일정 변경",
    "OWNER_TEAM_CHANGED": "담당팀 변경",
}


def _format_event_meta(event, payload: dict) -> str:
    """Human-readable meta line for a timeline row."""
    parts: list[str] = []
    created_by = getattr(event, "created_by", None)
    if created_by and getattr(created_by, "name", None):
        parts.append(str(created_by.name))
    created_at = getattr(event, "created_at", None)
    if created_at:
        parts.append(created_at.strftime("%Y-%m-%d %H:%M"))
    if payload.get("to") and event.event_type == "STAGE_CHANGED":
        to_stage = payload.get("to")
        parts.append(stage_badge_label(str(to_stage)) if to_stage else "")
    elif payload.get("to") is not None:
        parts.append(str(payload.get("to")))
    return " · ".join(p for p in parts if p)


def mobile_timeline_events(db, order_id: int, *, limit: int = 12) -> list[dict[str, Any]]:
    """Recent OrderEvent rows for mobile detail timeline (newest first).

    Args:
        db: SQLAlchemy session.
        order_id: Order primary key.
        limit: Maximum events to return.

    Returns:
        List of dicts with title, meta, and done flag for template rendering.
    """
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
        title = _EVENT_LABELS.get(ev.event_type or "", ev.event_type or "이벤트")
        items.append(
            {
                "title": title,
                "meta": _format_event_meta(ev, payload),
                "done": True,
            }
        )
    return items


def mobile_attachment_items(db, order_id: int, *, limit: int = 8) -> list[dict[str, Any]]:
    """Attachment summary rows for mobile detail attach grid.

    Args:
        db: SQLAlchemy session.
        order_id: Order primary key.
        limit: Maximum attachments.

    Returns:
        List of dicts with label and category for attach grid cells.
    """
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
        items.append({"label": label, "category": cat, "id": att.id})
    return items


def stage_badge_modifier(stage: str | None) -> str:
    """Map ERP stage label/code to foms-stage-badge BEM modifier suffix.

    Args:
        stage: Human-readable stage label or internal code.

    Returns:
        Modifier suffix including leading dashes, e.g. ``--measure``.
    """
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
    """Build a dashboard-compatible dict for mobile v2 queue/detail templates.

    Args:
        db: SQLAlchemy session.
        order: Order ORM instance.

    Returns:
        Dict with customer, stage, alerts, and badge modifiers.
    """
    sd = _ensure_dict(getattr(order, "structured_data", None))
    cnt = _attachment_count(db, order.id)
    stage = _erp_get_stage(order, sd)
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

    return {
        "id": order.id,
        "customer_name": (parties.get("customer") or {}).get("name") or "-",
        "phone": (parties.get("customer") or {}).get("phone") or "-",
        "address": site.get("address_full") or site.get("address_main") or "-",
        "measurement_date": (schedule.get("measurement") or {}).get("date"),
        "construction_date": (schedule.get("construction") or {}).get("date"),
        "manager_name": (parties.get("manager") or {}).get("name") or "-",
        "orderer_name": (parties.get("orderer") or {}).get("name") or None,
        "stage": stage,
        "stage_badge_modifier": stage_badge_modifier(stage),
        "stage_badge_label": stage_badge_label(stage),
        "product_subtitle": product_subtitle_from_sd(sd),
        "alerts": alerts,
        "has_media": _erp_has_media(order, cnt),
        "attachments_count": cnt,
        "attachments": mobile_attachment_items(db, order.id),
        "timeline_events": mobile_timeline_events(db, order.id),
        "structured_data": sd,
        "current_quest": {"title": current_quest.get("title", "")} if current_quest else None,
    }
