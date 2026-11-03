"""협력사 품목 옵션 고르기(설계서 docs/specs/2026-11-03-partner-statement_SPEC.md §3.2 · §5.2 — 2단계).

협력사에 지금 쓰는 단가표 판(ACTIVE)이 있을 때만 켜진다. 그때 협력사 새 주문 · 품목 고치기의 제품 속성 "옵션" 칸은
단가표 옵션 이름에서 고르는 칸이 되고(금액 없음), 품목마다 고른 것을 ``order_item_options`` 에 둔다:

* ``PARTNER`` — 협력사가 마지막으로 보낸 원문. ``CURRENT`` — 지금 값(3단계에서 도면팀이 고친다).
  협력사가 고칠 수 있는 때(첫 도면 전)에는 둘을 같이 쓴다. ``CONFIRMED`` 는 3단계(도면 확인) 몫이다.
* ``state`` — ``chosen``(고른 줄 · 커스텀이 있음) · ``none``("옵션 없음") · ``later``("상담 후 정함").
* 줄 ``{key, name, qty, memo}`` — ``key`` 는 단가표 줄 열쇠, ``name`` 은 협력사가 고른 이름, ``memo`` 는 위치(선택).
* 품목 JSON 의 ``option_detail`` 글에는 요약을 적는다(우리 직원 · 도면팀 화면이 지금처럼 글로 본다). 고른 값의 정본은 표다 —
  우리 주문 화면 저장이 품목 JSON 을 통째로 다시 써도 표는 그대로다(설계서 1장 6번).

협력사에게 싣는 목록(:func:`pick_lists`)에는 이름 · 단위만 있다. 금액은 명세서가 나온 뒤에만 보인다(결정 4).
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from foms.services.datetime_kst import now_utc_naive
from foms.services.partners.price_list import active_price_list, item_name, iter_items
from models import OrderItemOption

STATES = ("chosen", "none", "later")
STATE_TEXT = {"none": "옵션 없음", "later": "상담 후 정함"}
STAGES = ("PARTNER", "CURRENT", "CONFIRMED")
MAX_LINES = 30
MAX_CUSTOMS = 10
MAX_QTY = Decimal(999)
_SUMMARY_LIMIT = 500


class ItemOptionsError(ValueError):
    """화면에 그대로 보일 옵션 오류(품목 번호 포함)."""


def _label(row: dict[str, Any], item: dict[str, Any]) -> str:
    return item.get("partner_label") or item_name(row, item)


def _names(row: dict[str, Any], item: dict[str, Any]) -> list[str]:
    return list(item.get("pick_names") or []) or [_label(row, item)]


def pick_lists(sheet: dict[str, Any]) -> dict[str, Any]:
    """협력사 화면에 싣는 목록 — 이름 · 단위 · '이 제품일 때만'만(금액 없음).

    제품: 고르는 이름이 여럿인 줄(몰딩 여닫이 · 무몰딩 여닫이)은 그 줄 이름으로 묶고, 하나뿐인 줄은 표 제목으로 묶는다.
    옵션: 표 제목으로 묶는다. 같은 이름(같은 구간 묶음의 EP 줄 등)은 한 번만 싣는다.
    """
    products: list[dict[str, Any]] = []
    options: list[dict[str, Any]] = []
    seen_products: set[str] = set()
    seen_options: set[str] = set()
    for category in sheet.get("categories") or []:
        singles: list[str] = []
        opt_items: list[dict[str, Any]] = []
        for row in category.get("rows") or []:
            for item in row.get("items") or []:
                if item.get("pickable") is False:
                    continue
                names = [n for n in _names(row, item) if n]
                if item.get("role") == "product":
                    fresh = [n for n in names if n not in seen_products]
                    seen_products.update(fresh)
                    if len(names) > 1 and fresh:
                        products.append({"label": _label(row, item), "items": fresh})
                    else:
                        singles.extend(fresh)
                    continue
                for name in names:
                    if name in seen_options:
                        continue
                    seen_options.add(name)
                    opt_items.append({"key": item["key"], "name": name, "unit": item.get("unit") or "개",
                                      "only": list(item.get("for_products") or [])})
        if singles:
            products.append({"label": category.get("title") or "제품", "items": singles})
        if opt_items:
            options.append({"label": category.get("title") or "옵션", "items": opt_items})
    return {"products": products, "options": options}


def _index(sheet: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """옵션 열쇠 → ``{names, unit, only, label}`` · 제품 고르는 이름 → 제품 줄 열쇠."""
    options: dict[str, dict[str, Any]] = {}
    products: dict[str, str] = {}
    for _cat, row, item in iter_items(sheet):
        if item.get("pickable") is False:
            continue
        if item.get("role") == "product":
            for name in _names(row, item):
                products.setdefault(name, item["key"])
        else:
            options[item["key"]] = {"names": _names(row, item), "unit": item.get("unit") or "개",
                                    "only": list(item.get("for_products") or []), "label": _label(row, item)}
    return options, products


def _qty(value: Any, unit: str, where: str) -> str:
    try:
        qty = Decimal(str(value if value not in (None, "") else 1))
    except (InvalidOperation, ValueError) as exc:
        raise ItemOptionsError(f"{where}: 수량은 숫자로 넣어 주세요.") from exc
    if qty <= 0 or qty > MAX_QTY:
        raise ItemOptionsError(f"{where}: 수량은 1 이상 999 이하로 넣어 주세요.")
    if unit != "m" and qty != qty.to_integral():
        raise ItemOptionsError(f"{where}: 수량은 정수로 넣어 주세요(m 만 소수).")
    return format(qty.normalize(), "f")


def _text(value: Any, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value if value is not None else "")).strip()[:limit]


def clean_item_options(raw: Any, product_name: str, sheet: dict[str, Any], *, no: int) -> dict[str, Any]:
    """품목 하나의 옵션 칸 → 저장할 모양. 비었으면(고른 것 없음) 오류 — 꼭 넣을 칸이다(설계서 §5.2)."""
    where = f"항목 {no}"
    raw = raw if isinstance(raw, dict) else {}
    state = raw.get("state") if raw.get("state") in STATES else None
    options, products = _index(sheet)
    lines: list[dict[str, Any]] = []
    for picked in (raw.get("lines") or [])[:MAX_LINES]:
        picked = picked if isinstance(picked, dict) else {}
        info = options.get(str(picked.get("key") or ""))
        if info is None:
            raise ItemOptionsError(f"{where}: 단가표에 없는 옵션이 있습니다. 옵션을 다시 골라 주세요.")
        name = _text(picked.get("name"), 60)
        name = name if name in info["names"] else info["names"][0]
        if info["only"] and product_name not in info["only"]:
            raise ItemOptionsError(f"{where}: '{name}' 은(는) {' · '.join(info['only'])} 에만 고를 수 있습니다.")
        lines.append({"key": picked["key"], "name": name, "qty": _qty(picked.get("qty"), info["unit"], f"{where} {name}"),
                      "memo": _text(picked.get("memo"), 60)})
    customs = [{"text": _text(c.get("text"), 200)} for c in (raw.get("customs") or [])[:MAX_CUSTOMS]
               if isinstance(c, dict) and _text(c.get("text"), 200)]
    if state is None:
        state = "chosen" if (lines or customs) else None
    if state is None or (state == "chosen" and not (lines or customs)):
        raise ItemOptionsError(f"{where} 옵션을 골라 주세요. 없으면 \"옵션 없음\"을 고르면 됩니다.")
    if state != "chosen":
        lines, customs = [], []
    return {"state": state, "base_key": products.get(product_name), "lines": lines, "customs": customs}


def options_summary(options: dict[str, Any], sheet: dict[str, Any]) -> str:
    """품목 JSON ``option_detail`` 에 적을 요약 글(우리 직원 · 도면팀 화면용)."""
    if options["state"] != "chosen":
        return STATE_TEXT[options["state"]]
    units = {key: info["unit"] for key, info in _index(sheet)[0].items()}
    parts = []
    for line in options["lines"]:
        text = f"{line['name']} {line['qty']}{units.get(line['key'], '개')}"
        parts.append(f"{text}({line['memo']})" if line["memo"] else text)
    parts.extend(f"커스텀: {c['text']}" for c in options["customs"])
    return " · ".join(parts)[:_SUMMARY_LIMIT]


def prepare_partner_options(db, org_id: int, raw_items: list[dict[str, Any]], items: list[dict[str, Any]]):
    """저장 전 — 품목마다 옵션을 검사하고 ``option_detail`` 에 요약을 넣는다(in-place).

    협력사에 지금 판이 없으면 ``None``(옛 방식 — 옵션 칸은 글 그대로). 있으면 ``(판, 품목 순서대로 옵션 목록)``.
    ``raw_items`` 는 화면이 보낸 품목 가운데 이름이 있는 것(``items`` 와 같은 순서)이다.
    """
    price_list = active_price_list(db, org_id)
    if price_list is None:
        return None
    parsed = []
    for no, (raw, item) in enumerate(zip(raw_items, items), start=1):
        options = clean_item_options(raw.get("options"), item.get("product_name") or "", price_list.sheet, no=no)
        item["option_detail"] = options_summary(options, price_list.sheet)
        parsed.append(options)
    return price_list, parsed


def save_partner_options(db, order_id: int, items: list[dict[str, Any]], parsed: list[dict[str, Any]],
                         price_list_id: int, user_id: Optional[int]) -> None:
    """협력사 원문(PARTNER)과 지금 값(CURRENT)을 품목 uid 마다 쓴다. 이제 없는 품목의 PARTNER · CURRENT 줄은 지운다."""
    uids = [str(item.get("uid") or "") for item in items]
    if not all(uids):
        raise ItemOptionsError("품목 번호가 없어 옵션을 저장하지 못했습니다.")
    rows = {(r.item_uid, r.stage): r for r in db.query(OrderItemOption)
            .filter(OrderItemOption.order_id == order_id, OrderItemOption.stage.in_(("PARTNER", "CURRENT"))).all()}
    now = now_utc_naive()
    for uid, options in zip(uids, parsed):
        for stage in ("PARTNER", "CURRENT"):
            row = rows.pop((uid, stage), None) or OrderItemOption(order_id=order_id, item_uid=uid, stage=stage)
            row.state, row.base_key = options["state"], options["base_key"]
            row.lines, row.customs, row.changes = list(options["lines"]), list(options["customs"]), []
            row.price_list_id, row.updated_by, row.updated_at = price_list_id, user_id, now
            db.add(row)
    for row in rows.values():
        db.delete(row)
    db.flush()


def current_options(db, order_id: int) -> dict[str, dict[str, Any]]:
    """품목 uid → 지금 옵션(CURRENT) ``{state, lines, customs}`` — 품목 고치기 화면이 칸을 채운다."""
    rows = db.query(OrderItemOption).filter(OrderItemOption.order_id == order_id,
                                            OrderItemOption.stage == "CURRENT").all()
    return {r.item_uid: {"state": r.state, "lines": list(r.lines or []), "customs": list(r.customs or [])} for r in rows}
