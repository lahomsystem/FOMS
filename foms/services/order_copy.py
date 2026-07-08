"""Order copy helpers shared by dashboard/API flows."""

from __future__ import annotations

import copy
import datetime
from typing import Any

from foms.services.datetime_kst import now_kst
from foms.services.erp_order_flags import is_erp_order_record
from foms.services.erp_sync_columns import sync_erp_flat_columns
from models import Order

_STRUCTURED_COPY_DROP_KEYS = {
    "drawing",
    "blueprint",
    "drawing_status",
    "drawing_transferred",
    "drawing_confirmed_at",
    "drawing_confirmed_by",
    "drawing_current_files",
    "drawing_transfer_history",
    "last_drawing_transfer",
    "drawing_assignees",
    "drawing_wizard",
    "estimate_preview",
    "channeltalk_push",
    "channeltalk_push_drawing",
    "channeltalk_push_estimate",
    "quests",
}

_META_COPY_DROP_KEYS = {
    "draft",
    "draft_token",
    "wdc_estimate_id",
    "wdcalculator_estimate_id",
    "estimate_id",
}


def _ensure_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _first_product_name(structured_data: dict[str, Any]) -> str:
    items = structured_data.get("items")
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                name = (item.get("product_name") or item.get("name") or "").strip()
                if name:
                    return name
    return ""


def _copy_erp_structured_data(original_order: Order, copied_at: datetime.datetime) -> dict[str, Any]:
    structured_data = copy.deepcopy(_ensure_dict(getattr(original_order, "structured_data", None)))

    for key in _STRUCTURED_COPY_DROP_KEYS:
        structured_data.pop(key, None)

    structured_data["workflow"] = {
        "stage": "RECEIVED",
        "stage_updated_at": copied_at.isoformat(),
    }
    structured_data["assignments"] = {}
    structured_data["shipment"] = {}

    if not isinstance(structured_data.get("flags"), dict):
        structured_data["flags"] = {}
    if not isinstance(structured_data.get("schedule"), dict):
        structured_data["schedule"] = {}

    meta = copy.deepcopy(_ensure_dict(structured_data.get("meta")))
    for key in _META_COPY_DROP_KEYS:
        meta.pop(key, None)
    meta.update(
        {
            "draft": False,
            "created_via": "ORDER_COPY",
            "copied_from_order_id": original_order.id,
            "copied_at": copied_at.isoformat(),
        }
    )
    structured_data["meta"] = meta
    return structured_data


def _flat_customer_name(order: Order, structured_data: dict[str, Any]) -> str:
    customer = _ensure_dict(_ensure_dict(structured_data.get("parties")).get("customer"))
    name = (customer.get("name") or getattr(order, "customer_name", "") or "").strip()
    return name or "ERP Order"


def _flat_phone(order: Order, structured_data: dict[str, Any]) -> str:
    customer = _ensure_dict(_ensure_dict(structured_data.get("parties")).get("customer"))
    phone = (customer.get("phone") or getattr(order, "phone", "") or "").strip()
    return phone or "000-0000-0000"


def _flat_address(order: Order, structured_data: dict[str, Any]) -> str:
    site = _ensure_dict(structured_data.get("site"))
    address = (
        site.get("address_full")
        or site.get("address_main")
        or getattr(order, "address", "")
        or ""
    ).strip()
    return address or "-"


def _flat_product(order: Order, structured_data: dict[str, Any]) -> str:
    product = (_first_product_name(structured_data) or getattr(order, "product", "") or "").strip()
    return product or "ERP Order"


def copy_order_as_new(original_order: Order, *, copied_at: datetime.datetime | None = None) -> Order:
    """Create an unsaved copy with a fresh primary key assigned by the database."""
    copied_at = copied_at or now_kst()
    today_str = copied_at.strftime("%Y-%m-%d")
    time_str = copied_at.strftime("%H:%M")

    if is_erp_order_record(original_order):
        structured_data = _copy_erp_structured_data(original_order, copied_at)
        copied_order = Order(
            received_date=today_str,
            received_time=time_str,
            customer_name=_flat_customer_name(original_order, structured_data),
            phone=_flat_phone(original_order, structured_data),
            address=_flat_address(original_order, structured_data),
            product=_flat_product(original_order, structured_data),
            options=copy.deepcopy(getattr(original_order, "options", None)),
            notes=getattr(original_order, "notes", None),
            status="RECEIVED",
            is_regional=bool(getattr(original_order, "is_regional", False)),
            is_self_measurement=bool(getattr(original_order, "is_self_measurement", False)),
            is_cabinet=bool(getattr(original_order, "is_cabinet", False)),
            construction_type=getattr(original_order, "construction_type", None),
            regional_memo=getattr(original_order, "regional_memo", None),
            shipping_fee=getattr(original_order, "shipping_fee", None) or 0,
            is_erp_order=True,
            raw_order_text=getattr(original_order, "raw_order_text", None),
            structured_data=structured_data,
            structured_schema_version=getattr(original_order, "structured_schema_version", None) or 1,
            structured_confidence=getattr(original_order, "structured_confidence", None),
            structured_updated_at=copied_at,
        )
        sync_erp_flat_columns(copied_order, structured_data)
        if getattr(original_order, "payment_amount", None) and not getattr(copied_order, "payment_amount", None):
            copied_order.payment_amount = original_order.payment_amount
        return copied_order

    copied_order = Order(
        received_date=today_str,
        received_time=time_str,
        customer_name=f"[복사: 원본 #{original_order.id}] {getattr(original_order, 'customer_name', '')}",
        phone=getattr(original_order, "phone", ""),
        address=getattr(original_order, "address", ""),
        product=getattr(original_order, "product", ""),
        options=copy.deepcopy(getattr(original_order, "options", None)),
        notes=f"원본 주문 #{original_order.id} 에서 복사됨.\n---\n{getattr(original_order, 'notes', None) or ''}",
        status="RECEIVED",
        is_regional=bool(getattr(original_order, "is_regional", False)),
        is_self_measurement=bool(getattr(original_order, "is_self_measurement", False)),
        is_cabinet=bool(getattr(original_order, "is_cabinet", False)),
        construction_type=getattr(original_order, "construction_type", None),
        regional_memo=getattr(original_order, "regional_memo", None),
        shipping_fee=getattr(original_order, "shipping_fee", None) or 0,
    )
    return copied_order


__all__ = ["copy_order_as_new"]
