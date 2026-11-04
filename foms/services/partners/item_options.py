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

import hashlib
import json
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
    return {"products": products, "options": options, "tree": product_tree(sheet)}


def product_tree(sheet: dict[str, Any]) -> list[dict[str, Any]]:
    """제품 3단 ``[{label: 대분류, groups: [{label: 중분류, items: [이름]}]}]`` — 금액 없음(설계서 2026-11-04-partner-product-tree §2.2).

    이름마다 ``tree_by_name`` → 줄의 ``tree`` 차례로 본다. 대분류 차례는 판의 ``tree_order``(없으면 처음 나온 차례).
    분류가 없는 제품은 맨 뒤 "기타" 밑에 지금 묶음 이름(이름이 여럿인 줄 = 줄 이름, 나머지 = 표 제목)으로 둔다.
    """
    tree: dict[str, dict[str, list[str]]] = {}
    seen: set[str] = set()
    for category in sheet.get("categories") or []:
        for row in category.get("rows") or []:
            for item in row.get("items") or []:
                if item.get("role") != "product" or item.get("pickable") is False:
                    continue
                names = [n for n in _names(row, item) if n]
                fresh = [n for n in names if n not in seen]
                if not fresh:
                    continue
                seen.update(fresh)
                etc = ("기타", _label(row, item) if len(names) > 1 else category.get("title") or "제품")
                for name in fresh:
                    path = (item.get("tree_by_name") or {}).get(name) or item.get("tree") or []
                    big, mid = (path[0], path[-1]) if path else etc
                    tree.setdefault(big, {}).setdefault(mid, []).append(name)
    rank = {big: i for i, big in enumerate(sheet.get("tree_order") or [])}
    ordered = sorted(tree.items(), key=lambda kv: (kv[0] == "기타", rank.get(kv[0], len(rank))))
    return [{"label": big, "groups": [{"label": mid, "items": items} for mid, items in mids.items()]}
            for big, mids in ordered]


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
        raise ItemOptionsError(f"{where}: 수량은 1부터 999까지 넣어 주세요.")
    if unit != "m" and qty != qty.to_integral():
        raise ItemOptionsError(f"{where}: 수량은 소수점 없이 넣어 주세요.")
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
            raise ItemOptionsError(f"{where}: 지금은 고를 수 없는 옵션이 있습니다. 옵션을 다시 골라 주세요.")
        name = _text(picked.get("name"), 60)
        name = name if name in info["names"] else info["names"][0]
        if info["only"] and product_name not in info["only"]:
            raise ItemOptionsError(f"{where}: '{name}' 옵션은 {' · '.join(info['only'])}에만 고를 수 있습니다.")
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
        raise ItemOptionsError("옵션을 저장하지 못했습니다. 화면을 새로고침한 뒤 다시 저장해 주세요.")
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



# --------------------------------------------------------------------------
# 3단계 — 도면팀 옵션 확인 · 협력사 도면 확인 때 확정(설계서 §5.3 · §5.4)
# --------------------------------------------------------------------------
def _view(row: Optional[OrderItemOption], units: dict[str, str]) -> Optional[dict[str, Any]]:
    if row is None:
        return None
    lines = [{**line, "unit": units.get(line.get("key"), "개")} for line in (row.lines or [])]
    return {"state": row.state, "lines": lines, "customs": list(row.customs or []), "changes": list(row.changes or [])}


def _qty_text(line: Optional[dict[str, Any]], units: dict[str, str]) -> Optional[str]:
    return f"{line['qty']}{units.get(line.get('key'), '개')}" if line else None


def diff_options(partner: Optional[dict[str, Any]], current: dict[str, Any], units: dict[str, str]) -> list[dict[str, Any]]:
    """협력사 원문 → 지금 값에서 달라진 것 ``[{name, from, to}]`` — 수 · 더함 · 뺌 · 커스텀 · "옵션 없음/상담" 바뀜."""
    if partner is None:
        return []
    out: list[dict[str, Any]] = []
    if partner["state"] != current["state"] and "chosen" not in (partner["state"], current["state"]):
        out.append({"name": "", "from": STATE_TEXT[partner["state"]], "to": STATE_TEXT[current["state"]]})
    before = {line["name"]: line for line in partner.get("lines") or []}
    after = {line["name"]: line for line in current.get("lines") or []}
    for name in list(before) + [n for n in after if n not in before]:
        old, new = _qty_text(before.get(name), units), _qty_text(after.get(name), units)
        if old != new:
            out.append({"name": name, "from": old, "to": new})
    old_custom = [c["text"] for c in partner.get("customs") or []]
    new_custom = [c["text"] for c in current.get("customs") or []]
    if old_custom != new_custom:
        out.append({"name": "커스텀", "from": " · ".join(old_custom) or None, "to": " · ".join(new_custom) or None})
    return out


def _option_rows(db, order_id: int) -> dict[tuple[str, str], OrderItemOption]:
    rows = db.query(OrderItemOption).filter(OrderItemOption.order_id == order_id).all()
    return {(r.item_uid, r.stage): r for r in rows}


def _sheet_for(db, order: Any, rows: dict) -> Optional[dict[str, Any]]:
    """옵션 목록 · 단위를 볼 단가표 — 지금 판, 없으면 고를 때 본 판."""
    from models import PartnerPriceList

    price_list = active_price_list(db, order.partner_org_id) if order.partner_org_id else None
    if price_list is None:
        ids = [r.price_list_id for r in rows.values() if r.price_list_id]
        price_list = db.get(PartnerPriceList, ids[0]) if ids else None
    return price_list.sheet if price_list else None


def _units(sheet: dict[str, Any]) -> dict[str, str]:
    return {key: info["unit"] for key, info in _index(sheet)[0].items()}


def option_review(db, order: Any) -> Optional[dict[str, Any]]:
    """도면팀 · 협력사 화면 — 품목마다 지금 값 · 원문과 달라진 것 · 고를 목록(이름만). 옵션 줄이 없으면 None."""
    rows = _option_rows(db, order.id)
    sheet = _sheet_for(db, order, rows) if rows else None
    if not rows or sheet is None:
        return None
    units = _units(sheet)
    items = []
    for no, item in enumerate((order.structured_data or {}).get("items") or [], start=1):
        uid = str(item.get("uid") or "") if isinstance(item, dict) else ""
        current = _view(rows.get((uid, "CURRENT")), units)
        if current is None:
            continue
        partner = _view(rows.get((uid, "PARTNER")), units)
        items.append({"uid": uid, "no": no, "title": str(item.get("product_name") or ""), "current": current,
                      "partner": partner, "diff": diff_options(partner, current, units),
                      "confirmed": rows.get((uid, "CONFIRMED")) is not None})
    return {"catalog": pick_lists(sheet)["options"], "items": items} if items else None


def prepare_review_options(db, order: Any, raw: Any):
    """도면 전달 때 도면팀이 고친 옵션 — 검사만 먼저 하고, 쓰기는 돌려준 함수가 전달 쓰기 안에서 한다(같은 트랜잭션).

    ``raw`` = ``{품목 uid: {state, lines, customs, reason}}``. 협력사 원문과 달라진 품목은 까닭이 꼭 있어야 한다.
    """
    if not getattr(order, "partner_org_id", None) or not isinstance(raw, dict) or not raw:
        return None
    rows = _option_rows(db, order.id)
    sheet = _sheet_for(db, order, rows)
    if sheet is None:
        raise ItemOptionsError("협력사 단가표가 없어 옵션을 고칠 수 없습니다.")
    units = _units(sheet)
    items = [it for it in (order.structured_data or {}).get("items") or [] if isinstance(it, dict)]
    planned = []
    for uid, entry in raw.items():
        no = next((i for i, it in enumerate(items, start=1) if str(it.get("uid") or "") == str(uid)), None)
        current = rows.get((str(uid), "CURRENT"))
        if no is None or current is None:
            raise ItemOptionsError("옵션을 고칠 품목을 찾지 못했습니다. 화면을 새로 열어 주세요.")
        options = clean_item_options(entry, str(items[no - 1].get("product_name") or ""), sheet, no=no)
        diff = diff_options(_view(rows.get((str(uid), "PARTNER")), units), options, units)
        reason = _text((entry or {}).get("reason") if isinstance(entry, dict) else "", 200)
        if diff and not reason:
            raise ItemOptionsError(f"항목 {no}: 협력사가 고른 것과 달라진 옵션은 바꾼 이유를 한 줄 적어 주세요.")
        planned.append((str(uid), current, options, [{**d, "reason": reason} for d in diff]))

    def apply(s_data: dict[str, Any], user_id: Optional[int] = None) -> None:
        now = now_utc_naive()
        for uid, current, options, changes in planned:
            current.state, current.base_key = options["state"], options["base_key"]
            current.lines, current.customs, current.changes = options["lines"], options["customs"], changes
            current.updated_by, current.updated_at = user_id, now
            db.add(current)
            for item in s_data.get("items") or []:
                if isinstance(item, dict) and str(item.get("uid") or "") == uid:
                    item["option_detail"] = options_summary(options, sheet)
        db.flush()
    return apply


def confirm_partner_options(db, order: Any, raw: Any, user_id: Optional[int],
                            s_data: Optional[dict[str, Any]] = None) -> Optional[str]:
    """협력사 "이대로 만들어 주세요" — "상담 후 정함" 품목은 여기서 고른 값을 넣고, 지금 값을 확정본(CONFIRMED)으로 복사한다.

    확정 목록의 지문(sha256)을 돌려준다(감사 기록용). 옵션 줄이 없는 주문(단가표 전 주문)은 None. 커밋은 부르는 쪽.
    """
    rows = _option_rows(db, order.id)
    currents = sorted((uid, row) for (uid, stage), row in rows.items() if stage == "CURRENT")
    if not currents:
        return None
    sheet = _sheet_for(db, order, rows)
    items = {str(it.get("uid") or ""): (no, it) for no, it in
             enumerate((order.structured_data or {}).get("items") or [], start=1) if isinstance(it, dict)}
    raw = raw if isinstance(raw, dict) else {}
    now = now_utc_naive()
    snapshot = []
    for uid, current in currents:
        no, item = items.get(uid, (0, {}))
        if current.state == "later":
            picked = raw.get(uid)
            options = clean_item_options(picked, str(item.get("product_name") or ""), sheet, no=no) \
                if picked and sheet else None
            if options is None or options["state"] == "later":
                raise ItemOptionsError(f"항목 {no} 옵션이 아직 \"상담 후 정함\"입니다. 주문 화면 도면 탭에서 옵션을 골라 주세요.")
            for other in (s_data or {}).get("items") or []:
                if isinstance(other, dict) and str(other.get("uid") or "") == uid:
                    other["option_detail"] = options_summary(options, sheet)
            for row in (current, rows.get((uid, "PARTNER"))):
                if row is not None:
                    row.state, row.base_key = options["state"], options["base_key"]
                    row.lines, row.customs = options["lines"], options["customs"]
                    row.updated_by, row.updated_at = user_id, now
                    db.add(row)
        confirmed = rows.get((uid, "CONFIRMED")) or OrderItemOption(order_id=order.id, item_uid=uid, stage="CONFIRMED")
        confirmed.state, confirmed.base_key = current.state, current.base_key
        confirmed.lines, confirmed.customs = list(current.lines or []), list(current.customs or [])
        confirmed.changes, confirmed.price_list_id = list(current.changes or []), current.price_list_id
        confirmed.updated_by, confirmed.updated_at = user_id, now
        db.add(confirmed)
        snapshot.append({"uid": uid, "state": current.state, "base_key": current.base_key,
                         "lines": current.lines or [], "customs": current.customs or []})
    db.flush()
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
