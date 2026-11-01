"""AI 견적 규칙 층 — 사장님 결정 D73: 화면 계산(:func:`.pricing.compute_estimate`) 위에 스토어 규칙을 얹는다(AI 견적 길에서만).

실제 직원 견적 대조에서 어긋난 것(약 13%)은 모두 최소 길이 미만이었고 화면 값보다 35~38% 높았다(화면 계산은 최소 길이를 모른다). 화면
계산 · 계약 시험은 그대로 두고, 이 모듈이 **고친 가로**로 화면 계산을 다시 부른다. 계산기 값 · 값 규칙은 바꾸지 않는다.

- **30cm 가격 방식만** 해당한다. 남는 mm 는 cm 로 올린다(가로를 10mm 단위로 올린 뒤 계산 — 화면은 버린다). 1m 가격 방식은
  화면 계산 그대로다.
- 제품 '견적 규칙 종류' 칸(:data:`RULE_FIELD` — 계산기 제품 설정 화면에서 고른다):
  - ``hinge``(여닫이): 가로 1500mm 미만이면 사람에게(1500 미만 맞춤 공임은 금액이라 코드에 두지 않는다), 그 이상은 올림 계산.
  - ``slide``(슬라이딩): 2400mm 미만이면 2400mm 값(30cm 8개), 그 이상은 올림 계산.
  - ``linear``(cm 비례): cm = 올림(가로 ÷ 10), 값 = 반올림(30cm 단가 × cm ÷ 30) + 화면 옵션 값.
  - ``none``(최소 없음): 올림 계산만.
  - 칸이 비면 이름에 '슬라이딩'이 있으면 ``slide``, 그 밖은 '모름' — 2400mm 미만이면 사람에게, 그 이상은 올림 계산.
- 순수 함수다(네트워크 · DB 없음). 사람에게는 :class:`NeedsHuman`(까닭 코드)로 알린다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Mapping, Sequence

from foms.services.wdcalculator.pricing import compute_estimate, js_number, won

__all__ = [
    "HINGE_MIN_MM", "HUMAN_MIN_WIDTH", "RULES", "RULE_FIELD", "RULE_HINGE", "RULE_LINEAR", "RULE_NONE", "RULE_SLIDE",
    "RULE_UNKNOWN", "SLIDE_MIN_MM", "UNKNOWN_MIN_MM", "NeedsHuman", "RulePrice", "price", "rule_of", "rounded_width",
]

RULE_FIELD = "quote_rule"  # 제품 칸 이름(계산기 제품 설정 화면 '견적 규칙 종류')
RULE_HINGE, RULE_SLIDE, RULE_LINEAR, RULE_NONE, RULE_UNKNOWN = "hinge", "slide", "linear", "none", "unknown"
RULES: tuple[str, ...] = (RULE_HINGE, RULE_SLIDE, RULE_LINEAR, RULE_NONE)
HINGE_MIN_MM, SLIDE_MIN_MM, UNKNOWN_MIN_MM = 1500, 2400, 2400
HUMAN_MIN_WIDTH = "quote_min_width"  # 최소 길이 미만(여닫이 · 모름) — 사람에게
_SLIDE_NAME = "슬라이딩"


class NeedsHuman(ValueError):
    """규칙으로 값을 낼 수 없다 — 사람에게(``args[0]`` = 까닭 코드)."""


@dataclass(frozen=True)
class RulePrice:
    """한 후보 · 한 가로의 AI 견적 값. ``width_used`` = 계산에 쓴 가로(mm), ``note`` = 고친 까닭(없으면 빈 글)."""

    amount: int
    width_used: int
    note: str = ""


def rule_of(product: Mapping[str, Any]) -> str:
    """제품의 견적 규칙 — 칸 값, 비었으면 이름에 '슬라이딩'이 있으면 ``slide``, 그 밖은 ``unknown``(모름)."""
    value = product.get(RULE_FIELD)
    if value in RULES:
        return value
    return RULE_SLIDE if _SLIDE_NAME in str(product.get("name") or "") else RULE_UNKNOWN


def rounded_width(width: int) -> int:
    """남는 mm 를 cm 로 올린 가로(10mm 단위 올림)."""
    return -(-int(width) // 10) * 10


def _screen(product: Mapping[str, Any], width: int, options: Sequence[Mapping[str, Any]],
            products: Sequence[Mapping[str, Any]]) -> int:
    """화면 계산 값(원) — 제품 하나 · 가로 하나 · 옵션 줄. 화면이 그 제품을 못 담으면(id 꼴) ``failed``, 0원이면 ``zero``."""
    got = compute_estimate([{"mode": "select", "productId": product.get("id"), "widthMm": width,
                             "additionalFees": []}], products, options)
    if got.components != 1:
        raise ValueError("failed")
    if not math.isfinite(got.total_price_collect) or got.base_price_collect <= 0:
        raise ValueError("zero")
    amount = won(got.total_price_collect)
    if won(got.base_price_collect) <= 0 or amount <= 0:
        raise ValueError("zero")
    return amount


def _linear(product: Mapping[str, Any], width: int, options: Sequence[Mapping[str, Any]],
            products: Sequence[Mapping[str, Any]]) -> RulePrice:
    """cm 비례 — 반올림(30cm 단가 × cm ÷ 30) + 화면 옵션 값."""
    price_30 = js_number(product.get("price_30cm"))
    if not math.isfinite(price_30) or price_30 <= 0:
        raise ValueError("zero")
    cm = -(-int(width) // 10)
    exact = Fraction(str(price_30)) * cm / 30
    base = math.floor(exact + Fraction(1, 2))
    extra = compute_estimate([], products, options).additional_price
    if base <= 0 or not math.isfinite(extra):
        raise ValueError("zero")
    return RulePrice(won(base + extra), cm * 10, f"cm 비례 {cm:,}cm")


def price(product: Mapping[str, Any], width: int, options: Sequence[Mapping[str, Any]],
          products: Sequence[Mapping[str, Any]]) -> RulePrice:
    """AI 견적 값 하나(모듈 설명의 규칙).

    Raises:
        NeedsHuman: 최소 길이 미만(여닫이 · 모름). ValueError: ``zero``(0원) · ``failed``(화면이 제품을 못 담음).
    """
    if product.get("pricing_type") != "30cm":
        return RulePrice(_screen(product, width, options, products), int(width))
    rule = rule_of(product)
    if rule == RULE_LINEAR:
        return _linear(product, width, options, products)
    if (rule == RULE_HINGE and width < HINGE_MIN_MM) or (rule == RULE_UNKNOWN and width < UNKNOWN_MIN_MM):
        raise NeedsHuman(HUMAN_MIN_WIDTH)
    if rule == RULE_SLIDE and width < SLIDE_MIN_MM:
        return RulePrice(_screen(product, SLIDE_MIN_MM, options, products), SLIDE_MIN_MM,
                         f"슬라이딩 최소 {SLIDE_MIN_MM:,}mm 값")
    used = rounded_width(width)
    return RulePrice(_screen(product, used, options, products), used, "" if used == width else "10mm 단위 올림")
