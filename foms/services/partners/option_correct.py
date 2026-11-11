"""협력사 명세서 — 확정한 옵션 고치기(설계서 docs/specs/2026-11-11-partner-confirmed-option-fix_SPEC.md).

협력사가 옵션을 틀리게 고르고 도면을 확정하면 그 값이 확정본(``order_item_options`` CONFIRMED)으로 굳고, 명세서는 확정본으로만
센다. 우리 CS 가 명세서 초안(수정본 초안 포함)에서 품목 옵션을 고치면:

* 그 품목의 ``CURRENT`` · ``CONFIRMED`` 를 같은 값으로 바꾼다. ``PARTNER``(협력사가 처음 고른 원문)는 그대로 — "처음 → 지금"이 남는다.
* 확정본과 달라진 품목은 이유가 꼭 있어야 한다. ``changes`` 는 원문 대비 차이를 새로 내되, 이번에 안 바뀐 줄은 앞서 적힌 이유를
  그대로 두고 이번에 바뀐 줄에만 새 이유를 붙인다(협력사 화면 · 명세서 근거 칸에 보인다).
* 품목 JSON ``option_detail`` 요약도 새 값으로, 같은 트랜잭션에서 명세서 초안을 다시 센다(수정본은 발행본과 같은 판 · 일자).
* 제품(``base_key``)은 바꾸지 않는다. "상담 후 정함"은 고를 수 없다(이미 확정됨). 커밋은 부르는 쪽.
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Optional

from sqlalchemy.orm.attributes import flag_modified

from foms.services.datetime_kst import now_utc_naive
from foms.services.orders.drawing_confirm_partial import is_item_cancelled
from foms.services.orders.revision import lock_order_row
from foms.services.partners.item_options import (
    ItemOptionsError,
    _text,
    _units,
    _view,
    clean_item_options,
    diff_options,
    options_summary,
    pick_lists,
)
from foms.services.partners.statements import StatementError, locked_draft, refresh_draft
from models import OrderItemOption, PartnerPriceList, PartnerStatement


def _sheet(db, stmt: PartnerStatement) -> dict[str, Any]:
    price_list = db.get(PartnerPriceList, stmt.price_list_id) if stmt.price_list_id else None
    if price_list is None:
        raise StatementError("이 명세서의 단가표를 찾지 못했습니다. 다시 계산한 뒤 고쳐 주세요.", 409)
    return price_list.sheet


def _rows(db, order_id: int) -> dict[tuple[str, str], OrderItemOption]:
    rows = db.query(OrderItemOption).filter(OrderItemOption.order_id == order_id).all()
    return {(r.item_uid, r.stage): r for r in rows}


def _items(order: Any) -> dict[str, tuple[int, dict[str, Any]]]:
    return {str(it.get("uid") or ""): (no, it) for no, it in
            enumerate((order.structured_data or {}).get("items") or [], start=1)
            if isinstance(it, dict) and not is_item_cancelled(it)}


def correction_view(db, stmt: PartnerStatement, order: Any) -> dict[str, Any]:
    """고치기 창 — 명세서 품목마다 확정 옵션 · 협력사 원문 · 바뀐 줄(이유 포함) · 고를 목록(이름 · 단위만)."""
    sheet = _sheet(db, stmt)
    units = _units(sheet)
    rows = _rows(db, order.id)
    items = []
    for uid, (no, item) in _items(order).items():
        confirmed = _view(rows.get((uid, "CONFIRMED")), units)
        if confirmed is None:
            continue
        items.append({"uid": uid, "no": no, "title": str(item.get("product_name") or ""), "current": confirmed,
                      "partner": _view(rows.get((uid, "PARTNER")), units)})
    return {"statement_id": stmt.id, "version": stmt.version, "editable": stmt.status == "DRAFT",
            "catalog": pick_lists(sheet)["options"], "items": items}


def _changes(partner: Optional[dict[str, Any]], before: dict[str, Any], options: dict[str, Any],
             units: dict[str, str], reason: str) -> list[dict[str, Any]]:
    """원문 대비 차이 — 이번에 안 바뀐 줄은 앞선 이유, 바뀐 줄은 새 이유. 원문이 없으면 확정본 대비 차이."""
    now = diff_options(partner, options, units) if partner is not None else diff_options(before, options, units)
    touched = {(d["name"], d["to"]) for d in diff_options(before, options, units)}
    old = {(c.get("name"), c.get("from"), c.get("to")): c.get("reason") for c in before.get("changes") or []}
    out = []
    for d in now:
        keep = old.get((d["name"], d["from"], d["to"]))
        out.append({**d, "reason": reason if (d["name"], d["to"]) in touched or not keep else keep})
    return out


def _memos(options: dict[str, Any]) -> list[tuple[str, str]]:
    return sorted((str(line.get("name") or ""), str(line.get("memo") or "")) for line in options.get("lines") or [])


def _fingerprint(rows: list[OrderItemOption]) -> str:
    snap = [{"uid": r.item_uid, "state": r.state, "lines": r.lines or [], "customs": r.customs or []} for r in rows]
    return hashlib.sha256(json.dumps(snap, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def correct_options(db, statement_id: int, raw: Any, base_version: Any, user_id: Optional[int]):
    """옵션 고치기 저장 → ``(명세서, 감사 기록 detail)``. ``raw`` = ``{품목 uid: {state, lines, customs, reason}}``."""
    head = db.get(PartnerStatement, statement_id)
    if head is None:
        raise StatementError("명세서를 찾을 수 없습니다.", 404)
    order = lock_order_row(db, head.order_id)
    if order is None or not order.partner_org_id:
        raise StatementError("협력사 주문을 찾을 수 없습니다.", 404)
    stmt = locked_draft(db, statement_id, base_version)
    if not isinstance(raw, dict) or not raw:
        raise StatementError("고칠 옵션이 없습니다.")
    sheet = _sheet(db, stmt)
    units = _units(sheet)
    rows = _rows(db, order.id)
    items = _items(order)
    planned = []
    for uid, entry in raw.items():
        uid = str(uid)
        no, item = items.get(uid, (None, None))
        confirmed = rows.get((uid, "CONFIRMED"))
        if no is None or confirmed is None:
            raise StatementError("옵션을 고칠 품목을 찾지 못했습니다. 화면을 새로 고친 뒤 다시 해 주세요.", 409)
        try:
            options = clean_item_options(entry, str(item.get("product_name") or ""), sheet, no=no)
        except ItemOptionsError as exc:
            raise StatementError(str(exc)) from exc
        if options["state"] == "later":
            raise StatementError(f"항목 {no}: 도면이 이미 확정된 주문이라 \"상담 후 정함\"은 고를 수 없습니다.")
        before = _view(confirmed, units)
        diff = diff_options(before, options, units)
        if not diff:
            if _memos(before) != _memos(options):  # 위치 글만 바뀜 — 금액 · 협력사 차이는 그대로라 이유 없이 둔다
                planned.append((uid, no, confirmed, options, list(confirmed.changes or []), "", []))
            continue
        reason = _text((entry or {}).get("reason") if isinstance(entry, dict) else "", 200)
        if not reason:
            raise StatementError(f"항목 {no}: 옵션을 바꾼 이유를 한 줄 적어 주세요. 협력사에게 보입니다.")
        changes = _changes(_view(rows.get((uid, "PARTNER")), units), before, options, units, reason)
        planned.append((uid, no, confirmed, options, changes, reason, diff))
    if not planned:
        raise StatementError("바뀐 옵션이 없습니다.")
    before_fp = _fingerprint([rows[(uid, "CONFIRMED")] for uid, *_ in planned])
    now = now_utc_naive()
    sd = copy.deepcopy(order.structured_data or {})
    for uid, _no, confirmed, options, changes, _reason, _diff in planned:
        current = rows.get((uid, "CURRENT")) or OrderItemOption(order_id=order.id, item_uid=uid, stage="CURRENT",
                                                                 base_key=confirmed.base_key,
                                                                 price_list_id=confirmed.price_list_id)
        for row in (current, confirmed):
            row.state, row.lines, row.customs = options["state"], list(options["lines"]), list(options["customs"])
            row.changes, row.updated_by, row.updated_at = list(changes), user_id, now
            db.add(row)
        for it in sd.get("items") or []:
            if isinstance(it, dict) and str(it.get("uid") or "") == uid:
                it["option_detail"] = options_summary(options, sheet)
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db.flush()
    refresh_draft(db, order, stmt)
    detail = {"items": [{"uid": uid, "no": no, "reason": reason, "diff": diff}
                        for uid, no, _c, _o, _ch, reason, diff in planned],
              "before": before_fp, "after": _fingerprint([confirmed for _u, _n, confirmed, *_ in planned])}
    return stmt, detail
