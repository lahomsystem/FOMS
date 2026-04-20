"""Calendar-event response builder for the legacy orders blueprint."""

from __future__ import annotations

from flask import jsonify, request
from sqlalchemy import and_, or_
from sqlalchemy.orm import defer

from foms.services.erp_order_flags import is_erp_order_record
from foms.services.orders.status_constants import STATUS
from db import get_db
from models import Order, OrderScheduleDate


_STATUS_COLORS = {
    "RECEIVED": "#3788d8",
    "MEASURED": "#f39c12",
    "SCHEDULED": "#e74c3c",
    "SHIPPED_PENDING": "#ff6b35",
    "COMPLETED": "#2ecc71",
    "AS_RECEIVED": "#9b59b6",
    "AS_COMPLETED": "#1abc9c",
}


def _apply_erp_order_display_overrides(
    order,
    *,
    customer_name: str,
    phone: str,
    address: str,
    product: str,
    measurement_date,
    measurement_time,
    scheduled_date,
):
    """Overlay ERP Order structured-data fields on top of the flat legacy columns."""
    structured_data = getattr(order, "structured_data", None)
    if not (is_erp_order_record(order) and isinstance(structured_data, dict)):
        return customer_name, phone, address, product, measurement_date, measurement_time, scheduled_date

    erp_customer_name = ((structured_data.get("parties") or {}).get("customer") or {}).get("name")
    if erp_customer_name:
        customer_name = erp_customer_name

    erp_phone = ((structured_data.get("parties") or {}).get("customer") or {}).get("phone")
    if erp_phone:
        phone = erp_phone

    erp_address = (structured_data.get("site") or {}).get("address_full") or (
        structured_data.get("site") or {}
    ).get("address_main")
    if erp_address:
        address = erp_address

    items = structured_data.get("items") or []
    if items:
        first_item = items[0]
        product_name = first_item.get("product_name") or first_item.get("name")
        if product_name:
            product = (
                f"{product_name} 외 {len(items) - 1}개" if len(items) > 1 else product_name
            )

    erp_measurement_date = (((structured_data.get("schedule") or {}).get("measurement") or {}).get("date"))
    if erp_measurement_date:
        measurement_date = erp_measurement_date

    erp_measurement_time = (((structured_data.get("schedule") or {}).get("measurement") or {}).get("time"))
    if erp_measurement_time:
        measurement_time = erp_measurement_time

    erp_scheduled_date = (((structured_data.get("schedule") or {}).get("construction") or {}).get("date"))
    if erp_scheduled_date:
        scheduled_date = erp_scheduled_date

    return customer_name, phone, address, product, measurement_date, measurement_time, scheduled_date


def _build_start_date_value(order, measurement_date, scheduled_date):
    """Choose the date field that backs the calendar event start date."""
    if is_erp_order_record(order) and measurement_date:
        return measurement_date

    status = getattr(order, "status", None) or ""
    status_date_map = {
        "RECEIVED": getattr(order, "received_date", None),
        "MEASURED": measurement_date,
        "SCHEDULED": scheduled_date,
        "SHIPPED_PENDING": scheduled_date,
        "COMPLETED": getattr(order, "completion_date", None),
        "AS_RECEIVED": getattr(order, "as_received_date", None),
        "AS_COMPLETED": getattr(order, "as_completed_date", None),
    }
    return status_date_map.get(status)


def _build_status_time_map(order, measurement_time):
    """Return the time-map that mirrors the legacy calendar surface."""
    return {
        "RECEIVED": getattr(order, "received_time", None),
        "MEASURED": measurement_time,
        "SCHEDULED": None,
        "SHIPPED_PENDING": None,
        "COMPLETED": None,
        "AS_RECEIVED": None,
        "AS_COMPLETED": None,
    }


def calendar_orders_response():
    """Build the `/api/orders` FullCalendar payload."""
    start_date = request.args.get("start")
    end_date = request.args.get("end")
    status_filter = request.args.get("status")
    limit_raw = request.args.get("limit", "2000")

    db = get_db()
    query = db.query(Order).filter(Order.active_filter()).options(
        defer(Order.raw_order_text),
        defer(Order.regional_memo),
        defer(Order.address_hash),
        defer(Order.lat),
        defer(Order.lng),
        defer(Order.geocode_status),
        defer(Order.options),
    )

    if status_filter and status_filter in STATUS:
        if status_filter == "RECEIVED":
            query = query.filter(Order.status.in_(["RECEIVED", "ON_HOLD"]))
        else:
            query = query.filter(Order.status == status_filter)

    if start_date and end_date:
        if "T" in str(start_date):
            start_date_only = str(start_date).split("T")[0]
            end_date_only = str(end_date).split("T")[0]
        else:
            start_date_only = start_date
            end_date_only = end_date

        query = query.outerjoin(OrderScheduleDate, Order.id == OrderScheduleDate.order_id)
        query = query.filter(
            or_(
                Order.received_date.between(start_date_only, end_date_only),
                Order.as_received_date.between(start_date_only, end_date_only),
                Order.as_completed_date.between(start_date_only, end_date_only),
                Order.completion_date.between(start_date_only, end_date_only),
                and_(
                    OrderScheduleDate.id.isnot(None),
                    OrderScheduleDate.date.between(start_date_only, end_date_only),
                ),
            )
        ).distinct()

    try:
        limit = int(limit_raw)
    except (TypeError, ValueError):
        limit = 2000
    limit = max(100, min(limit, 5000))

    orders = query.order_by(Order.id.desc()).limit(limit).all()

    events = []
    for order in orders:
        customer_name = getattr(order, "customer_name", None) or ""
        phone = getattr(order, "phone", None) or ""
        address = getattr(order, "address", None) or ""
        product = getattr(order, "product", None) or ""
        measurement_date = getattr(order, "measurement_date", None)
        measurement_time = getattr(order, "measurement_time", None)
        scheduled_date = getattr(order, "scheduled_date", None)

        (
            customer_name,
            phone,
            address,
            product,
            measurement_date,
            measurement_time,
            scheduled_date,
        ) = _apply_erp_order_display_overrides(
            order,
            customer_name=customer_name,
            phone=phone,
            address=address,
            product=product,
            measurement_date=measurement_date,
            measurement_time=measurement_time,
            scheduled_date=scheduled_date,
        )

        start_date_value = _build_start_date_value(order, measurement_date, scheduled_date)
        if not start_date_value:
            continue

        start_dates_list = [
            value.strip()
            for value in str(start_date_value).split(",")
            if value.strip() and len(value.strip()) == 10
        ]
        if not start_dates_list:
            raw_value = str(start_date_value).strip()
            start_dates_list = [raw_value] if raw_value else []

        status = getattr(order, "status", None) or ""
        status_time_map = _build_status_time_map(order, measurement_time)
        time_str = status_time_map.get(status)
        color = _STATUS_COLORS.get(status, "#3788d8")
        title = f"{customer_name} | {phone} | {product}"
        extended_props = {
            "customer_name": customer_name,
            "phone": phone,
            "address": address,
            "product": product,
            "options": getattr(order, "options", None),
            "notes": getattr(order, "notes", None),
            "status": status,
            "received_date": getattr(order, "received_date", None),
            "received_time": getattr(order, "received_time", None),
            "measurement_date": measurement_date,
            "measurement_time": measurement_time,
            "completion_date": getattr(order, "completion_date", None),
            "scheduled_date": scheduled_date,
            "as_received_date": getattr(order, "as_received_date", None),
            "as_completed_date": getattr(order, "as_completed_date", None),
            "manager_name": getattr(order, "manager_name", None),
        }

        for index, one_date in enumerate(start_dates_list):
            if status == "MEASURED" and measurement_time in ["종일", "오전", "오후"]:
                start_datetime = one_date
                all_day = True
            elif time_str:
                start_datetime = f"{one_date}T{time_str}:00"
                all_day = False
            else:
                start_datetime = one_date
                all_day = True

            events.append(
                {
                    "id": f"{order.id}-{index}-{one_date}"
                    if len(start_dates_list) > 1
                    else order.id,
                    "title": title,
                    "start": start_datetime,
                    "allDay": all_day,
                    "backgroundColor": color,
                    "borderColor": color,
                    "extendedProps": extended_props,
                }
            )

    return jsonify(events)
