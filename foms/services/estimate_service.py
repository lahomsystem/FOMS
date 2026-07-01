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


def build_measurement_manager_phone_map(settings: Optional[dict] = None) -> dict[str, str]:
    """정규화된 실측담당자 이름 → 연락처 map (출고 설정 1회 로드, 첫 매치 우선).

    모바일 큐 등 다건 처리에서 행마다 설정을 재조회하는 N+1을 없애기 위한 사전조회용.
    중복 이름은 첫 행 우선(원본 iterate-first-match와 동일).
    """
    if settings is None:
        try:
            from foms.services.erp_shipment_settings import load_erp_shipment_settings

            settings = load_erp_shipment_settings()
        except Exception:
            logger.exception("실측담당자 연락처 맵 로드 실패 (출고 설정 로드)")
            return {}

    out: dict[str, str] = {}
    for m in settings.get("measurement_manager") or []:
        if not isinstance(m, dict):
            continue
        key = normalize_measurement_manager_key(m.get("name"))
        if not key or key in out:
            continue
        out[key] = str(m.get("phone") or "").strip()
    return out


def resolve_manager_phone_from_map(manager_name: str, phone_map: dict[str, str]) -> str:
    """사전 구축된 이름→연락처 map에서 담당자 연락처 조회(설정 재조회 없음)."""
    if not (manager_name or "").strip():
        return ""
    key = normalize_measurement_manager_key(manager_name)
    if not key:
        return ""
    return phone_map.get(key, "")


def resolve_manager_phone_from_measurement_settings(manager_name: str) -> str:
    """ERP 출고 설정의 실측담당자 목록에서 이름이 일치하는 행의 연락처를 반환한다."""
    if not (manager_name or "").strip():
        return ""
    return resolve_manager_phone_from_map(
        manager_name, build_measurement_manager_phone_map()
    )


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


def _coerce_manual_row_after_index(value, item_count: int) -> int:
    try:
        after_index = int(value)
    except (TypeError, ValueError):
        after_index = item_count - 1
    return max(-1, min(after_index, item_count - 1))


def _coerce_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return False


def _extract_estimate_manual_rows(structured_data: dict, item_count: int) -> list[dict]:
    preview = structured_data.get("estimate_preview") or {}
    if not isinstance(preview, dict):
        return []
    raw_rows = preview.get("manual_rows") or []
    if not isinstance(raw_rows, list):
        return []

    rows = []
    for idx, raw_row in enumerate(raw_rows):
        if not isinstance(raw_row, dict):
            continue
        row_id = str(raw_row.get("id") or f"manual_{idx + 1}").strip() or f"manual_{idx + 1}"
        amount_raw = str(raw_row.get("amount") or "").strip()
        rows.append(
            {
                "id": row_id,
                "after_index": _coerce_manual_row_after_index(
                    raw_row.get("after_index"),
                    item_count,
                ),
                "product_name": str(raw_row.get("product_name") or "").strip(),
                "spec": str(raw_row.get("spec") or "").strip(),
                "color": str(raw_row.get("color") or "").strip(),
                "quantity": str(raw_row.get("quantity") or "").strip(),
                "amount": amount_raw,
                "amount_value": _parse_money_amount(amount_raw),
                "affects_total": _coerce_bool(raw_row.get("affects_total")),
            }
        )
    return rows


def _manual_row_to_estimate_item(row: dict) -> dict:
    return {
        "product_name": row.get("product_name") or "",
        "spec": row.get("spec") or "",
        "color": row.get("color") or "",
        "option_detail": "",
        "quantity": row.get("quantity") or "",
        "unit_price": int(row.get("amount_value") or 0),
        "amount": int(row.get("amount_value") or 0),
        "source": "manual",
        "manual_row_id": row.get("id") or "",
        "after_index": int(row.get("after_index", -1)),
        "affects_total": bool(row.get("affects_total")),
        "amount_raw": row.get("amount") or "",
    }


def _merge_estimate_manual_rows(estimate_items: list[dict], manual_rows: list[dict]) -> list[dict]:
    if not manual_rows:
        return estimate_items

    grouped: dict[int, list[dict]] = {}
    for row in manual_rows:
        grouped.setdefault(int(row.get("after_index", -1)), []).append(
            _manual_row_to_estimate_item(row)
        )

    merged = []
    merged.extend(grouped.get(-1, []))
    for idx, item in enumerate(estimate_items):
        merged.append(item)
        merged.extend(grouped.get(idx, []))
    return merged


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


def _extract_discount_amount(structured_data: dict) -> int:
    payment = structured_data.get("payment") or {}
    if isinstance(payment, dict):
        amount = _parse_money_amount(payment.get("discount"))
        if amount > 0:
            return amount
    totals = structured_data.get("totals") or {}
    if isinstance(totals, dict):
        amount = _parse_money_amount(totals.get("discount_amount"))
        if amount > 0:
            return amount
    return 0


def _extract_free_input_text(structured_data: dict) -> str:
    """structured_data에서 자유입력 텍스트를 추출한다."""
    payment = structured_data.get("payment") or {}
    if isinstance(payment, dict) and "free_input" in payment:
        return str(payment.get("free_input") or "").strip()
    legacy_payments = structured_data.get("payments") or {}
    if isinstance(legacy_payments, dict):
        legacy_entry = legacy_payments.get("free_input")
        if isinstance(legacy_entry, dict):
            return str(legacy_entry.get("value") or legacy_entry.get("raw") or "").strip()
        if legacy_entry not in (None, ""):
            return str(legacy_entry).strip()
    return ""


def _balance_after_payments(total_amount: int, deposit_amount: int, discount_amount: int = 0) -> int:
    return max(
        0,
        int(total_amount or 0) - int(deposit_amount or 0) - int(discount_amount or 0),
    )


def _balance_after_deposit(total_amount: int, deposit_amount: int) -> int:
    return _balance_after_payments(total_amount, deposit_amount, 0)


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

    manual_rows = _extract_estimate_manual_rows(sd, len(estimate_items))
    manual_total = sum(
        int(row.get("amount_value") or 0)
        for row in manual_rows
        if row.get("affects_total")
    )
    merged_items = _merge_estimate_manual_rows(estimate_items, manual_rows)

    total_amount = sum(item["amount"] for item in estimate_items) + manual_total
    deposit_amount = _extract_deposit_amount(sd)
    discount_amount = _extract_discount_amount(sd)
    balance_amount = _balance_after_payments(total_amount, deposit_amount, discount_amount)

    return {
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "site_address": site_address,
        "construction_date": construction_date,
        "manager_name": manager_name,
        "manager_phone": manager_phone,
        "is_lahom": is_lahom,
        "items": merged_items,
        "estimate_preview": {"manual_rows": manual_rows},
        "total_amount": total_amount,
        "deposit_amount": int(deposit_amount or 0),
        "discount_amount": int(discount_amount or 0),
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
            "discount_amount",
            "balance_amount",
            "notes",
        ):
            if key in override_data:
                data[key] = override_data[key]

        if "items" in override_data and "total_amount" not in override_data:
            data["total_amount"] = sum(int(item.get("amount") or 0) for item in data["items"])
        if "total_amount" in override_data or "deposit_amount" in override_data or "discount_amount" in override_data:
            data["balance_amount"] = _balance_after_payments(
                data.get("total_amount", 0),
                data.get("deposit_amount", 0),
                data.get("discount_amount", 0),
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
