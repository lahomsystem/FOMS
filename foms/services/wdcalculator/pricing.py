"""계산기 값 — 직원 화면 계산(``static/js/wdcalculator/pricing-core.js``)과 같은 값을 내는 서버 계산(순수 함수).

플랜 ``docs/plans/2026-10-27-cs-ai-agent-plan.md`` C10-6 · 설계서 17.4(원장 R10-24 · V10-1). 정본은 화면 계산이다 — 이 모듈은
그 계산을 그대로 옮긴 것이고, 같은 입력이면 원 단위로 같아야 쓴다(CI 계약 시험
``tests/contracts/wdcalculator/test_server_pricing_contract.py`` 가 node 로 화면 계산을 돌려 견준다).

- :func:`compute_estimate` = ``wdcComputeCurrentEstimateMath``: 구성품(``baseComponents`` — 고른 제품 · 직접 입력 단가 · 구성품
  추가금) + 추가 옵션 줄(이름 · 단가 · 수량). 높이는 화면 계산에 없다(값에 안 들어간다 — 제작 조건 검사에만 쓴다).
- :func:`aggregate_totals` = ``wdcComputeAggregateTotals``(견적 여러 개 합 · 쿠폰 · 운임). CS 견적은 쿠폰 0 · 운임 빼고 쓴다.
- :func:`option_rows` — 옵션 id(``카테고리id:옵션id``)를 서버 옵션 목록에서 찾아 화면의 옵션 줄 꼴(``카테고리 > 옵션``)로.
- :func:`calculate_estimate` · :func:`apply_coupon` — 옛 ``/api/wdcalculator/calculate`` 함수를 값 그대로 옮긴 것(가로만 ·
  옵션 수량 무시). 계산기 길의 값은 바꾸지 않는다(설계서 17.4 경계) — 화면과 같은 값은 :func:`compute_estimate` 다.

JS 와 같게 하려고 숫자는 JS ``Number()`` 규칙으로 읽고(:func:`js_number`), 계산은 같은 순서의 배정밀도 실수다. 원 단위는
JS ``Math.round`` (:func:`won`)다. 네트워크 · DB 가 없다 — 계산기 설정 읽기는 :mod:`.catalog`.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional, Sequence

__all__ = [
    "BRAND_HAUD", "BRAND_LAHOM", "PRICING_TYPES", "EstimateInputError", "EstimateMath", "WidthInputError",
    "aggregate_totals", "apply_coupon", "calculate_estimate", "compute_estimate", "find_product", "js_number",
    "option_rows", "product_brand", "won",
]

BRAND_LAHOM, BRAND_HAUD = "LAHOM", "HAUD"
#: 화면 계산이 아는 가격 방식 — 이 밖이면 화면도 0원이다(CS 는 사람에게).
PRICING_TYPES: tuple[str, ...] = ("1m", "30cm")
#: 제품 이름이 이 말로 시작하면 하우드(처음 채우기 파일엔 브랜드 칸이 없다 — 설계서 17.4 · V10-2).
_HAUD_NAME = re.compile(r"^\s*하우드")
#: JS 숫자 글 꼴(ASCII 숫자만 — 전각 · 아랍 숫자는 JS 에서 NaN 이다, 검수 R17-7).
_JS_NUMBER = re.compile(r"[+-]?(\d+\.?\d*(e[+-]?\d+)?|\.\d+(e[+-]?\d+)?)", re.IGNORECASE | re.ASCII)
_JS_RADIX = {"x": (16, re.compile(r"0x[0-9a-f]+", re.IGNORECASE | re.ASCII)),
             "b": (2, re.compile(r"0b[01]+", re.IGNORECASE | re.ASCII)),
             "o": (8, re.compile(r"0o[0-7]+", re.IGNORECASE | re.ASCII))}
#: JS ``String.prototype.trim`` 이 걷는 글자(공백 · 줄바꿈 · BOM ``﻿`` · 유니코드 Zs).
_JS_SPACE = "\t\n\v\f\r              " \
            "    　﻿"
_ZEROS = re.compile(r"0+(\.0+)?", re.ASCII)


class EstimateInputError(ValueError):
    """화면 계산이 예외를 내는 입력(빈 구성품 · 빈 추가금 칸 등) — 화면도 계산하지 않는다."""


class WidthInputError(EstimateInputError):
    """가로 글을 숫자로 못 읽었다(화면은 알림을 띄우고 계산하지 않는다 — ``validateBaseWidthComponents``)."""


# ── JS 숫자 규칙 ─────────────────────────────────────────────────────────
def _js_string(value: Any) -> str:
    """JS ``String()``(배열 칸 · 숫자 — 배열을 숫자로 바꿀 때 쓴다). 객체는 '[object Object]'."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer() and abs(value) < 1e21:
        return str(int(value))
    if isinstance(value, (int, float, str)):
        return str(value)
    if isinstance(value, list):
        return ",".join(_js_string(item) for item in value)
    return "[object Object]"


def js_number(value: Any) -> float:
    """JS ``Number(value)`` — 못 바꾸면 NaN. ``None`` 은 ``Number(null)`` 처럼 0, 배열은 글로 바꿔 읽는다."""
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, list):
        return js_number(_js_string(value))
    if not isinstance(value, str):
        return math.nan
    text = value.strip(_JS_SPACE)
    if not text:
        return 0.0
    if text in ("Infinity", "+Infinity", "-Infinity"):
        return -math.inf if text.startswith("-") else math.inf
    radix = _JS_RADIX.get(text[1:2].lower()) if text[:1] == "0" else None
    if radix is not None:
        return float(int(text[2:], radix[0])) if radix[1].fullmatch(text) else math.nan
    return float(text) if _JS_NUMBER.fullmatch(text) else math.nan


def _or0(value: float) -> float:
    """JS ``x || 0`` (숫자에 대해) — 0 · NaN 이면 0."""
    return 0.0 if value == 0 or math.isnan(value) else value


def _num0(value: Any) -> float:
    """JS ``Number(value) || 0``."""
    return _or0(js_number(value))


def _truthy(value: Any) -> bool:
    """JS 참 거짓(글 · 숫자 · 없음만)."""
    if value is None or value is False:
        return False
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0 and not math.isnan(value)
    if isinstance(value, str):
        return value != ""
    return True


def _operand(value: Any) -> float:
    """JS ``value || 0`` 을 곱셈에 넣은 값(거짓이면 0, 아니면 ``Number`` 로 바뀐다)."""
    return js_number(value) if _truthy(value) else 0.0


def won(value: float) -> int:
    """원 단위 — JS ``Math.round``(반은 위로). 화면은 이 값으로 금액을 보인다."""
    if not math.isfinite(value):
        raise ValueError("금액이 수가 아니다")
    floor = math.floor(value)
    return int(floor + 1 if value - floor >= 0.5 else floor)


# ── 제품 ─────────────────────────────────────────────────────────────────
def find_product(products: Sequence[Mapping[str, Any]], product_id: Any) -> Optional[Mapping[str, Any]]:
    """화면 ``findProduct`` — 숫자 id 가 같거나 글 id 가 같은 첫 제품(객체가 아닌 칸은 건너뛴다)."""
    if product_id is None or product_id == "":
        return None
    pid = js_number(product_id)
    for row in products or ():
        if not isinstance(row, Mapping):
            continue
        if not math.isnan(pid) and js_number(row.get("id")) == pid:
            return row
        if _js_string(row.get("id")) == _js_string(product_id):
            return row
    return None


def product_brand(product: Mapping[str, Any]) -> str:
    """제품의 브랜드 — 브랜드 칸(``LAHOM`` · ``HAUD``)이 있으면 그것, 없으면 이름('하우드…' = 하우드, 나머지 라홈)."""
    brand = product.get("brand")
    if brand in (BRAND_LAHOM, BRAND_HAUD):
        return brand
    return BRAND_HAUD if _HAUD_NAME.match(str(product.get("name") or "")) else BRAND_LAHOM


# ── 화면 계산 ────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class EstimateMath:
    """``wdcComputeCurrentEstimateMath`` 의 금액 칸(배정밀도 그대로 — 원 단위는 :func:`won`)."""

    base_price_calculate: float
    base_price_collect: float
    additional_price: float
    total_price_calculate: float
    total_price_collect: float
    components: int  # 견적에 담기는 구성품 수(``normalizedComponents``)


def _floor(value: float) -> float:
    """JS ``Math.floor`` — 무한 · NaN 은 그대로(파이썬 ``math.floor`` 는 예외를 낸다)."""
    return float(math.floor(value)) if math.isfinite(value) else value


def _ceil(value: float) -> float:
    """JS ``Math.ceil`` — 무한 · NaN 은 그대로(파이썬 ``math.ceil`` 은 예외를 낸다)."""
    return float(math.ceil(value)) if math.isfinite(value) else value


def _mod(value: float, divisor: float) -> float:
    """JS ``%`` — 무한을 나누면 NaN(파이썬 ``math.fmod`` 는 예외를 낸다)."""
    return math.fmod(value, divisor) if math.isfinite(value) else math.nan


def _get(value: Any, key: str) -> Any:
    """JS ``value.key`` — 객체가 아니면 없음(``undefined``)."""
    return value.get(key) if isinstance(value, Mapping) else None


def _check_width_inputs(components: Sequence[Any]) -> None:
    """화면 ``validateBaseWidthComponents`` — 가로 글이 있는데 0 이하로 읽혔고 '0' 꼴도 아니면 :class:`WidthInputError`."""
    for comp in components or ():
        raw = _js_string(_get(comp, "widthInput") or "").strip(_JS_SPACE)
        if not raw or _num0(_get(comp, "widthMm")) > 0:
            continue
        if _ZEROS.fullmatch("".join(ch for ch in raw if ch not in _JS_SPACE)):
            continue
        raise WidthInputError("가로(mm) 형식을 확인하세요")


def _thirty(width: float, price_30: float, price_1: float) -> float:
    """30cm 단가 + 나머지 1cm 단가(남는 mm 는 1cm 로 올린다 — 화면 그대로, 사장님 지시 11-01: 2,841mm → 2,850mm 값)."""
    return _floor(width / 300) * price_30 + _ceil(_mod(width, 300) / 10) * price_1


def _manual_price(comp: Mapping[str, Any], width: float) -> Optional[float]:
    """직접 입력 단가 구성품의 값 — 단가가 0 이하면 ``None``(화면은 그 구성품을 담지 않는다)."""
    pricing = comp.get("manualPricing")
    if (_get(pricing, "pricing_type") or "30cm") == "1m":
        price_1m = _num0(_get(pricing, "price_1m"))
        return (width / 1000) * price_1m if price_1m > 0 else None
    price_30, price_1 = _num0(_get(pricing, "price_30cm")), _num0(_get(pricing, "price_1cm"))
    return _thirty(width, price_30, price_1) if price_30 > 0 and price_1 > 0 else None


def _select_price(product: Mapping[str, Any], width: float) -> float:
    """고른 제품의 값 — 1m 단가 또는 30cm 단가 + 나머지 1cm 단가(V10-1). 모르는 가격 방식이면 0."""
    if product.get("pricing_type") == "1m":
        return (width / 1000) * _operand(product.get("price_1m"))
    if product.get("pricing_type") == "30cm":
        return _thirty(width, _operand(product.get("price_30cm")), _operand(product.get("price_1cm")))
    return 0.0


def _fee_amounts(fees: Any) -> list[float]:
    """구성품 추가금 칸 → 금액들. 빈 칸(``null``)이면 화면이 예외를 낸다 — :class:`EstimateInputError`."""
    if not isinstance(fees, list):
        return []  # 배열이 아니면 화면은 하나도 돌지 않는다(글이면 글자마다 0)
    if any(fee is None for fee in fees):
        raise EstimateInputError("구성품 추가금 칸이 비었다")
    return [_num0(_get(fee, "amount")) for fee in fees]


def _component(comp: Mapping[str, Any], products: Sequence[Mapping[str, Any]]) -> tuple[float, bool]:
    """구성품 하나 → (값, 견적에 담기나) — 화면 ``computeBaseLayer`` 의 한 바퀴."""
    width = _num0(comp.get("widthMm"))
    amounts = _fee_amounts(comp.get("additionalFees") or [])
    price, kept = 0.0, False
    if width > 0:
        if comp.get("mode") == "manual":
            manual = _manual_price(comp, width)
            price, kept = (manual, True) if manual is not None else (0.0, False)
        else:
            product_id = _num0(comp.get("productId"))
            product = find_product(products, product_id) if product_id else None
            if product is not None:
                price, kept = _select_price(product, width), True
    total_fee = 0.0
    for amount in amounts:  # sum() 은 보정 덧셈이라 JS 차례 덧셈과 끝자리가 갈릴 수 있다 — 차례로 더한다
        total_fee += amount
    if not kept and total_fee > 0:
        kept = True
    for amount in amounts:
        if amount > 0:
            price += amount
    return price, kept


def _options_price(rows: Iterable[Any]) -> float:
    """화면 ``computeOptionsLayer`` 의 금액 — 이름 없거나 단가 0 이하인 줄은 뺀다, 수량이 0 · 없음이면 1."""
    total = 0.0
    for row in rows or ():
        if not _truthy(_get(row, "name")):
            continue
        price, quantity = _num0(row.get("price")), _or0(js_number(row.get("quantity"))) or 1.0
        if price <= 0:
            continue
        total += price * quantity
    return total


def compute_estimate(components: Sequence[Any], products: Sequence[Mapping[str, Any]],
                     options: Sequence[Any] = ()) -> EstimateMath:
    """화면 ``wdcComputeCurrentEstimateMath`` 와 같은 금액.

    Args:
        components: 구성품(``{"mode": "select", "productId", "widthMm", "widthInput"?, "additionalFees": [{"name",
            "amount"}]}`` 또는 ``mode: "manual"`` + ``manualPricing``).
        products: 계산기 제품 목록(계산기 DB 설정 — 처음 채우기 파일이 아니다).
        options: 추가 옵션 줄(``{"name", "price", "quantity"}`` — :func:`option_rows`).

    Raises:
        EstimateInputError: 화면도 계산하지 않는 입력 — 가로 글을 못 읽음(:class:`WidthInputError`) · 빈 구성품 칸 · 빈 추가금 칸.
    """
    _check_width_inputs(components)
    base_calc = base_collect = 0.0
    kept_count = 0
    for comp in components or ():
        if comp is None:
            raise EstimateInputError("구성품 칸이 비었다")
        if not isinstance(comp, Mapping):
            continue  # 객체가 아닌 칸은 화면에서 가로 0 · 추가금 없음 — 값이 없다
        price, kept = _component(comp, products)
        base_calc += price
        if kept:
            base_collect += price
            kept_count += 1
    additional = _options_price(options)
    return EstimateMath(base_calc, base_collect, additional, base_calc + additional, base_collect + additional,
                        kept_count)


def aggregate_totals(estimates: Iterable[Any], coupon_value: Any = 0, shipping_cost: Any = 0,
                     shipping_included: Any = True) -> dict[str, float]:
    """화면 ``wdcComputeAggregateTotals`` — 견적마다 ``basePrice`` · ``additionalPrice`` 합, 쿠폰은 합에 한 번, 운임은 끝 값만."""
    def finite(value: Any) -> float:
        number = js_number(value)
        return number if math.isfinite(number) else 0.0

    base = additional = 0.0
    for est in estimates or ():
        if est is None:
            continue
        base += finite(_get(est, "basePrice"))
        additional += finite(_get(est, "additionalPrice"))
    total = base + additional
    estimate = max(0.0, total - finite(coupon_value))
    final = estimate + finite(shipping_cost) if shipping_included is not False else estimate
    return {"totalBasePrice": base, "totalAdditionalPrice": additional, "totalPrice": total,
            "totalEstimate": estimate, "finalPrice": final}


def option_rows(refs: Iterable[tuple[str, Any]], categories: Sequence[Any]) -> list[dict[str, Any]]:
    """옵션 id(``카테고리id:옵션id``) · 수량 → 화면 옵션 줄(``카테고리 > 옵션`` · 서버 목록의 단가 · 수량).

    객체가 아닌 카테고리 · 옵션 칸(깨진 설정)은 건너뛴다(검수 R17-7).

    Raises:
        KeyError: 서버 목록에 없는 옵션 id.
    """
    index: dict[str, dict[str, Any]] = {}
    for category in categories or ():
        if not isinstance(category, Mapping):
            continue
        for option in category.get("options") or ():
            if not isinstance(option, Mapping):
                continue
            index[f"{category.get('id')}:{option.get('id')}"] = {
                "name": f"{category.get('name')} > {option.get('name')}", "price": option.get("price")}
    rows = []
    for ref, quantity in refs:
        if ref not in index:
            raise KeyError("모르는 옵션 id")
        rows.append({**index[ref], "quantity": quantity})
    return rows


# ── 옛 서버 계산(계산기 API 값 그대로) ──────────────────────────────────
def calculate_estimate(product, width_mm, additional_options=None):
    """옛 견적 계산(``/api/wdcalculator/calculate``) — 가로만 · 옵션 단가 합(수량 무시). 값은 옮기기 전과 같다."""
    if not product:
        return 0
    base_price = 0
    if product['pricing_type'] == '1m':
        meters = width_mm / 1000
        base_price = meters * product.get('price_1m', 0)
    elif product['pricing_type'] == '30cm':
        units_30cm = width_mm // 300
        remainder_mm = width_mm % 300
        units_1cm = -(-remainder_mm // 10)  # 남는 mm 는 1cm 로 올린다(화면과 같게)
        base_price = (units_30cm * product.get('price_30cm', 0)) + (units_1cm * product.get('price_1cm', 0))
    additional_price = 0
    if additional_options:
        for option in additional_options:
            if isinstance(option, dict) and 'price' in option:
                additional_price += float(option.get('price', 0))
    return base_price + additional_price


def apply_coupon(total_price, coupon_type, coupon_value):
    """쿠폰가 적용(옛 API 그대로 — CS 견적은 쿠폰을 쓰지 않는다)."""
    if coupon_type == 'percentage':
        return total_price - (total_price * (float(coupon_value) / 100))
    elif coupon_type == 'fixed':
        return max(0, total_price - float(coupon_value))
    return total_price
