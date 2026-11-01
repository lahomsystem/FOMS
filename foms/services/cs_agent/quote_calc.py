"""견적 계산 — 뽑은 견적 재료로 제작 조건을 보고 계산기 값을 낸다(순수 함수 — 네트워크 · DB 없음).

플랜 C10-6 · 설계서 17.4 길 2 · 3 · 5(원장 R10-24 · R10-25). 금액은 :func:`foms.services.wdcalculator.pricing.compute_estimate`
(직원 화면 계산과 원 단위로 같은 서버 계산 — CI 계약 시험)만 낸다. 쿠폰 · 운임은 넣지 않는다. 결과(:func:`evaluate`):

- **ok** — 계산기 줄(두뇌 ``calculator_lines`` 재료)과 같은 줄을 금액 허용 목록에 더한다. 확인 날 줄은 허용 목록에 넣지 않는다.
- **needs_check** — 계산기 설정 저장(= 가격 확인 날) 뒤 14일이 지났거나 확인 날이 없다(처음 채우기 파일). 금액은 손님 글에 쓰지
  않고 직원 참고 칸에만(설계서 7.1 의 5) — 허용 목록에 더하지 않는다.
- **ask** — 계산에 꼭 필요한 칸(제품 · 가로, 제작 조건이 보는 높이 · 문 방식)을 모른다. 한 가지만 묻게 한다(제품 → 가로 →
  높이 → 문 방식 차례).
- **human** — 사람에게: 하우드(이번 범위 밖) · 제작 조건에 안 맞음 · 제작 조건 글을 못 읽음 · 모르는 가격 방식 · 0원 · 계산 실패.

**제작 조건(build_rule)**: 지식 문서의 ``build_rule`` 항목 글에서 ``검사:`` 로 시작하는 줄만 코드가 읽는다(그 밖의 글은 두뇌
재료일 뿐). 꼴: ``검사: product=7,24 min_width=600 max_width=4800 max_height=2400 door=hinged`` — ``product`` 가 없으면
모든 라홈 제품, 나머지 칸은 있는 것만 본다(mm · ``door`` 는 hinged · sliding 쉼표 목록 = 되는 문 방식). 항목이 없으면 빈 규칙.
"""

from __future__ import annotations

import datetime
import math
import re
from dataclasses import dataclass
from typing import Any, Iterable, Optional, Sequence

from foms.services.cs_agent.quote_brain import DOORS, HANDLES, QuoteAsk, QuoteSpace
from foms.services.wdcalculator.catalog import FRESH_DAYS, Catalog
from foms.services.wdcalculator.pricing import (
    BRAND_HAUD, PRICING_TYPES, compute_estimate, find_product, option_rows, won,
)

__all__ = [
    "ASK_ORDER", "KIND_BUILD_RULE", "STATUS_ASK", "STATUS_CHECK", "STATUS_HUMAN", "STATUS_OK", "BuildRule",
    "QuoteOutcome", "RuleUnreadable", "build_rules", "evaluate",
]

KIND_BUILD_RULE = "build_rule"  # 지식 문서 종류 이름(설계서 17.5 — 그 종류가 문서에 들어오면 여기서 읽는다)
STATUS_OK, STATUS_CHECK, STATUS_ASK, STATUS_HUMAN = "ok", "needs_check", "ask", "human"
#: 사람에게 넘기는 까닭 코드(차례 기록 ``error_code`` · 넘김 칸 — 글이 아니다).
HUMAN_BRAND, HUMAN_RULE, HUMAN_RULE_UNREADABLE = "quote_brand", "quote_build_rule", "quote_rule_unreadable"
HUMAN_PRICING_TYPE, HUMAN_ZERO, HUMAN_FAILED = "quote_pricing_type", "quote_zero", "quote_calc_failed"
#: 모르면 묻는 차례와 손님께 물을 말(두뇌 재료 — 한 가지만 묻는다).
ASK_ORDER: dict[str, str] = {
    "product": "어떤 가구(제품 · 문 방식)를 원하시는지",
    "width": "설치하실 벽의 가로 길이(mm)",
    "height": "천장 높이(mm)",
    "door": "문 방식(여닫이 · 슬라이딩)",
}
_RULE_LINE = re.compile(r"^\s*검사\s*:\s*(.*)$")
_RULE_KEYS = frozenset({"product", "min_width", "max_width", "max_height", "door"})


class RuleUnreadable(ValueError):
    """제작 조건 ``검사:`` 줄을 못 읽었다(항목 id 만 싣는다) — 확인 못 한 견적은 사람에게."""


@dataclass(frozen=True)
class BuildRule:
    """제작 조건 하나(코드가 보는 칸). ``products`` 가 비면 모든 제품. 0 = 그 칸은 보지 않음."""

    item_id: str
    products: frozenset[str] = frozenset()
    min_width: int = 0
    max_width: int = 0
    max_height: int = 0
    doors: frozenset[str] = frozenset()

    def applies(self, product_id: Any) -> bool:
        """이 제품에 걸리는 규칙인가."""
        return not self.products or str(product_id) in self.products


@dataclass(frozen=True)
class QuoteOutcome:
    """계산 결과. ``lines`` = 두뇌 계산 결과 줄, ``allowed`` = 허용 목록에 더할 글, ``note`` = 직원 참고 줄(코드가 쓴 것)."""

    status: str
    lines: tuple[str, ...] = ()
    allowed: tuple[str, ...] = ()
    note: str = ""
    code: Optional[str] = None  # human · ask 의 까닭 코드(ask 는 물을 칸 이름)


# ── 제작 조건 ────────────────────────────────────────────────────────────
def _rule(item_id: str, body: str) -> BuildRule:
    """``검사:`` 줄 하나 → 규칙. 모르는 칸 · 틀린 값이면 :class:`RuleUnreadable`."""
    values: dict[str, str] = {}
    for part in body.split():
        key, sep, value = part.partition("=")
        if not sep or key not in _RULE_KEYS or not value or key in values:
            raise RuleUnreadable(item_id)
        values[key] = value
    numbers = {}
    for key in ("min_width", "max_width", "max_height"):
        raw = values.get(key, "0")
        if not raw.isdigit():
            raise RuleUnreadable(item_id)
        numbers[key] = int(raw)
    doors = frozenset(values["door"].split(",")) if "door" in values else frozenset()
    products = frozenset(values["product"].split(",")) if "product" in values else frozenset()
    if not values or not doors <= (set(DOORS) - {"unknown"}) or "" in products:
        raise RuleUnreadable(item_id)
    return BuildRule(item_id, products, doors=doors, **numbers)


def build_rules(items: Iterable[Any]) -> tuple[BuildRule, ...]:
    """지식 항목(``kind``, ``item_id``, ``text``)에서 제작 조건 규칙 — ``build_rule`` 항목의 ``검사:`` 줄만.

    Raises:
        RuleUnreadable: 읽지 못한 ``검사:`` 줄이 있다.
    """
    rules = []
    for item in items:
        if getattr(item, "kind", None) != KIND_BUILD_RULE:
            continue
        for line in str(getattr(item, "text", "")).splitlines():
            found = _RULE_LINE.match(line)
            if found:
                rules.append(_rule(item.item_id, found.group(1)))
    return tuple(rules)


def _rule_gaps(space: QuoteSpace, rules: Sequence[BuildRule]) -> list[str]:
    """규칙이 보는데 모르는 칸(높이 · 문 방식)."""
    gaps = []
    for rule in rules:
        if not any(rule.applies(pid) for pid in space.product_ids):
            continue
        if rule.max_height and not space.height_mm:
            gaps.append("height")
        if rule.doors and space.door == "unknown":
            gaps.append("door")
    return gaps


def _breaks(space: QuoteSpace, rules: Sequence[BuildRule]) -> bool:
    """제작 조건에 안 맞는 후보가 하나라도 있나(가로 범위면 두 끝 모두 본다)."""
    widths = [w for w in (space.width_mm, space.width_max_mm) if w]
    for rule in rules:
        for pid in space.product_ids:
            if not rule.applies(pid):
                continue
            if rule.min_width and any(w < rule.min_width for w in widths):
                return True
            if rule.max_width and any(w > rule.max_width for w in widths):
                return True
            if rule.max_height and space.height_mm > rule.max_height:
                return True
            if rule.doors and space.door not in rule.doors:
                return True
    return False


# ── 계산 ─────────────────────────────────────────────────────────────────
def _missing(ask: QuoteAsk, rules: Sequence[BuildRule]) -> Optional[str]:
    """모르는 칸 하나(:data:`ASK_ORDER` 차례) — 다 알면 ``None``."""
    gaps: set[str] = set()
    if not ask.spaces:
        gaps.add("product")
    for space in ask.spaces:
        if not space.product_ids or "product" in ask.unknown:
            gaps.add("product")
        if not space.width_mm or "width" in ask.unknown:
            gaps.add("width")
        gaps.update(_rule_gaps(space, rules))
    return next((name for name in ASK_ORDER if name in gaps), None)


def _price(product: dict[str, Any], width: int, rows: Sequence[dict[str, Any]], products: Sequence[Any]) -> int:
    """한 후보 · 한 가로의 계산기 값(원). 0 이하 · 수가 아님 · 구성품 값 0 이면 :class:`ValueError` ``zero``."""
    math_ = compute_estimate([{"mode": "select", "productId": product.get("id"), "widthMm": width,
                               "additionalFees": []}], products, rows)
    if not math.isfinite(math_.total_price_collect) or math_.base_price_collect <= 0 or math_.components != 1:
        raise ValueError("zero")
    if any(js <= 0 for js in (won(math_.base_price_collect), won(math_.total_price_collect))):
        raise ValueError("zero")
    return won(math_.total_price_collect)


def _space_lines(number: int, space: QuoteSpace, catalog: Catalog) -> tuple[list[str], list[int]]:
    """공간 하나의 계산기 줄 · 값들(후보 × 가로 끝). 모르는 가격 방식이면 ``KeyError`` ``pricing_type``."""
    rows = option_rows(space.options, catalog.option_categories)
    for row in rows:
        if not (isinstance(row.get("price"), (int, float)) and not isinstance(row.get("price"), bool)
                and row["price"] > 0):
            raise ValueError("zero")  # 화면은 0원 옵션 줄을 빼고 계산한다 — 손님이 말한 옵션이 빠진 값은 쓰지 않는다
    label = space.space if space.space != "기타" else f"공간 {number}"
    extra = [f"높이 {space.height_mm:,}mm"] if space.height_mm else []
    extra += [f"{DOORS[space.door]}"] if space.door != "unknown" else []
    extra += [f"손잡이 {HANDLES[space.handle]}"] if space.handle not in ("unknown", "other") else []
    extra += [f"옵션 {row['name']} × {qty}" for row, (_, qty) in zip(rows, space.options)]
    lines, values = [], []
    for pid in space.product_ids:
        product = find_product(catalog.products, pid)
        if product is None:
            raise ValueError("failed")
        if product.get("pricing_type") not in PRICING_TYPES:
            raise KeyError("pricing_type")
        for width in [w for w in (space.width_mm, space.width_max_mm) if w]:
            amount = _price(product, width, rows, catalog.products)
            name = " ".join(str(product.get("name") or "").split())
            lines.append(" · ".join([label, name, f"가로 {width:,}mm", *extra]) + f" = {amount:,}원")
            values.append(amount)
    return lines, values


def _priced(ask: QuoteAsk, catalog: Catalog) -> QuoteOutcome | tuple[list[str], int]:
    """모든 공간의 줄 + 합(후보 · 범위가 하나뿐일 때만, 아니면 0). 안 되면 사람에게 결과."""
    lines: list[str] = []
    single, total = True, 0
    for number, space in enumerate(ask.spaces, start=1):
        try:
            space_lines, values = _space_lines(number, space, catalog)
        except KeyError as exc:
            code = HUMAN_PRICING_TYPE if exc.args == ("pricing_type",) else HUMAN_FAILED
            return QuoteOutcome(STATUS_HUMAN, code=code)
        except ValueError as exc:
            return QuoteOutcome(STATUS_HUMAN, code=HUMAN_ZERO if exc.args == ("zero",) else HUMAN_FAILED)
        lines += space_lines
        single = single and len(values) == 1
        total += values[0]
    return lines, (total if single and len(ask.spaces) > 1 else 0)


def evaluate(ask: QuoteAsk, catalog: Catalog, rules: Sequence[BuildRule], *,
             now_utc: datetime.datetime) -> QuoteOutcome:
    """뽑은 재료 → 계산 결과(모듈 설명). ``now_utc`` 는 UTC naive(확인 날과 견준다)."""
    if ask.brand == BRAND_HAUD:
        return QuoteOutcome(STATUS_HUMAN, code=HUMAN_BRAND)
    missing = _missing(ask, rules)
    if missing is not None:
        line = (f"견적 계산 전 — 모르는 칸: {ASK_ORDER[missing]}. 손님께 이 한 가지만 묻는다(다른 것은 묻지 않는다). "
                "금액은 쓰지 않는다.")
        return QuoteOutcome(STATUS_ASK, lines=(line,), note=f"[견적 계산] 모르는 칸 — {ASK_ORDER[missing]}", code=missing)
    if any(_breaks(space, rules) for space in ask.spaces):
        return QuoteOutcome(STATUS_HUMAN, code=HUMAN_RULE)
    priced = _priced(ask, catalog)
    if isinstance(priced, QuoteOutcome):
        return priced
    values, total = priced
    if total:
        values.append(f"합계(공간 {len(ask.spaces)}곳) {total:,}원")
    day = f"{catalog.saved_at:%Y-%m-%d}" if catalog.saved_at else "없음"
    if catalog.needs_check(now_utc):
        head = (f"계산기 금액 '확인 필요' — 계산기 제품 설정 확인 날({day}) 뒤 {FRESH_DAYS}일이 지났거나 확인 날이 없다. "
                "금액은 손님 글에 쓰지 않고 직원 참고 칸에만 적는다:")
        return QuoteOutcome(STATUS_CHECK, lines=(head, *values),
                            note=f"[견적 계산 · 확인 필요 — 확인 날 {day}] " + " / ".join(values))
    head = (f"라홈 견적 계산기 값(직원 계산기 화면과 같은 계산 · 쿠폰 · 운임 빼고 · 실측 전 값, 계산기 설정 확인 날 {day}) — "
            "금액은 이 줄의 값만 쓴다:")
    return QuoteOutcome(STATUS_OK, lines=(head, *values), allowed=tuple(values),
                        note=f"[견적 계산 — 확인 날 {day}] " + " / ".join(values))
