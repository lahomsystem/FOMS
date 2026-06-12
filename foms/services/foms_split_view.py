"""Tablet split-view master list helpers (P1-05)."""

from __future__ import annotations

from typing import Any


def build_split_master_cards(orders: list[dict[str, Any]], *, active_order_id: int | None = None) -> list[dict[str, Any]]:
    """Build master pane card descriptors from dashboard order rows."""
    cards: list[dict[str, Any]] = []
    for row in orders[:30]:
        oid = int(row.get("id") or 0)
        if not oid:
            continue
        stage = str(row.get("stage_badge_label") or row.get("stage") or "")
        schedule_label = ""
        schedule_value = ""
        if row.get("measurement_date"):
            schedule_label = "실측"
            schedule_value = str(row.get("measurement_date") or "")
        elif row.get("construction_date"):
            schedule_label = "시공"
            schedule_value = str(row.get("construction_date") or "")
        cards.append(
            {
                "order_id": oid,
                "title": str(row.get("customer_name") or f"#{oid}"),
                "stage": stage,
                "meta": stage,
                "subtitle": str(row.get("product_subtitle") or ""),
                "schedule_label": schedule_label,
                "schedule_value": schedule_value,
                "phone": str(row.get("phone") or "-"),
                "address": str(row.get("address") or "-"),
                "manager": str(row.get("manager_name") or "-"),
                "detail_href": f"/api/foms/fragment/order/{oid}/edit?open=erp-order",
                "active": active_order_id is not None and oid == active_order_id,
            }
        )
    return cards


def default_split_side_items() -> list[dict[str, str]]:
    """Minimal side-tab items for ERP dashboard split shell."""
    return [
        {"id": "dashboard", "label": "대시", "icon": "fas fa-layer-group", "href": "/erp/dashboard", "active": "true"},
        {"id": "orders", "label": "주문", "icon": "fas fa-list", "href": "/", "active": ""},
    ]
