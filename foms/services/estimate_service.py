"""Estimate generation and update helpers."""

from __future__ import annotations

import copy
import datetime
import logging
import re
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from foms.services.datetime_kst import get_today_kst
from foms.services.measurement_manager_colors import normalize_measurement_manager_key
from foms.services.orders.estimate_defaults import ESTIMATE_PAYMENT_INFO
from models import Order, OrderEstimate

__all__ = [
    "generate_estimate_number",
    "extract_estimate_data_from_order",
    "create_estimate",
    "update_estimate",
]

logger = logging.getLogger(__name__)


def resolve_manager_phone_from_measurement_settings(manager_name: str) -> str:
    """ERP 출고 설정의 실측담당자 목록에서 이름이 일치하는 행의 연락처를 반환한다."""
    if not (manager_name or "").strip():
        return ""
    try:
        from foms.services.erp_shipment_settings import load_erp_shipment_settings

        settings = load_erp_shipment_settings()
    except Exception:
        logger.exception("실측담당자 연락처 조회 실패 (출고 설정 로드)")
        return ""

    key = normalize_measurement_manager_key(manager_name)
    if not key:
        return ""

    for m in settings.get("measurement_manager") or []:
        if not isinstance(m, dict):
            continue
        if normalize_measurement_manager_key(m.get("name")) != key:
            continue
        return str(m.get("phone") or "").strip()
    return ""


def generate_estimate_number(db: Session, date_str: str) -> str:
    """Generate the next estimate number for the given date."""
    date_prefix = date_str.replace("-", "")
    like_pattern = f"{date_prefix}_%"

    existing = (
        db.query(OrderEstimate.estimate_number)
        .filter(OrderEstimate.estimate_number.like(like_pattern))
        .all()
    )

    max_seq = 0
    for (num,) in existing:
        try:
            seq = int(num.split("_")[-1])
            if seq > max_seq:
                max_seq = seq
        except (ValueError, IndexError):
            continue

    return f"{date_prefix}_{max_seq + 1}"


def _format_spec_rows(item: dict) -> str:
    """Build a multiline spec string from ``spec_rows`` when present."""
    spec_rows = item.get("spec_rows") or []
    if not spec_rows:
        return item.get("spec") or ""

    lines = []
    for row in spec_rows:
        w = str(row.get("spec_width") or row.get("w") or "").strip()
        d = str(row.get("spec_depth") or row.get("d") or "").strip()
        h = str(row.get("spec_height") or row.get("h") or "").strip()
        parts = [part for part in [w, d, h] if part]
        if parts:
            lines.append("x".join(parts))

    return "\n".join(lines) if lines else (item.get("spec") or "")


def _parse_money_amount(value) -> int:
    if value is None:
        return 0
    if isinstance(value, dict):
        return _parse_money_amount(value.get("amount") or value.get("raw"))
    if isinstance(value, (int, float)):
        return max(0, int(value))

    digits = re.sub(r"[^0-9]", "", str(value))
    return int(digits) if digits else 0


def _extract_deposit_amount(structured_data: dict) -> int:
    for payments in (
        structured_data.get("payment") or {},
        structured_data.get("payments") or {},
    ):
        if not isinstance(payments, dict):
            continue
        amount = _parse_money_amount(payments.get("deposit"))
        if amount > 0:
            return amount
    return 0


def _balance_after_deposit(total_amount: int, deposit_amount: int) -> int:
    return max(0, int(total_amount or 0) - int(deposit_amount or 0))


def extract_estimate_data_from_order(order: Order) -> dict:
    """Extract estimate-friendly data from an order's structured data."""
    sd = order.structured_data or {}
    parties = sd.get("parties", {})
    customer = parties.get("customer", {})
    manager = parties.get("manager", {})
    site = sd.get("site", {})
    schedule = sd.get("schedule", {})

    customer_name = customer.get("name") or order.customer_name or ""
    customer_phone = customer.get("phone") or order.phone or ""
    site_address = site.get("address_full") or order.address or ""
    construction_date = (schedule.get("construction") or {}).get("date")
    manager_name = manager.get("name") or order.manager_name or ""
    manager_phone = str(manager.get("phone") or "").strip()
    resolved_phone = resolve_manager_phone_from_measurement_settings(manager_name)
    if resolved_phone:
        manager_phone = resolved_phone

    orderer = parties.get("orderer", {})
    orderer_name = str(orderer.get("name") or "")
    is_lahom = "라홈" in orderer_name

    raw_items = sd.get("items") or []
    estimate_items = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        quantity = int(item.get("quantity") or 1)
        unit_price = int(item.get("price") or 0)
        estimate_items.append(
            {
                "product_name": item.get("product_name") or "",
                "spec": _format_spec_rows(item),
                "color": item.get("color") or "상담",
                "option_detail": item.get("option_detail") or "",
                "quantity": quantity,
                "unit_price": unit_price,
                "amount": unit_price * quantity,
            }
        )

    total_amount = sum(item["amount"] for item in estimate_items)
    deposit_amount = _extract_deposit_amount(sd)
    balance_amount = _balance_after_deposit(total_amount, deposit_amount)

    return {
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "site_address": site_address,
        "construction_date": construction_date,
        "manager_name": manager_name,
        "manager_phone": manager_phone,
        "is_lahom": is_lahom,
        "items": estimate_items,
        "total_amount": total_amount,
        "deposit_amount": int(deposit_amount or 0),
        "balance_amount": balance_amount,
        "final_amount": balance_amount,
    }


def create_estimate(
    db: Session,
    order: Order,
    *,
    override_data: Optional[dict] = None,
    created_by_user_id: Optional[int] = None,
) -> OrderEstimate:
    """Create a new estimate from an order plus optional override data."""
    today = get_today_kst().strftime("%Y-%m-%d")
    data = extract_estimate_data_from_order(order)

    if override_data:
        for key in (
            "customer_name",
            "customer_phone",
            "site_address",
            "construction_date",
            "manager_name",
            "manager_phone",
            "items",
            "total_amount",
            "deposit_amount",
            "balance_amount",
            "notes",
        ):
            if key in override_data:
                data[key] = override_data[key]

        if "items" in override_data and "total_amount" not in override_data:
            data["total_amount"] = sum(int(item.get("amount") or 0) for item in data["items"])
        if "total_amount" in override_data or "deposit_amount" in override_data:
            data["balance_amount"] = _balance_after_deposit(
                data.get("total_amount", 0),
                data.get("deposit_amount", 0),
            )
        data["final_amount"] = data.get("balance_amount", data.get("total_amount", 0))

    estimate_date = (override_data or {}).get("estimate_date") or today
    estimate_number = generate_estimate_number(db, estimate_date)

    estimate = OrderEstimate(
        order_id=order.id,
        estimate_number=estimate_number,
        customer_name=data["customer_name"],
        customer_phone=data["customer_phone"],
        site_address=data["site_address"],
        estimate_date=estimate_date,
        construction_date=data.get("construction_date"),
        manager_name=data.get("manager_name"),
        manager_phone=data.get("manager_phone"),
        items=data["items"],
        total_amount=data["total_amount"],
        deposit_amount=data.get("deposit_amount", 0),
        balance_amount=data.get("balance_amount", data["total_amount"]),
        payment_info=copy.deepcopy(ESTIMATE_PAYMENT_INFO),
        status="DRAFT",
        notes=data.get("notes"),
        created_by_user_id=created_by_user_id,
    )

    db.add(estimate)
    db.flush()

    logger.info("견적서 생성: #%s (주문 %d, 금액 %s원)", estimate.estimate_number, order.id, f"{estimate.total_amount:,}")
    return estimate


def update_estimate(
    db: Session,
    estimate: OrderEstimate,
    update_data: dict,
) -> OrderEstimate:
    """Update an existing estimate and recalculate totals when required."""
    allowed_fields = {
        "customer_name",
        "customer_phone",
        "site_address",
        "estimate_date",
        "construction_date",
        "manager_name",
        "manager_phone",
        "items",
        "total_amount",
        "deposit_amount",
        "balance_amount",
        "notes",
        "status",
    }

    for key, value in update_data.items():
        if key in allowed_fields:
            setattr(estimate, key, value)

    if "items" in update_data:
        flag_modified(estimate, "items")
        if "total_amount" not in update_data:
            estimate.total_amount = sum(int(item.get("amount") or 0) for item in (estimate.items or []))

    if "total_amount" in update_data or "deposit_amount" in update_data or "items" in update_data:
        estimate.balance_amount = max(0, (estimate.total_amount or 0) - (estimate.deposit_amount or 0))

    estimate.updated_at = datetime.datetime.now()

    logger.info("견적서 수정: #%s", estimate.estimate_number)
    return estimate
