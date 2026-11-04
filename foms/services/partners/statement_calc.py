"""협력사 거래명세서 금액 계산 — 순수 함수 하나(설계서 docs/specs/2026-11-03-partner-statement_SPEC.md §4).

입력은 단가표 판(``sheet`` · ``rules``)과 품목 하나(제품명으로 고른 단가표 줄 · 규격 줄 · 옵션 칸에서 고른 줄 ·
커스텀 글)다. DB · 화면 · 모델(AI)을 모른다. 금액 계산은 여기 하나뿐이고 화면 JS 는 서버 값을 보여만 준다.

- 자 단가(``ja``): 수량 = 가로 ÷ 300 을 소수 둘째 자리에서 반올림(0.5 는 위로 — 12.33 → 12.3 · 12.35 → 12.4).
- m 단가(``meter``): 가로 ÷ 1000, 같은 반올림(자리는 ``rules``).
- 크기 구간(``band``): 같은 묶음(``cond.group``) 줄 가운데 가로(또는 깊이)가 드는 줄. 가장 큰 구간을 넘으면
  그 줄 + 넘친 만큼(``over``) 줄 — (치수 − 구간 최대) ÷ 100 올림.
- 개수(``count``) · 정해진 값(``fixed``): 수 × 단가.
- 기본 포함: 단가가 빈칸 · 0 인 줄은 명세서 줄을 만들지 않고 기본 줄 비고에 이름만(값으로만 판정).
- 원 단위: 줄 금액 = 반올림(수량 × 단가). 공급가액 = 반올림(합계 ÷ 1.1), 세액 = 합계 − 공급가액(단가는 VAT 포함).
- 커스텀: 금액 빈 줄로 들어간다(CS 가 넣는다). 빈 금액 · 못 찾은 줄은 ``needs`` 에 적어 발행을 막는 근거가 된다.
"""
from __future__ import annotations

import math
import re
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Optional

from foms.services.partners.price_list import DEFAULT_RULES, iter_items, item_name, item_price

_UNDECIDED = {"", "상담", "모르면 상담", "사진참조", "사진 참조"}


def round_half_up(value: Decimal, places: int = 0) -> Decimal:
    return value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def parse_mm(text: Any) -> Optional[int]:
    """규격 칸 → mm. ``5700(2402+1864+1434)`` 는 괄호 앞 값, ``2400+1200`` 은 합. 숫자가 없으면 None."""
    raw = re.sub(r"\(.*?\)", "", str(text if text is not None else "")).replace(",", "")
    parts = [p for p in re.split(r"\s*\+\s*", raw.strip()) if p]
    total = 0
    for part in parts:
        match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(?:mm)?\s*", part)
        if not match:
            return None
        total += int(round(float(match.group(1))))
    return total if parts and total > 0 else None


def index_sheet(sheet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """열쇠 → 줄 정보(이름 · 단가 · 계산 방법 …). 지운 줄(``retired``)도 넣어 옛 선택이 끊기지 않게 한다."""
    out: dict[str, dict[str, Any]] = {}
    for _cat, row, item in iter_items(sheet):
        out[item["key"]] = {**item, "name": item_name(row, item), "price": item_price(row, item)}
    for old in sheet.get("retired") or []:
        out.setdefault(old["key"], {**old, "retired": True})
    return out


def _band_pick(index: dict[str, dict[str, Any]], info: dict[str, Any], value: Optional[int]):
    """구간 줄 고르기 → ``(줄, 넘친 mm)``. 치수가 없으면 고른 줄 그대로."""
    cond = info.get("cond") or {}
    group = cond.get("group")
    rows = [i for i in index.values() if i.get("kind") == "band" and (i.get("cond") or {}).get("group") == group
            and (i.get("cond") or {}).get("dim") == cond.get("dim") and not i.get("retired")] if group else [info]
    if value is None or not rows:
        return info, 0
    for row in sorted(rows, key=lambda r: (r["cond"].get("max") is None, r["cond"].get("max") or 0)):
        low, high = row["cond"].get("min", 0), row["cond"].get("max")
        if value >= low and (high is None or value <= high):
            return row, 0
    top = max((r for r in rows if r["cond"].get("max") is not None), key=lambda r: r["cond"]["max"], default=info)
    return top, max(0, value - int(top["cond"].get("max") or value))


def _line(info: dict[str, Any], qty: Decimal, *, spec: str = "", basis: str = "", unit: str = "",
          name: str = "") -> dict[str, Any]:
    price = info.get("price")
    amount = int(round_half_up(qty * price)) if price is not None else None
    return {"key": info["key"], "name": name or info["name"], "spec": spec, "unit": unit or info.get("unit") or "개",
            "qty": format(qty, "f"),
            "unit_price": price, "amount": amount, "source": "auto", "basis": basis}


def _spec_text(row: dict[str, Any]) -> str:
    return "*".join(str(row.get(k) or "").strip() for k in ("width", "depth", "height") if str(row.get(k) or "").strip())


def _base_lines(index, info, item, rules, needs):
    kind = info.get("kind")
    # 자 · m · 정해진 값 줄은 협력사가 고른 제품 이름으로 적는다(단가표 줄 이름은 "여닫이 / 몰딩, 무몰딩"처럼 여럿을 묶는다).
    title = str(item.get("title") or "").strip()
    rows = item.get("spec_rows") or [{}]
    lines: list[dict[str, Any]] = []
    for row in rows:
        width, depth = parse_mm(row.get("width")), parse_mm(row.get("depth"))
        spec = _spec_text(row)
        if kind in ("ja", "meter"):
            if width is None:
                needs.append(f"{item.get('title') or info['name']}: 가로 치수가 없습니다")
                continue
            per, places = (300, int(rules.get("ja_decimals", 1))) if kind == "ja" else (1000, int(rules.get("meter_decimals", 1)))
            exact = Decimal(width) / Decimal(per)
            qty = round_half_up(exact, places)
            basis = f"가로 {width:,} ÷ {per:,} = {round_half_up(exact, places + 1)} → {qty}"
            lines.append(_line(info, qty, spec=spec, basis=basis, unit="자" if kind == "ja" else "m", name=title))
        elif kind == "band":
            by_depth = (info.get("cond") or {}).get("dim") == "depth"
            dim = depth if by_depth else width
            chosen, over_mm = _band_pick(index, info, dim)
            label = "깊이" if by_depth else "가로"
            basis = f"{label} {dim:,}mm에 맞는 구간" if dim is not None else f"{label} 치수가 없어 고른 줄 그대로"
            lines.append(_line(chosen, Decimal(1), spec=spec, basis=basis))
            if over_mm:
                lines.extend(_over_line(index, chosen, over_mm, needs))
        else:
            lines.append(_line(info, Decimal(max(1, int(item.get("quantity") or 1))), spec=spec, name=title))
    return lines


def _over_line(index, band_info, over_mm, needs):
    over = index.get((band_info.get("cond") or {}).get("over_key") or "")
    if not over:
        needs.append(f"{band_info['name']}: 가장 큰 구간보다 {over_mm}mm 큽니다. 단가표에서 이 줄의 '넘치면 이 줄'을 정해 주세요")
        return []
    per = int((over.get("cond") or {}).get("per") or 100)
    count = math.ceil(over_mm / per)
    return [_line(over, Decimal(count), basis=f"넘친 {over_mm}mm ÷ {per} 올림 = {count}")]


def _option_lines(index, item, notes, needs):
    rows = item.get("spec_rows") or [{}]
    width = parse_mm(rows[0].get("width"))
    depth = parse_mm(rows[0].get("depth"))
    lines = []
    for picked in item.get("lines") or []:
        info = index.get(str(picked.get("key") or ""))
        if info is None:
            needs.append(f"단가표에 없는 옵션이 있습니다: {picked.get('name') or picked.get('key')}")
            continue
        try:
            qty = Decimal(str(picked.get("qty") or 1))
        except ArithmeticError:
            qty = Decimal(1)
        qty = qty if qty > 0 else Decimal(1)
        if info.get("kind") == "band":
            dim = depth if (info.get("cond") or {}).get("dim") == "depth" else width
            info, _over = _band_pick(index, info, dim)
        if not info.get("price"):
            notes.append(f"{info.get('partner_label') or info['name']} 포함")
            continue
        lines.append(_line(info, qty, spec=str(picked.get("memo") or "").strip()[:60], basis="고른 옵션"))
    return lines


def calc_item(sheet: dict[str, Any], item: dict[str, Any], rules: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """품목 하나 → 명세서 묶음 ``{item_uid, title, lines, notes, needs, subtotal}``."""
    rules = {**DEFAULT_RULES, **(rules or {})}
    index = index_sheet(sheet)
    notes: list[str] = []
    needs: list[str] = []
    lines: list[dict[str, Any]] = []
    base = index.get(str(item.get("base_key") or ""))
    title = re.sub(r"\s+", " ", str(item.get("title") or "")).strip()[:100]
    if base is None and title:
        # 목록에 없는 제품(커스텀 제품 — 설계서 2026-11-04-partner-product-tree §2.3): 금액 빈 줄, CS 가 초안에서 넣는다.
        notes.append("목록에 없는 제품")
        lines.append({"key": None, "name": title, "spec": _spec_text((item.get("spec_rows") or [{}])[0]), "unit": "식",
                      "qty": "1", "unit_price": None, "amount": None, "source": "custom",
                      "basis": "목록에 없는 제품 — 금액을 넣어 주세요"})
    elif base is None:
        needs.append("품목: 제품명이 단가표 줄과 이어져 있지 않습니다")
    elif base.get("price") is None:
        needs.append(f"{base['name']}: 단가표 금액이 빈칸입니다")
    else:
        lines.extend(_base_lines(index, base, item, rules, needs))
    internal = re.sub(r"\s+", " ", str(item.get("internal") or "")).strip()
    if internal and internal not in _UNDECIDED:
        notes.insert(0, f"내부 {internal} 포함")
    lines.extend(_option_lines(index, item, notes, needs))
    for custom in item.get("customs") or []:
        text = str((custom or {}).get("text") or "").strip()[:200]
        if text:
            lines.append({"key": None, "name": text, "spec": "", "unit": "식", "qty": "1", "unit_price": None,
                          "amount": None, "source": "custom", "basis": "커스텀 — 금액을 넣어 주세요"})
    if lines and notes:
        lines[0]["note"] = " · ".join(notes)
    return {"item_uid": item.get("uid"), "title": item.get("title") or (base or {}).get("name") or "",
            "lines": lines, "notes": notes, "needs": needs,
            "subtotal": sum(line["amount"] for line in lines if line["amount"] is not None)}


def summarize(groups: list[dict[str, Any]]) -> dict[str, Any]:
    """묶음 목록 → 합계 · 공급가액 · 세액. 금액이 빈 줄이 있으면 ``complete=False``."""
    amounts = [line.get("amount") for group in groups for line in group.get("lines") or []]  # 커스텀은 금액이 빌 수 있다
    total = sum(a for a in amounts if a is not None)
    supply = int(round_half_up(Decimal(total) / Decimal("1.1")))
    return {"total": total, "supply": supply, "vat": total - supply,
            "complete": all(a is not None for a in amounts) and not any(g.get("needs") for g in groups)}
