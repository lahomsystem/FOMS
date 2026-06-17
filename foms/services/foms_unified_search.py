"""Unified ERP mobile search (P1-02): customer / order / drawing groups."""

from __future__ import annotations

import json
from typing import Any, Literal

from sqlalchemy import String, cast, or_
from sqlalchemy.orm import Session

from foms.services.erp_dashboard_search import erp_order_dashboard_search_predicate
from foms.services.erp_display import _ensure_dict, _normalize_for_search
from foms.services.erp_order_deeplink import build_order_queue_focus_href
from foms.services.phone_search import extract_phone_digit_query, normalize_phone_digits
from models import Order

SearchGroup = Literal["all", "customer", "order", "drawing"]

_CHOSUNG = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
_MAX_SQL_ROWS = 80
_MAX_CHOSUNG_SCAN = 200
_MAX_HISTORY_FALLBACK_ROWS = 80


def _compact(text: str | None) -> str:
    """Remove whitespace for comparison."""
    normalized = _normalize_for_search(text)
    return "".join(normalized.split()).lower()


def _to_chosung(text: str) -> str:
    """Hangul syllables → initial consonant jamo string."""
    out: list[str] = []
    for char in text:
        if "가" <= char <= "힣":
            index = (ord(char) - ord("가")) // 588
            out.append(_CHOSUNG[index])
        elif char in _CHOSUNG:
            out.append(char)
        else:
            out.append(char.lower())
    return "".join(out)


def is_chosung_query(query: str) -> bool:
    """True when query is jamo-only (e.g. ㄱㅁㅇ)."""
    compact = _compact(query)
    return bool(compact) and all(ch in _CHOSUNG for ch in compact)


def matches_query(haystack: str | None, query: str) -> bool:
    """Substring or chosung-prefix match."""
    if not query.strip():
        return False
    compact_h = _compact(haystack)
    compact_q = _compact(query)
    if not compact_h or not compact_q:
        return False
    if is_chosung_query(query):
        return _to_chosung(compact_h).startswith(compact_q)
    return compact_q in compact_h


def _order_customer_name(order: Order) -> str:
    sd = _ensure_dict(order.structured_data)
    parties = sd.get("parties") if isinstance(sd.get("parties"), dict) else {}
    customer = parties.get("customer") if isinstance(parties.get("customer"), dict) else {}
    for candidate in (customer.get("name"), order.customer_name):
        text = _normalize_for_search(candidate)
        if text:
            return text
    return _normalize_for_search(order.customer_name)


def _order_phone(order: Order) -> str:
    sd = _ensure_dict(order.structured_data)
    parties = sd.get("parties") if isinstance(sd.get("parties"), dict) else {}
    customer = parties.get("customer") if isinstance(parties.get("customer"), dict) else {}
    return _normalize_for_search(customer.get("phone") or order.phone)


def _order_address(order: Order) -> str:
    """Display address from structured_data site paths, then Order column."""
    sd = _ensure_dict(order.structured_data)
    site = sd.get("site") if isinstance(sd.get("site"), dict) else {}
    for candidate in (
        site.get("address_full"),
        site.get("address_main"),
        order.address,
    ):
        text = _normalize_for_search(candidate)
        if text and text not in {"-", "ERP Order"}:
            return text[:120]
    return ""


def _format_contact_subtitle(phone: str, address: str) -> str:
    """Single-line fallback subtitle: phone · address."""
    parts = [part for part in (phone, address) if part]
    return " · ".join(parts)


def _matches_phone(phone: str | None, erp_phone_digits: str | None, query: str) -> bool:
    """Match formatted phone text or indexed digit column."""
    if matches_query(phone, query):
        return True
    digits_q = extract_phone_digit_query(query)
    if not digits_q:
        return False
    digits_h = erp_phone_digits or normalize_phone_digits(phone)
    return bool(digits_h and digits_q in digits_h)


def _classify_order_hit(order: Order, query: str) -> set[str]:
    """Return search groups matched by this order."""
    groups: set[str] = set()
    customer = _order_customer_name(order)
    phone = _order_phone(order)
    if matches_query(customer, query) or _matches_phone(phone, order.erp_phone_digits, query):
        groups.add("customer")
    order_fields = [
        str(order.id),
        order.product,
        order.address,
        order.manager_name,
    ]
    if any(matches_query(field, query) for field in order_fields):
        groups.add("order")
    stage = (order.erp_stage_code or order.status or "").upper()
    sd = _ensure_dict(order.structured_data)
    drawing_stage = stage in {"DRAWING", "D. 도면"} or "DRAWING" in stage
    has_blueprint = bool(order.blueprint_image_url or sd.get("drawing"))
    if drawing_stage or has_blueprint:
        if matches_query(customer, query) or matches_query(str(order.id), query):
            groups.add("drawing")
        elif matches_query(order.product, query):
            groups.add("drawing")
    return groups


def _history_classify_order_hit(order: Order, query: str) -> set[str]:
    """History fallback: visible fields first, then structured_data blob substring."""
    matched = _classify_order_hit(order, query)
    if matched:
        return matched
    sd = _ensure_dict(order.structured_data)
    if not sd:
        return set()
    try:
        blob_text = json.dumps(sd, ensure_ascii=False)
    except (TypeError, ValueError):
        blob_text = str(sd)
    if matches_query(blob_text, query):
        return {"customer"}
    return set()


def _phone_digit_prefilter(db: Session, query: str):
    """Indexed ``erp_phone_digits`` lookup for digit-heavy queries (P1-02)."""
    digits = extract_phone_digit_query(query)
    if not digits:
        return None
    q = db.query(Order).filter(Order.active_filter(), Order.is_erp_order.is_(True))
    return (
        q.filter(Order.erp_phone_digits.isnot(None))
        .filter(Order.erp_phone_digits.contains(digits))
        .order_by(Order.id.desc())
        .limit(_MAX_SQL_ROWS)
        .all()
    )


def _base_orders_query(db: Session, query: str):
    """SQL prefilter for non-jamo queries."""
    phone_hits = _phone_digit_prefilter(db, query)
    if phone_hits is not None:
        return phone_hits

    q = db.query(Order).filter(Order.active_filter(), Order.is_erp_order.is_(True))
    if is_chosung_query(query):
        return (
            q.order_by(Order.created_at.desc(), Order.id.desc())
            .limit(_MAX_CHOSUNG_SCAN)
            .all()
        )
    term = f"%{_compact(query)}%"
    if not term.strip("%"):
        return []
    return (
        q.filter(erp_order_dashboard_search_predicate(term))
        .order_by(Order.id.desc())
        .limit(_MAX_SQL_ROWS)
        .all()
    )


def _history_style_orders_query(db: Session, query: str) -> list[Order]:
    """
    History dashboard parity: all active orders + structured_data blob ilike.

    PC ``/erp/dashboard`` zero-hit → ``/erp/history`` redirect와 동일한 폭.
    """
    trimmed = _normalize_for_search(query)
    if not trimmed or is_chosung_query(trimmed):
        return []
    term = f"%{_compact(trimmed)}%"
    return (
        db.query(Order)
        .filter(Order.active_filter())
        .filter(
            or_(
                Order.id.cast(String).ilike(term),
                Order.customer_name.ilike(term),
                Order.phone.ilike(term),
                Order.address.ilike(term),
                Order.manager_name.ilike(term),
                cast(Order.structured_data, String).ilike(term),  # perf-ok: ix_orders_structured_data_text_trgm
            )
        )
        .order_by(Order.created_at.desc(), Order.id.desc())
        .limit(_MAX_HISTORY_FALLBACK_ROWS)
        .all()
    )


def _order_search_href(order: Order, search_query: str) -> str:
    """Deep link: ERP queue focus when possible, otherwise order edit."""
    if getattr(order, "is_erp_order", False):
        return build_order_queue_focus_href(order, search_query=search_query)
    return f"/edit/{order.id}?open=erp-order"


def _append_order_hits(
    buckets: dict[str, list[dict[str, Any]]],
    order: Order,
    matched: set[str],
    trimmed: str,
    *,
    limit_per_group: int,
) -> None:
    """Fill customer/order/drawing buckets for one classified hit."""
    customer = _order_customer_name(order)
    phone = _order_phone(order)
    address = _order_address(order)
    contact_subtitle = _format_contact_subtitle(phone, address)
    href = _order_search_href(order, trimmed)
    base = {
        "order_id": order.id,
        "title": customer or f"주문 #{order.id}",
        "phone": phone,
        "address": address,
        "subtitle": contact_subtitle or (order.product or ""),
    }
    if "customer" in matched and len(buckets["customer"]) < limit_per_group:
        buckets["customer"].append(
            {
                **base,
                "group": "customer",
                "href": href,
            }
        )
    if "order" in matched and len(buckets["order"]) < limit_per_group:
        order_subtitle_parts = [part for part in (order.product, phone, address) if part]
        buckets["order"].append(
            {
                **base,
                "group": "order",
                "title": f"#{order.id} · {customer or '주문'}",
                "subtitle": " · ".join(order_subtitle_parts) or contact_subtitle,
                "href": href,
            }
        )
    if "drawing" in matched and len(buckets["drawing"]) < limit_per_group:
        drawing_subtitle_parts = [part for part in (phone, address) if part]
        buckets["drawing"].append(
            {
                **base,
                "group": "drawing",
                "title": f"도면 · #{order.id}",
                "subtitle": " · ".join(drawing_subtitle_parts) or customer,
                "href": href,
            }
        )


def _buckets_have_hits(buckets: dict[str, list[dict[str, Any]]]) -> bool:
    return any(buckets[group] for group in ("customer", "order", "drawing"))


def _collect_search_hits(
    db: Session,
    query: str,
    *,
    limit_per_group: int,
) -> dict[str, list[dict[str, Any]]]:
    """Run ERP queue search, then history-breadth fallback when empty."""
    buckets: dict[str, list[dict[str, Any]]] = {
        "customer": [],
        "order": [],
        "drawing": [],
    }
    trimmed = _normalize_for_search(query)
    if not trimmed:
        return buckets

    seen_ids: set[int] = set()
    for order in _base_orders_query(db, trimmed):
        matched = _classify_order_hit(order, trimmed)
        if not matched:
            continue
        seen_ids.add(int(order.id))
        _append_order_hits(buckets, order, matched, trimmed, limit_per_group=limit_per_group)

    if not _buckets_have_hits(buckets):
        for order in _history_style_orders_query(db, trimmed):
            if int(order.id) in seen_ids:
                continue
            matched = _history_classify_order_hit(order, trimmed)
            if not matched:
                continue
            seen_ids.add(int(order.id))
            _append_order_hits(buckets, order, matched, trimmed, limit_per_group=limit_per_group)

    return buckets


def search_unified(
    db: Session,
    query: str,
    *,
    group: SearchGroup = "all",
    limit_per_group: int = 8,
) -> dict[str, list[dict[str, Any]]]:
    """
    Search ERP orders into customer / order / drawing buckets.

    Args:
        db: SQLAlchemy session.
        query: User search string (supports chosung prefix).
        group: Filter to one bucket or ``all``.
        limit_per_group: Max hits per bucket.

    Returns:
        Dict of group id → list of result dicts.
    """
    buckets: dict[str, list[dict[str, Any]]] = {
        "customer": [],
        "order": [],
        "drawing": [],
    }
    trimmed = _normalize_for_search(query)
    if not trimmed:
        return buckets

    buckets = _collect_search_hits(db, trimmed, limit_per_group=limit_per_group)

    if group == "all":
        return buckets
    return {group: buckets.get(group, [])}
