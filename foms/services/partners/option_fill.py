"""단가표 전 협력사 주문 — 우리 CS 가 옵션을 채운다(설계서 docs/specs/2026-11-03-partner-statement_SPEC.md 결정 12).

단가표가 생기기 전에 들어온 주문은 ``order_item_options`` 줄이 없어 발행 대기에 뜨지 않는다. CS 가 주문 화면의
사진 · 도면을 보고 품목마다 단가표 제품(제품명 ▾ 와 같은 이름)과 옵션을 고른다. 검사는 협력사 옵션 칸과 같은
:func:`clean_item_options` 를 쓴다.

- 생산 · 시공 · 완료 단계(협력사가 이미 도면을 확정함): 원문(PARTNER) · 지금 값(CURRENT) · 확정본(CONFIRMED)을 같이 써서
  바로 발행 대기에 뜬다.
- 그 전 단계: 원문 · 지금 값만 쓴다. 도면팀 전달 창 · 협력사 도면 확인이 예전처럼 이어 받는다(확정은 협력사가).
  아직 모르면 "상담 후 정함"(협력사가 도면 확인 때 고른다).
- 이미 옵션 줄이 있는 품목은 건드리지 않는다(협력사가 고른 값을 덮지 않는다). 품목 JSON 도 건드리지 않는다.
"""
from __future__ import annotations

from typing import Any, Optional

from foms.services.datetime_kst import now_utc_naive
from foms.services.orders.drawing_confirm_partial import is_item_cancelled
from foms.services.orders.erp_policy_constants import STAGE_NAME_TO_CODE
from foms.services.orders.revision import lock_order_row
from foms.services.partners.item_options import ItemOptionsError, clean_item_options, pick_lists
from foms.services.partners.price_list import active_price_list
from foms.services.partners.statements import ship_date
from foms.services.partners.view import build_partner_order_view
from models import Order, OrderItemOption, PartnerOrg, PartnerPriceList

# 협력사 "이대로 만들어 주세요"가 지난 단계 — 여기서는 CS 가 채운 값이 곧 확정본이다.
CONFIRMED_STAGES = ("PRODUCTION", "CONSTRUCTION", "CS", "COMPLETED")
_STAGE_TEXT = {code: name for name, code in STAGE_NAME_TO_CODE.items()}
_TEXT_KEYS = (("internal", "내부"), ("color", "색상"), ("option_detail", "옵션"), ("handle", "손잡이"), ("misc", "기타"))


def _stage(order: Order) -> str:
    return str(order.erp_stage_code or "").strip().upper()


def _items(order: Order) -> list[tuple[int, dict[str, Any]]]:
    """(번호, 품목) — 취소 품목 · 모양이 깨진 줄은 뺀다(번호는 주문 화면과 같게 전체 순서)."""
    return [(no, it) for no, it in enumerate((order.structured_data or {}).get("items") or [], start=1)
            if isinstance(it, dict) and not is_item_cancelled(it)]


def _filled(db, order_ids: list[int]) -> set[tuple[int, str]]:
    if not order_ids:
        return set()
    return {(oid, uid) for oid, uid in db.query(OrderItemOption.order_id, OrderItemOption.item_uid).filter(
        OrderItemOption.order_id.in_(order_ids), OrderItemOption.stage == "CURRENT").all()}


def fill_rows(db) -> list[dict[str, Any]]:
    """옵션 채울 주문 — 단가표가 있는 협력사의 주문 가운데 옵션 줄이 없는 품목이 남은 것(출고일 가까운 순)."""
    org_ids = [oid for (oid,) in db.query(PartnerPriceList.partner_org_id).filter(
        PartnerPriceList.status == "ACTIVE").all()]
    if not org_ids:
        return []
    orders = db.query(Order).filter(Order.active_filter(), Order.partner_org_id.in_(org_ids)).all()
    filled = _filled(db, [o.id for o in orders])
    names = {o.id: o.name for o in db.query(PartnerOrg).filter(PartnerOrg.id.in_(org_ids)).all()}
    rows = []
    for order in orders:
        items = _items(order)
        missing = [it for _no, it in items if (order.id, str(it.get("uid") or "")) not in filled]
        if not missing:
            continue
        on_date = ship_date(order)
        stage = _stage(order)
        rows.append({"order_id": order.id, "customer_name": build_partner_order_view(order)["customer_name"],
                     "org_name": names.get(order.partner_org_id, ""), "stage": _STAGE_TEXT.get(stage, stage),
                     "date": on_date.isoformat() if on_date else "", "items": len(items), "missing": len(missing),
                     "confirmed": stage in CONFIRMED_STAGES})
    rows.sort(key=lambda r: (r["date"] == "", r["date"], r["order_id"]))
    return rows


def _spec(item: dict[str, Any]) -> str:
    rows = [r for r in item.get("spec_rows") or [] if isinstance(r, dict)]
    parts = ["*".join(str(r.get(k) or "").strip() for k in ("spec_width", "spec_depth", "spec_height")
                      if str(r.get(k) or "").strip()) for r in rows]
    return " / ".join(p for p in parts if p)


def fill_view(db, order: Order) -> dict[str, Any]:
    """한 주문 채우기 화면 — 품목마다 예전 글 칸 · 고를 목록(이름만). 단가표가 없으면 오류."""
    price_list = active_price_list(db, order.partner_org_id)
    if price_list is None:
        raise ItemOptionsError("이 협력사 단가표가 없습니다. 관리 화면에서 단가표를 먼저 저장해 주세요.")
    lists = pick_lists(price_list.sheet)
    product_names = {name for group in lists["products"] for name in group["items"]}
    filled = _filled(db, [order.id])
    items = []
    for no, item in _items(order):
        uid = str(item.get("uid") or "")
        title = str(item.get("product_name") or "")
        items.append({"uid": uid, "no": no, "title": title, "spec": _spec(item),
                      "quantity": str(item.get("quantity") or ""),
                      "texts": [[label, str(item.get(key) or "").strip()] for key, label in _TEXT_KEYS
                                if str(item.get(key) or "").strip()],
                      "base": title if title in product_names else "", "filled": (order.id, uid) in filled})
    stage = _stage(order)
    return {"order_id": order.id, "customer_name": build_partner_order_view(order)["customer_name"],
            "stage": _STAGE_TEXT.get(stage, stage), "confirmed": stage in CONFIRMED_STAGES,
            "products": lists["products"], "tree": lists["tree"], "catalog": lists["options"], "items": items}


def fill_options(db, order_id: int, raw: Any, user_id: Optional[int]) -> dict[str, Any]:
    """옵션 채우기 저장(커밋은 부르는 쪽). ``raw`` = ``{품목 uid: {base, state, lines, customs}}`` — 비어 있는 품목 모두.

    ``base`` = 단가표 제품 고르는 이름(제품명 ▾ 목록). 돌려주는 값은 감사 기록용 ``{items, stages, confirmed}``.
    """
    order = lock_order_row(db, order_id)
    if order is None or not order.partner_org_id:
        raise ItemOptionsError("주문을 찾을 수 없습니다.")
    price_list = active_price_list(db, order.partner_org_id)
    if price_list is None:
        raise ItemOptionsError("이 협력사 단가표가 없습니다. 관리 화면에서 단가표를 먼저 저장해 주세요.")
    raw = raw if isinstance(raw, dict) else {}
    filled = _filled(db, [order.id])
    targets = [(no, item) for no, item in _items(order) if (order.id, str(item.get("uid") or "")) not in filled]
    if not targets:
        raise ItemOptionsError("옵션을 채울 품목이 없습니다. 그사이 다른 사람이 채웠을 수 있으니 목록을 새로 열어 주세요.")
    stray = set(map(str, raw)) - {str(item.get("uid") or "") for _no, item in targets}
    if stray:
        raise ItemOptionsError("이미 옵션이 있는 품목이 섞여 있습니다. 화면을 새로 열어 주세요.")
    confirmed = _stage(order) in CONFIRMED_STAGES
    planned = []
    for no, item in targets:
        uid = str(item.get("uid") or "")
        entry = raw.get(uid)
        if not uid or not isinstance(entry, dict):
            raise ItemOptionsError(f"항목 {no} 옵션을 골라 주세요. 없으면 \"옵션 없음\"을 고르면 됩니다.")
        base = str(entry.get("base") or "").strip()
        options = clean_item_options(entry, base, price_list.sheet, no=no)
        if options["base_key"] is None:
            raise ItemOptionsError(f"항목 {no}: 단가표 제품을 골라 주세요.")
        if confirmed and options["state"] == "later":
            raise ItemOptionsError(f"항목 {no}: 도면이 이미 확정된 주문이라 \"상담 후 정함\"은 고를 수 없습니다.")
        planned.append((uid, options))
    stages = ("PARTNER", "CURRENT", "CONFIRMED") if confirmed else ("PARTNER", "CURRENT")
    now = now_utc_naive()
    for uid, options in planned:
        for stage in stages:
            row = (db.query(OrderItemOption).filter(OrderItemOption.order_id == order.id, OrderItemOption.item_uid == uid,
                                                     OrderItemOption.stage == stage).first()
                   or OrderItemOption(order_id=order.id, item_uid=uid, stage=stage))
            row.state, row.base_key = options["state"], options["base_key"]
            row.lines, row.customs, row.changes = list(options["lines"]), list(options["customs"]), []
            row.price_list_id, row.updated_by, row.updated_at = price_list.id, user_id, now
            db.add(row)
    db.flush()
    return {"order": order, "items": len(planned), "stages": list(stages), "confirmed": confirmed}
