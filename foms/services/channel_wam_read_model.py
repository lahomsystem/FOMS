"""WAM 채널용 주문 read model: Order/structured_data를 읽기 전용 뷰 모델로 투영한다."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote_plus

from db import get_db
from foms.services.erp_display import (
    _ensure_dict,
    _erp_alerts,
    _erp_get_stage,
    apply_erp_display_fields,
)
from foms.services.order_event_display import (
    format_timeline_description,
    translate_event_type_to_korean,
)
from foms.services.erp_order_flags import is_erp_order_record
from models import Order, OrderEvent

__all__ = [
    "STATUS_LABELS",
    "WamTimelineEntry",
    "WamOrderReadModel",
    "get_order_for_wam",
    "load_wam_order_read_model",
    "build_order_read_model",
    "get_recent_events_for_wam",
]


STATUS_LABELS = {
    "RECEIVED": "주문접수",
    "MEASURE": "실측",
    "DRAWING": "도면",
    "CONFIRM": "고객컨펌",
    "PRODUCTION": "생산",
    "CONSTRUCTION": "시공",
    "CS": "CS",
    "COMPLETED": "완료",
    "AS": "AS",
}


@dataclass
class WamTimelineEntry:
    event_type: str
    label: str
    description: str
    created_at_label: str | None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "label": self.label,
            "description": self.description,
            "created_at_label": self.created_at_label,
            "meta": self.meta,
        }


@dataclass
class WamOrderReadModel:
    order_id: int
    status_code: str
    status_label: str
    customer_name: str
    phone: str
    address: str
    product: str
    manager_name: str
    orderer_name: str
    measurement_date: str
    measurement_time: str
    construction_date: str
    construction_time: str
    received_date: str
    shipping_scheduled_date: str
    as_visit_date: str
    created_at_label: str | None
    urgent: bool
    owner_team: str
    customer: dict[str, Any]
    site: dict[str, Any]
    people: dict[str, Any]
    schedule: dict[str, Any]
    items: list[dict[str, Any]]
    payment: dict[str, Any]
    timeline: list[WamTimelineEntry]
    info_banner: dict[str, Any] | None = None
    structured_data: dict[str, Any] = field(default_factory=dict)


def _nested_value(data: dict[str, Any], *path: str) -> Any:
    current: Any = data
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _value_or_dash(value: Any) -> str:
    if value in (None, ""):
        return "-"
    return str(value)


def _normalize_name_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            if isinstance(item, dict):
                candidate = item.get("name") or item.get("label") or item.get("value")
            else:
                candidate = item
            if candidate not in (None, ""):
                result.append(str(candidate))
        return result
    if isinstance(value, dict):
        candidate = value.get("name") or value.get("label") or value.get("value")
        return [str(candidate)] if candidate not in (None, "") else []
    return [str(value)]


def _map_url(address: str) -> str:
    if not address or address == "-":
        return ""
    return f"https://maps.google.com/?q={quote_plus(address)}"


def get_order_for_wam(order_id: int) -> Order | None:
    db = get_db()
    return db.query(Order).filter(Order.id == int(order_id), Order.active_filter()).first()


def _display_order(order: Order) -> Order:
    structured_data = _ensure_dict(getattr(order, "structured_data", None))
    if is_erp_order_record(order) and structured_data:
        copied = deepcopy(order)
        apply_erp_display_fields(copied)
        return copied
    return order


def _status_label(order: Order, structured_data: dict[str, Any], display_order: Order) -> str:
    if is_erp_order_record(order):
        return _erp_get_stage(order, structured_data)
    return STATUS_LABELS.get(display_order.status, display_order.status or "-")


def _normalize_item(raw_item: Any, index: int, fallback_product: str) -> dict[str, Any]:
    item = raw_item if isinstance(raw_item, dict) else {"product_name": raw_item}
    product_name = (
        item.get("product_name")
        or item.get("name")
        or item.get("title")
        or fallback_product
        or f"품목 {index + 1}"
    )
    return {
        "index": index,
        "title": _value_or_dash(product_name),
        "product_name": _value_or_dash(product_name),
        "quantity": item.get("quantity") or item.get("qty") or item.get("count"),
        "spec": _value_or_dash(item.get("spec")),
        "inside": _value_or_dash(item.get("inside") or item.get("internal")),
        "color": _value_or_dash(item.get("color")),
        "option": _value_or_dash(item.get("option") or item.get("options") or item.get("option_summary")),
        "handle": _value_or_dash(item.get("handle")),
        "extra": _value_or_dash(item.get("extra") or item.get("etc") or item.get("misc")),
        "payload": item,
    }


def _normalize_items(structured_data: dict[str, Any], fallback_product: str) -> list[dict[str, Any]]:
    raw_items = structured_data.get("items")
    items: list[dict[str, Any]] = []

    if isinstance(raw_items, list):
        for index, raw_item in enumerate(raw_items):
            items.append(_normalize_item(raw_item, index, fallback_product))

    if not items and fallback_product not in (None, "", "-"):
        items.append(
            {
                "index": 0,
                "title": str(fallback_product),
                "product_name": str(fallback_product),
                "quantity": None,
                "spec": "-",
                "inside": "-",
                "color": "-",
                "option": "-",
                "handle": "-",
                "extra": "-",
                "payload": {},
            }
        )
    return items


def _timeline_label(event_type: str, payload: dict[str, Any]) -> str:
    custom = payload.get("title") or payload.get("label") or payload.get("field_label")
    if custom not in (None, ""):
        return str(custom)
    return translate_event_type_to_korean(event_type)


def _load_timeline(order_id: int, limit: int = 5) -> list[WamTimelineEntry]:
    db = get_db()
    events = (
        db.query(OrderEvent)
        .filter(OrderEvent.order_id == int(order_id))
        .order_by(OrderEvent.created_at.desc(), OrderEvent.id.desc())
        .limit(limit)
        .all()
    )

    result: list[WamTimelineEntry] = []
    for event in events:
        payload = event.payload if isinstance(event.payload, dict) else {}
        result.append(
            WamTimelineEntry(
                event_type=str(event.event_type or "event"),
                label=_timeline_label(str(event.event_type or "event"), payload),
                description=format_timeline_description(str(event.event_type or "event"), payload),
                created_at_label=event.created_at.strftime("%Y-%m-%d %H:%M")
                if event.created_at
                else None,
                meta={"payload": payload},
            )
        )
    return result


def load_wam_order_read_model(order_id: int) -> WamOrderReadModel | None:
    order = get_order_for_wam(order_id)
    if not order:
        return None

    structured_data = _ensure_dict(order.structured_data)
    display_order = _display_order(order)

    schedule = _ensure_dict(structured_data.get("schedule"))
    site = _ensure_dict(structured_data.get("site"))
    parties = _ensure_dict(structured_data.get("parties"))
    shipment = _ensure_dict(structured_data.get("shipment"))
    flags = _ensure_dict(structured_data.get("flags"))
    workflow = _ensure_dict(structured_data.get("workflow"))
    assignments = _ensure_dict(structured_data.get("assignments"))

    measurement_date = (
        _nested_value(schedule, "measurement", "date")
        or getattr(display_order, "measurement_date", None)
        or getattr(display_order, "erp_measurement_date", None)
        or "-"
    )
    measurement_time = (
        _nested_value(schedule, "measurement", "time")
        or getattr(display_order, "measurement_time", None)
        or "-"
    )
    construction_date = (
        _nested_value(schedule, "construction", "date")
        or getattr(display_order, "scheduled_date", None)
        or getattr(display_order, "erp_construction_date", None)
        or "-"
    )
    construction_time = _nested_value(schedule, "construction", "time") or "-"
    as_visit_date = (
        _nested_value(schedule, "as_visit", "date")
        or getattr(display_order, "as_visit_date", None)
        or "-"
    )

    customer_name = _value_or_dash(
        getattr(display_order, "customer_name", None)
        or _nested_value(parties, "customer", "name")
    )
    phone = _value_or_dash(
        getattr(display_order, "phone", None)
        or _nested_value(parties, "customer", "phone")
    )
    address_full = _value_or_dash(site.get("address_full") or getattr(display_order, "address", None))
    address_main = _value_or_dash(site.get("address_main") or getattr(display_order, "address", None))
    address_detail = _value_or_dash(site.get("address_detail"))
    manager_name = _value_or_dash(
        getattr(display_order, "manager_name", None)
        or _nested_value(parties, "manager", "name")
    )
    orderer_name = _value_or_dash(
        getattr(display_order, "orderer_name", None)
        or _nested_value(parties, "orderer", "name")
    )
    product = _value_or_dash(getattr(display_order, "product", None))
    status_label = _value_or_dash(_status_label(order, structured_data, display_order))
    owner_team = _value_or_dash(
        _nested_value(assignments, "owner_team")
        or _nested_value(workflow, "current_quest", "owner_team")
        or workflow.get("owner_team")
        or getattr(order, "erp_owner_team_code", None)
    )
    urgent = bool(flags.get("urgent") or getattr(order, "erp_urgent", False))
    drawing_manager = _value_or_dash(
        shipment.get("drawing_manager") or ", ".join(_normalize_name_list(shipment.get("drawing_managers")))
    )
    construction_workers = _normalize_name_list(
        shipment.get("construction_workers") or shipment.get("construction_worker")
    )

    items = _normalize_items(structured_data, product)
    timeline = _load_timeline(order.id)
    alerts = _erp_alerts(order, structured_data, attachments_count=0)

    customer = {
        "customer_name": customer_name,
        "phone": phone,
        "orderer_name": orderer_name,
        "manager_name": manager_name,
    }
    site_payload = {
        "address_full": address_full,
        "address_main": address_main,
        "address_detail": address_detail,
        "map_url": _map_url(address_full),
    }
    people = {
        "manager_name": manager_name,
        "drawing_manager": drawing_manager,
        "drawing_managers": _normalize_name_list(shipment.get("drawing_managers")),
        "construction_workers": construction_workers,
        "owner_team": owner_team,
        "construction_type": _value_or_dash(getattr(display_order, "construction_type", None)),
    }
    schedule_payload = {
        "received_date": _value_or_dash(getattr(display_order, "received_date", None)),
        "measurement_date": _value_or_dash(measurement_date),
        "measurement_time": _value_or_dash(measurement_time),
        "construction_date": _value_or_dash(construction_date),
        "construction_time": _value_or_dash(construction_time),
        "shipping_scheduled_date": _value_or_dash(getattr(display_order, "shipping_scheduled_date", None)),
        "as_visit_date": _value_or_dash(as_visit_date),
    }
    payment = {
        "payment_amount": int(getattr(display_order, "payment_amount", 0) or 0),
        "shipping_fee": int(getattr(display_order, "shipping_fee", 0) or 0),
        "total_label": f"{int(getattr(display_order, 'payment_amount', 0) or 0):,}원",
        "shipping_fee_label": f"{int(getattr(display_order, 'shipping_fee', 0) or 0):,}원",
    }

    banner_text = "읽기 전용 화면입니다."
    if alerts.get("urgent"):
        banner_text = "긴급 주문입니다. 일정과 담당 정보를 우선 확인하세요."

    return WamOrderReadModel(
        order_id=order.id,
        status_code=str(display_order.status or ""),
        status_label=status_label,
        customer_name=customer_name,
        phone=phone,
        address=address_full,
        product=product,
        manager_name=manager_name,
        orderer_name=orderer_name,
        measurement_date=_value_or_dash(measurement_date),
        measurement_time=_value_or_dash(measurement_time),
        construction_date=_value_or_dash(construction_date),
        construction_time=_value_or_dash(construction_time),
        received_date=_value_or_dash(getattr(display_order, "received_date", None)),
        shipping_scheduled_date=_value_or_dash(getattr(display_order, "shipping_scheduled_date", None)),
        as_visit_date=_value_or_dash(as_visit_date),
        created_at_label=display_order.created_at.strftime("%Y-%m-%d %H:%M")
        if display_order.created_at
        else None,
        urgent=urgent,
        owner_team=owner_team,
        customer=customer,
        site=site_payload,
        people=people,
        schedule=schedule_payload,
        items=items,
        payment=payment,
        timeline=timeline,
        info_banner={"text": banner_text},
        structured_data=structured_data,
    )


def build_order_read_model(order_id: int) -> dict[str, Any] | None:
    read_model = load_wam_order_read_model(order_id)
    if not read_model:
        return None

    return {
        "header": {
            "order_id": read_model.order_id,
            "status_label": read_model.status_label,
            "customer_name": read_model.customer_name,
            "manager_name": read_model.manager_name,
            "urgent": read_model.urgent,
            "owner_team": read_model.owner_team,
        },
        "summary_strip": {
            "cards": [
                {"key": "measurement_date", "label": "실측일", "value": read_model.measurement_date},
                {"key": "construction_date", "label": "시공일", "value": read_model.construction_date},
                {"key": "address", "label": "주소", "value": read_model.address},
                {"key": "product", "label": "제품", "value": read_model.product},
            ]
        },
        "customer": read_model.customer,
        "site": read_model.site,
        "schedule": read_model.schedule,
        "people": read_model.people,
        "items": read_model.items,
        "payment": read_model.payment,
        "timeline": [entry.to_dict() for entry in read_model.timeline],
        "info_banner": read_model.info_banner,
    }


def get_recent_events_for_wam(order_id: int, limit: int = 5) -> list[dict[str, Any]]:
    return [entry.to_dict() for entry in _load_timeline(order_id, limit=limit)]
