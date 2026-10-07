"""정산 대시보드 "제품별 매출" 탭 집계 (읽기 전용, 2026-10-07 사용자 승인 계약).

요약 탭의 예상/실제 매출(:func:`foms.services.settlement_aggregation.aggregate_settlement` 의
``forecast``)을 **같은 모집단·같은 축**에서 제품군·시리즈로 나눈다.

- 모집단: 살아 있는 ERP 주문(``_erp_scope_filters``) 중 시공일(``completion_day_key``)이 구간 안.
  예상 = 그 전부, 실제 = 시공완료(``ORDER_SETTLEMENT_ALERT_TARGET_STATUSES``).
- 주문 매출 = 출고가(``erp_shipping_price_from_structured``, 미산출은 0) — 요약 탭과 같은 값.
- 품목 몫 = 출고가를 품목 단가(``_erp_coerce_item_price_krw`` — 출고가의 품목합 폴백과 같은
  해석, 수량 곱 없음) 비율로 **최대 잔여 배분**해 원 단위까지 정확히 나눈다. 그래서 제품군 합 ==
  예상 매출, 실제 합 == ``kpi.revenue`` 가 항등식이다(테스트가 고정). 할인·자유입력(배송 등)은
  출고가에 이미 들어 있어 품목 비율대로 함께 나뉜다.
- 품목이 없는 주문은 전액 미입력(PLACEHOLDER)·기본 시리즈, 품목 수 0 이다. 단가 합이 0 이면 첫
  품목이 전액을 진다.
- 채널: 일반/라홈은 ``brand_channel_of``, 네이버는 라홈 안의 부분값(shop in shop).

분류 규칙은 :mod:`foms.services.settlement_product_rules` 가 정본이다. 문서는 품명까지 실은
얇은 투영(:data:`PRODUCTS_SD_SPEC`)으로 한 번만 읽는다(N+1 없음, 채널 맵 배치 쿼리 1회 별도).

이 모듈은 읽기 전용이다 — 커밋·flag_modified·Order 속성 대입을 하지 않는다.
"""
from __future__ import annotations

import calendar
import datetime
from collections import Counter, defaultdict
from typing import Any, Optional

# 순서 주의: `foms.services.orders.*` 를 `erp_display` 보다 먼저 둔다(settlement_aggregation
# 상단 주석의 순환 회피와 같은 것).
from foms.services.orders.erp_policy_constants import ORDER_SETTLEMENT_ALERT_TARGET_STATUSES
from foms.services.datetime_kst import get_today_kst
from foms.services.erp_display import (
    _ensure_dict,
    _erp_coerce_item_price_krw,
    erp_shipping_price_from_structured,
)
from foms.services.settlement_aggregation import (
    _DEFAULT_CHANNEL,
    _NAVER_CHANNEL,
    BRAND_LAHOM,
    _channel_map,
    _erp_scope_filters,
    brand_channel_of,
    completion_day_key,
    parse_day_range,
)
from foms.services.settlement_product_rules import (
    FAMILIES,
    FAMILY_CODES,
    SERIES,
    SERIES_BASIC,
    SERIES_CODES,
    family,
    series,
)
from foms.services.settlement_source import ARRAY_ITEMS, fetch_settlement_rows
from models import Order

__all__ = ["PRODUCTS_SD_SPEC", "aggregate_products", "allocate"]

#: 이 탭이 읽는 경로만 남긴 투영 나무. 출고가(품목합·자유입력·할인), 완료일, 발주사, 품명·단가.
PRODUCTS_SD_SPEC: dict[str, Any] = {
    "items": {ARRAY_ITEMS: {"price": None, "product_name": None}},
    "totals": None,
    "parties": {"orderer": {"name": None}},
    "payment": None,
    "payments": None,
    "schedule": {"construction": {"date": None}},
}

#: 추이 카드의 개월 수(구간 끝 달로 끝난다).
_TREND_MONTHS = 12
#: 제품군별 대표 품명 수 / 분류 안 된 품명 수.
_TOP_NAMES_LIMIT = 8
_UNMAPPED_LIMIT = 30
_PLACEHOLDER = "PLACEHOLDER"
_OTHER = "OTHER"


def allocate(total: int, weights: list[int]) -> Optional[list[int]]:
    """``total`` 을 ``weights`` 비율로 정수 배분한다(최대 잔여 배분 — 합이 정확히 ``total``).

    몫을 내림으로 먼저 주고, 남은 원을 나머지가 큰 순서(같으면 앞 품목)대로 1원씩 준다.

    Args:
        total: 나눌 금액(0 이상 정수).
        weights: 품목 단가(0 이상 정수).

    Returns:
        배분 목록. 가중치 합이 0 이하이면 None(호출자가 첫 품목에 전액을 준다).
    """
    weight_sum = sum(weights)
    if weight_sum <= 0:
        return None
    shares = [total * weight // weight_sum for weight in weights]
    remainder = total - sum(shares)
    order = sorted(range(len(weights)), key=lambda i: -((total * weights[i]) % weight_sum))
    for index in order[:remainder]:
        shares[index] += 1
    return shares


def _order_lines(sd: dict, shipping: int) -> tuple[int, list[tuple[str, str, int, int, Optional[str]]]]:
    """주문 1건 → (품목 단가 합, [(제품군, 시리즈, 단가, 배분 매출, 품명|None)]).

    품명이 None 인 줄은 품목 없는 주문의 자리줄이다(품목 수에 들지 않는다). dict 가 아닌
    원소도 품목 자리로 센다(이름 '' · 단가 0 — 출고가 품목합 폴백이 원소 수를 세는 것과 같다).
    """
    items = sd.get("items")
    if not isinstance(items, list) or not items:
        return 0, [(_PLACEHOLDER, SERIES_BASIC, 0, shipping, None)]
    parsed = [
        (str(item.get("product_name") or "") if isinstance(item, dict) else "",
         _erp_coerce_item_price_krw(item))
        for item in items
    ]
    prices = [price for _, price in parsed]
    shares = allocate(shipping, prices) or [shipping] + [0] * (len(parsed) - 1)
    lines = [(family(name), series(name), price, shares[index], name)
             for index, (name, price) in enumerate(parsed)]
    return sum(prices), lines


def _blank_entry() -> dict:
    """FAMILY_ENTRY 빈 값(계약 스키마 — 모든 시리즈 키를 0 으로 둔다)."""
    return {
        "expected": 0, "expected_raw": 0, "expected_items": 0, "expected_orders": 0,
        "actual": 0, "actual_raw": 0, "actual_items": 0, "actual_orders": 0,
        "general": {"expected": 0, "actual": 0},
        "lahom": {"expected": 0, "actual": 0},
        "naver": {"expected": 0, "actual": 0},
        "series": {code: {"expected": 0, "actual": 0, "expected_items": 0, "actual_items": 0}
                   for code in SERIES_CODES},
    }


def _month_keys_between(start: datetime.date, end: datetime.date) -> list[str]:
    """[start, end] 가 걸친 달 키("YYYY-MM") 목록."""
    first = start.year * 12 + start.month - 1
    last = end.year * 12 + end.month - 1
    return [f"{i // 12:04d}-{i % 12 + 1:02d}" for i in range(first, last + 1)]


def _trend_months(end: datetime.date) -> list[str]:
    """``end`` 의 달로 끝나는 12개월 키."""
    last = end.year * 12 + end.month - 1
    return [f"{i // 12:04d}-{i % 12 + 1:02d}" for i in range(last - _TREND_MONTHS + 1, last + 1)]


def _resolve_range(date_from: Any, date_to: Any) -> tuple[datetime.date, datetime.date]:
    """조회 구간. 둘 다 없으면 이번 달(KST), 아니면 ``parse_day_range`` 검증 그대로."""
    if date_from is None and date_to is None:
        today = get_today_kst()  # date 를 돌려준다 — .date() 를 부르지 않는다.
        last_day = calendar.monthrange(today.year, today.month)[1]
        return today.replace(day=1), today.replace(day=last_day)
    return parse_day_range(date_from, date_to)


def _add_period(entry: dict, line: tuple, *, done: bool, brand_key: str, naver: bool) -> None:
    """구간 합계 FAMILY_ENTRY 에 품목 줄 하나를 더한다(주문 수는 호출자가 센다)."""
    _family, series_code, price, revenue, name = line
    is_item = int(name is not None)
    bucket = entry["series"][series_code]
    fields = ("expected", "actual") if done else ("expected",)
    for field in fields:
        entry[field] += revenue
        entry[f"{field}_raw"] += price
        entry[f"{field}_items"] += is_item
        entry[brand_key][field] += revenue
        if naver:
            entry["naver"][field] += revenue
        bucket[field] += revenue
        bucket[f"{field}_items"] += is_item


def _ranked(counter: Counter) -> list[tuple[str, int]]:
    """건수 내림차순, 같으면 이름순(조회 행 순서와 무관하게 결정적)."""
    return sorted(counter.items(), key=lambda pair: (-pair[1], pair[0]))


def aggregate_products(db: Any, *, date_from: Optional[str] = None,
                       date_to: Optional[str] = None) -> dict:
    """제품별 매출 탭 집계(계약 ``data``).

    Args:
        db: SQLAlchemy Session.
        date_from: 시공일 구간 시작 "YYYY-MM-DD"(포함). 둘 다 없으면 이번 달(KST).
        date_to: 시공일 구간 끝 "YYYY-MM-DD"(포함).

    Returns:
        range/families/series/period/trend/selected_months/top_names/unmapped_top/coverage/
        allocation_check 키를 가진 dict.

    Raises:
        ValueError: 날짜 형식 오류·한쪽만 지정·범위 역전·366일 초과(``parse_day_range``).
    """
    start, end = _resolve_range(date_from, date_to)
    lo, hi = start.isoformat(), end.isoformat()
    trend_months = _trend_months(end)
    trend_set = set(trend_months)

    period = {code: _blank_entry() for code in FAMILY_CODES}
    by_month = {month: {code: {"expected": 0, "actual": 0} for code in FAMILY_CODES}
                for month in trend_months}
    names: dict[str, Counter] = defaultdict(Counter)
    other_amounts: Counter = Counter()
    check = {"orders": 0, "sum_shipping": 0, "sum_raw_items": 0}
    items_total = items_other = 0

    channels = _channel_map(db)
    rows = fetch_settlement_rows(db, (Order.id, Order.status), _erp_scope_filters(),
                                 spec=PRODUCTS_SD_SPEC)
    for row in rows:
        sd = _ensure_dict(row.structured_data)
        # 완료일 읽기는 집계 커널 ``_settlement_row`` 와 같은 식이다(모집단 판정이 갈리지 않게).
        day = completion_day_key(
            ((sd.get("schedule") or {}).get("construction") or {}).get("date"))
        in_range = bool(day) and lo <= day <= hi
        month = day[:7]
        if not in_range and month not in trend_set:
            continue
        done = row.status in ORDER_SETTLEMENT_ALERT_TARGET_STATUSES
        channel = channels.get(int(row.id), _DEFAULT_CHANNEL)
        shipping = erp_shipping_price_from_structured(sd)
        shipping = shipping if isinstance(shipping, int) else 0
        raw_sum, lines = _order_lines(sd, shipping)

        if month in trend_set:
            for line in lines:
                cell = by_month[month][line[0]]
                cell["expected"] += line[3]
                if done:
                    cell["actual"] += line[3]
        if not in_range:
            continue

        check["orders"] += 1
        check["sum_shipping"] += shipping
        check["sum_raw_items"] += raw_sum
        brand_key = "lahom" if brand_channel_of(sd, channel) == BRAND_LAHOM else "general"
        naver = channel == _NAVER_CHANNEL
        for line in lines:
            _add_period(period[line[0]], line, done=done, brand_key=brand_key, naver=naver)
            name = line[4]
            if name is None:
                continue
            label = name.strip()
            names[line[0]][label] += 1
            items_total += 1
            if line[0] == _OTHER:
                items_other += 1
                other_amounts[label] += line[2]
        for family_code in {line[0] for line in lines}:
            period[family_code]["expected_orders"] += 1
            if done:
                period[family_code]["actual_orders"] += 1

    total_expected = sum(entry["expected"] for entry in period.values())
    return {
        "range": {"date_from": lo, "date_to": hi},
        "families": [{"code": code, "label": label} for code, label in FAMILIES],
        "series": [{"code": code, "label": label} for code, label in SERIES],
        "period": period,
        "trend": {"months": trend_months, "by_month": by_month},
        "selected_months": _month_keys_between(start, end),
        "top_names": {code: [[label, count] for label, count in
                             _ranked(names[code])[:_TOP_NAMES_LIMIT]]
                      for code in FAMILY_CODES},
        "unmapped_top": [[label, count, other_amounts[label]] for label, count in
                         _ranked(names[_OTHER])[:_UNMAPPED_LIMIT]],
        "coverage": {
            "items_total": items_total,
            "items_other": items_other,
            "revenue_other_share": (round(period[_OTHER]["expected"] / total_expected, 5)
                                    if total_expected else 0.0),
        },
        "allocation_check": check,
    }
