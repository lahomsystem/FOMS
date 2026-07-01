"""Unified ERP mobile search (P1-02): customer / order / drawing groups."""

from __future__ import annotations

import json
from typing import Any, Literal

from sqlalchemy import String, and_, cast, or_
from sqlalchemy.orm import Session

from foms.services.erp_dashboard_search import erp_order_dashboard_search_predicate
from foms.services.erp_display import _ensure_dict, _erp_get_stage, _normalize_for_search
from foms.services.erp_order_deeplink import build_order_queue_focus_href, resolve_order_stage_code
from foms.services.erp_mobile_order_display import (
    format_queue_card_schedule_summary,
    resolve_queue_card_schedule,
)
from foms.services.erp_policy import STAGE_LABELS
from foms.services.phone_search import extract_phone_digit_query, normalize_phone_digits
from models import Order

SearchGroup = Literal["all", "customer", "order", "drawing"]

_CHOSUNG = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
# 흔한 성씨(김·이·박 등) 검색에서 오래된 주문이 newest-N 캡에 잘려 누락되던 문제(A4)를
# 줄이기 위해 후보 폭을 넓힌다. 후보는 Python 분류기를 거치므로 trgm 인덱스 + 200ms 디바운스
# 하에서 안전한 범위로만 상향한다.
_MAX_SQL_ROWS = 300
_MAX_CHOSUNG_SCAN = 400
_MAX_HISTORY_FALLBACK_ROWS = 200


def _compact(text: str | None) -> str:
    """Remove whitespace for comparison."""
    normalized = _normalize_for_search(text)
    return "".join(normalized.split()).lower()


def _search_tokens(query: str | None) -> list[str]:
    """
    공백 기준 토큰 분리(A5). 다중 토큰은 AND·어순 무관으로 매칭한다.

    "부평구 인천"처럼 단어 순서가 DB값("인천 부평구")과 달라도, 각 토큰을 trgm
    인덱스 ilike로 따로 매칭해 교집합을 취하면 누락 없이 잡힌다. 공백 strip으로
    DB 공백값과 ilike가 어긋나던 문제도 함께 해소한다. 단일 토큰은 기존 동작과 동일.
    """
    normalized = _normalize_for_search(query)
    return [tok for tok in normalized.split() if tok]


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


def _order_extra_text_fields(order: Order) -> list[str]:
    """
    structured_data 가시 경로 텍스트 — SQL 후보(erp_order_dashboard_search_predicate)와
    분류기 필드 폭을 일치시킨다.

    SQL은 SD parties.manager/orderer·site 주소·items 상품명·일정 날짜까지 후보로
    뽑지만 분류기가 레거시 컬럼만 보면 SD에만 값이 있는 ERP 주문이 조용히 탈락한다.
    """
    sd = _ensure_dict(order.structured_data)
    parties = sd.get("parties") if isinstance(sd.get("parties"), dict) else {}
    site = sd.get("site") if isinstance(sd.get("site"), dict) else {}
    schedule = sd.get("schedule") if isinstance(sd.get("schedule"), dict) else {}
    manager = parties.get("manager") if isinstance(parties.get("manager"), dict) else {}
    orderer = parties.get("orderer") if isinstance(parties.get("orderer"), dict) else {}
    measurement = schedule.get("measurement") if isinstance(schedule.get("measurement"), dict) else {}
    construction = schedule.get("construction") if isinstance(schedule.get("construction"), dict) else {}
    fields: list[Any] = [
        manager.get("name"),
        orderer.get("name"),
        site.get("address_full"),
        site.get("address_main"),
        measurement.get("date"),
        construction.get("date"),
    ]
    items = sd.get("items") if isinstance(sd.get("items"), list) else []
    for item in items:
        if isinstance(item, dict):
            fields.append(item.get("product_name"))
            fields.append(item.get("name"))
    return [str(value) for value in fields if value]


def _classify_order_hit(order: Order, query: str) -> set[str]:
    """
    Return search groups matched by this order.

    다중 토큰(A5)은 그룹별 필드 집합 안에서 '모든 토큰이 각각 어떤 필드엔가 매칭'될 때
    히트로 본다(어순 무관). 단일 토큰은 ``all([x]) == x``라 기존 OR 동작과 동일.
    """
    tokens = _search_tokens(query) or [query]
    groups: set[str] = set()
    customer = _order_customer_name(order)
    phone = _order_phone(order)
    extra_fields = _order_extra_text_fields(order)

    def _all_tokens_in(fields: list[str], *, with_phone: bool = False) -> bool:
        for tok in tokens:
            if any(matches_query(field, tok) for field in fields):
                continue
            if with_phone and _matches_phone(phone, order.erp_phone_digits, tok):
                continue
            return False
        return True

    if _all_tokens_in([customer], with_phone=True):
        groups.add("customer")
    order_fields = [
        str(order.id),
        order.product,
        order.address,
        order.manager_name,
        *extra_fields,
    ]
    if _all_tokens_in(order_fields):
        groups.add("order")
    stage = (order.erp_stage_code or order.status or "").upper()
    sd = _ensure_dict(order.structured_data)
    drawing_stage = stage in {"DRAWING", "D. 도면"} or "DRAWING" in stage
    has_blueprint = bool(order.blueprint_image_url or sd.get("drawing"))
    if drawing_stage or has_blueprint:
        if _all_tokens_in([customer, str(order.id)]):
            groups.add("drawing")
        elif _all_tokens_in([order.product, *extra_fields]):
            groups.add("drawing")
    # 다중 토큰이 그룹 경계를 가로지르면(예: "남궁 인천" = 고객명+주소) 정밀 그룹엔
    # 안 잡히지만 SQL 후보(predicate AND)엔 들어온다. 전체 가시 필드로 모든 토큰이
    # 매칭되면 고객 그룹에 노출해 누락을 막는다(단일 토큰은 위에서 이미 처리).
    if not groups and len(tokens) > 1:
        global_fields = [customer, *order_fields]
        if _all_tokens_in(global_fields, with_phone=True):
            groups.add("customer")
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
    tokens = _search_tokens(query) or [query]
    if all(matches_query(blob_text, tok) for tok in tokens):
        return {"customer"}
    return set()


def _order_id_prefilter(db: Session, query: str):
    """
    주문번호 직검색: 순수 숫자 쿼리(``#`` 접두 허용)는 ``Order.id`` 단건을 직접 조회한다.

    폰 자릿수 경로(``erp_phone_digits``)가 4자리+ 숫자를 가로채기 전에 호출해,
    "4114" 같은 주문번호가 자기 id로 조회되지 않던 누락을 막는다.
    """
    raw = (query or "").strip().lstrip("#").strip()
    if not raw.isdigit():
        return None
    try:
        order_id = int(raw)
    except ValueError:
        return None
    # 비현실적 큰 값(전화번호 등)은 id로 취급하지 않는다.
    if order_id <= 0 or order_id > 2_000_000_000:
        return None
    return (
        db.query(Order)
        .filter(Order.active_filter(), Order.id == order_id)
        .limit(1)
        .all()
    )


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


def _term_prefilter(db: Session, query: str):
    """
    가시 컬럼 + structured_data 가시 경로 ILIKE 후보.

    다중 토큰은 각 토큰 술어를 AND로 묶어 어순 무관·공백 보존 매칭한다(A5).
    각 토큰은 OR-over-fields 술어라 토큰별로 다른 필드에 걸려도 된다.
    """
    tokens = _search_tokens(query)
    if not tokens:
        return []
    q = db.query(Order).filter(Order.active_filter(), Order.is_erp_order.is_(True))
    clauses = [erp_order_dashboard_search_predicate(f"%{tok}%") for tok in tokens]
    return (
        q.filter(and_(*clauses))
        .order_by(Order.id.desc())
        .limit(_MAX_SQL_ROWS)
        .all()
    )


def _base_orders_query(db: Session, query: str):
    """
    SQL prefilter 후보를 여러 경로에서 모아 중복 제거한다.

    숫자 쿼리가 폰 경로로 단락(short-circuit)되며 주문번호·이름 매치를 버리던
    문제를 막기 위해, id/phone/term 후보를 모두 합집합으로 수집한다.
    """
    candidates: list[Order] = []
    seen: set[int] = set()

    def _extend(rows) -> None:
        for order in rows or []:
            oid = int(order.id)
            if oid in seen:
                continue
            seen.add(oid)
            candidates.append(order)

    # 1) 주문번호 직검색(순수 숫자) — 폰 경로보다 먼저.
    _extend(_order_id_prefilter(db, query))

    # 초성 쿼리는 ILIKE term이 자모라 의미가 없으므로 별도 스캔만 수행.
    if is_chosung_query(query):
        chosung_rows = (
            db.query(Order)
            .filter(Order.active_filter(), Order.is_erp_order.is_(True))
            .order_by(Order.created_at.desc(), Order.id.desc())
            .limit(_MAX_CHOSUNG_SCAN)
            .all()
        )
        _extend(chosung_rows)
        return candidates

    # 2) 폰 자릿수 인덱스 경로.
    _extend(_phone_digit_prefilter(db, query))
    # 3) 가시 필드 ILIKE 경로.
    _extend(_term_prefilter(db, query))
    return candidates


def _history_style_orders_query(db: Session, query: str) -> list[Order]:
    """
    History dashboard parity: all active orders + structured_data blob ilike.

    PC ``/erp/dashboard`` zero-hit → ``/erp/history`` redirect와 동일한 폭.
    """
    trimmed = _normalize_for_search(query)
    if not trimmed or is_chosung_query(trimmed):
        return []
    tokens = _search_tokens(trimmed)
    if not tokens:
        return []

    def _token_clause(tok: str):
        term = f"%{tok}%"
        return or_(
            Order.id.cast(String).ilike(term),  # perf-ok: bounded id search admin/cold path
            Order.customer_name.ilike(term),  # perf-ok: ix_orders_customer_name_trgm
            Order.phone.ilike(term),  # perf-ok: ix_orders_phone_trgm
            Order.address.ilike(term),  # perf-ok: ix_orders_address_trgm
            Order.manager_name.ilike(term),  # perf-ok: ix_orders_manager_name_trgm
            cast(Order.structured_data, String).ilike(term),  # perf-ok: ix_orders_structured_data_text_trgm
        )

    return (
        db.query(Order)
        .filter(Order.active_filter())
        .filter(and_(*[_token_clause(tok) for tok in tokens]))
        .order_by(Order.created_at.desc(), Order.id.desc())
        .limit(_MAX_HISTORY_FALLBACK_ROWS)
        .all()
    )


def _order_stage_label(order: Order) -> str:
    """Human-readable workflow stage for search disambiguation."""
    code = resolve_order_stage_code(order)
    return STAGE_LABELS.get(code, code) or "-"


def _order_schedule_dates(order: Order) -> tuple[str | None, str | None]:
    """Measurement/construction dates from structured_data schedule."""
    sd = _ensure_dict(order.structured_data)
    schedule = sd.get("schedule") if isinstance(sd.get("schedule"), dict) else {}
    measurement = schedule.get("measurement") if isinstance(schedule.get("measurement"), dict) else {}
    construction = schedule.get("construction") if isinstance(schedule.get("construction"), dict) else {}
    return measurement.get("date"), construction.get("date")


def _order_schedule_summary(order: Order) -> str:
    """Compact schedule line for search overlay disambiguation."""
    sd = _ensure_dict(order.structured_data)
    meas, cons = _order_schedule_dates(order)
    schedule = resolve_queue_card_schedule(
        stage=_erp_get_stage(order, sd),
        stage_code=resolve_order_stage_code(order),
        measurement_date=meas,
        construction_date=cons,
    )
    return format_queue_card_schedule_summary(schedule)


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
    stage_label = _order_stage_label(order)
    contact_subtitle = _format_contact_subtitle(phone, address)
    schedule_summary = _order_schedule_summary(order)
    href = _order_search_href(order, trimmed)
    base = {
        "order_id": order.id,
        "title": customer or f"주문 #{order.id}",
        "phone": phone,
        "address": address,
        "stage_label": stage_label,
        "schedule_summary": schedule_summary,
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


def _relevance_rank(order: Order, trimmed: str) -> tuple[int, int]:
    """
    후보 정렬 키(A4): 고객명 정확 > 접두 > 부분 > 기타 필드, 동순위는 최신 주문 우선.

    newest-N 캡 안에서 부분일치 신규 주문이 정확일치 과거 주문의 8칸을 빼앗던 문제를 막아,
    검색어에 가장 가까운 주문이 그룹 상위에 노출되게 한다.
    """
    cq = _compact(trimmed)
    name = _compact(_order_customer_name(order))
    try:
        recency = -int(order.id)
    except (TypeError, ValueError):
        recency = 0
    if not cq or not name:
        return (3, recency)
    if name == cq:
        return (0, recency)
    if name.startswith(cq):
        return (1, recency)
    if cq in name:
        return (2, recency)
    return (3, recency)


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
    primary: list[tuple[Order, set[str]]] = []
    for order in _base_orders_query(db, trimmed):
        matched = _classify_order_hit(order, trimmed)
        if not matched:
            continue
        seen_ids.add(int(order.id))
        primary.append((order, matched))
    # 관련도 정렬 후 슬롯 채움 — 정확/접두 일치가 부분일치보다 먼저 8칸을 차지한다.
    primary.sort(key=lambda pair: _relevance_rank(pair[0], trimmed))
    for order, matched in primary:
        _append_order_hits(buckets, order, matched, trimmed, limit_per_group=limit_per_group)

    # 레거시·비-ERP 주문은 1차(ERP) 스캔에 없으므로, 버킷이 가득 차지 않은 한 항상
    # history 폭(active 전체 + 깊은 필드)을 병합한다. 기존엔 ERP 히트가 하나라도 있으면
    # 폴백을 건너뛰어 레거시 주문이 영구히 숨던 누락을 막는다.
    buckets_full = all(
        len(buckets[group]) >= limit_per_group
        for group in ("customer", "order", "drawing")
    )
    if not buckets_full:
        fallback: list[tuple[Order, set[str]]] = []
        for order in _history_style_orders_query(db, trimmed):
            if int(order.id) in seen_ids:
                continue
            matched = _history_classify_order_hit(order, trimmed)
            if not matched:
                continue
            seen_ids.add(int(order.id))
            fallback.append((order, matched))
        fallback.sort(key=lambda pair: _relevance_rank(pair[0], trimmed))
        for order, matched in fallback:
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
