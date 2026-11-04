"""협력사 품목 옵션 고르기(설계서 docs/specs/2026-11-03-partner-statement_SPEC.md §3.2 · §5.2 · §8 — 2단계).

협력사에 단가표 지금 판이 있으면 새 주문 · 품목 고치기의 옵션 칸은 꼭 고르는 칸이다: 고른 줄은 품목 uid 마다 원문(PARTNER) ·
지금 값(CURRENT) 두 줄로 남고, 품목 JSON ``option_detail`` 에는 요약 글이 들어간다. 대조군: 단가표가 없는 협력사(다른 회사)는
지금처럼 옵션 글 칸이다. 협력사 화면에 싣는 목록에는 이름만 있고 금액은 없다. 우리 주문 화면 저장(PUT structured)은 옵션 표를
건드리지 않는다. 단가 · 이름은 가짜다.
"""
from __future__ import annotations

import copy
import html as htmllib
import json
import re

import pytest

from db import db_session
from foms.services.partners.item_options import ItemOptionsError, clean_item_options, options_summary, pick_lists
from foms.services.partners.price_list import save_price_list
from models import Order, OrderItemOption, User
from tests.security.partner_fixtures import _PAYLOAD, _client, _create, world  # noqa: F401 — pytest fixture 재노출


def _row(key, name, price, *, role="option", kind="count", unit="개", pick=None, only=None, pickable=True, cond=None):
    return {"cells": [name, price], "items": [{
        "key": key, "name_col": 0, "price_col": 1, "role": role, "unit": unit, "kind": kind, "cond": cond or {},
        "partner_label": "", "pick_names": pick or [name], "for_products": only or [], "pickable": pickable}]}


SHEET = {"schema": 1, "brand": "t", "seq": 20, "retired": [], "categories": [
    {"id": "c0", "side": "left", "title": "기본 제품 가격", "headers": ["제품명", "자당 단가"], "types": ["text", "price"],
     "layout": {}, "rows": [
         _row("r1", "여닫이 / 몰딩, 무몰딩", 91234, role="product", kind="ja", unit="자", pick=["몰딩 여닫이", "무몰딩 여닫이"]),
         _row("r2", "슬라이딩", 98765, role="product", kind="ja", unit="자"),
         _row("r3", "침대 붙박이장", 87654, role="product", kind="ja", unit="자"),
     ]},
    {"id": "c1", "side": "left", "title": "제품 추가 옵션", "headers": ["품목", "추가 금액"], "types": ["text", "price"],
     "layout": {}, "rows": [
         _row("r4", "슬라이딩 거울 도어", 176543, unit="짝"),
         _row("r5", "측면 EP 마감 (폭 300mm 이하)", 31111, kind="band", pick=["측면 마감판(EP)"],
              cond={"dim": "depth", "max": 300, "group": "EP"}),
         _row("r6", "측면 EP 마감 (폭 301~800mm)", 62222, kind="band", pick=["측면 마감판(EP)"],
              cond={"dim": "depth", "min": 301, "group": "EP"}),
         _row("r7", "침대 프레임 Q", 765432, only=["침대 붙박이장"]),
         _row("r8", "라인 조명 추가 (1m 당)", 43210, unit="m"),
         _row("r9", "여닫이 통 추가 (한통)", 200001, pickable=False),
     ]},
]}
PRICES = ("91234", "98765", "87654", "176543", "31111", "62222", "765432", "43210", "200001")


@pytest.fixture
def priced(app, world):
    save_price_list(db_session, world["org_a"], SHEET, label="11월판", effective_from="2026-11-01", base_id=None, user_id=None)
    db_session.commit()
    return world


def _item(name="슬라이딩", **options):
    return {"product_name": name, "spec_rows": [{"spec_width": "3700", "spec_depth": "620", "spec_height": "2290"}],
            "options": options}


def _rows(order_id, stage=None):
    db_session.expire_all()
    q = db_session.query(OrderItemOption).filter(OrderItemOption.order_id == order_id)
    if stage:
        q = q.filter(OrderItemOption.stage == stage)
    return q.order_by(OrderItemOption.id).all()


# ── 서비스(순수) ─────────────────────────────────────────────────────────
def test_pick_lists_have_names_and_units_but_no_prices():
    lists = pick_lists(SHEET)
    assert lists["products"] == [{"label": "여닫이 / 몰딩, 무몰딩", "items": ["몰딩 여닫이", "무몰딩 여닫이"]},
                                 {"label": "기본 제품 가격", "items": ["슬라이딩", "침대 붙박이장"]}]
    names = [it["name"] for g in lists["options"] for it in g["items"]]
    assert names == ["슬라이딩 거울 도어", "측면 마감판(EP)", "침대 프레임 Q", "라인 조명 추가 (1m 당)"]  # 묶음 이름은 한 번 · 숨긴 줄 없음
    assert lists["options"][0]["items"][2]["only"] == ["침대 붙박이장"]
    text = repr(lists)
    assert not any(price in text for price in PRICES)


def test_clean_item_options_rules():
    ok = clean_item_options({"lines": [{"key": "r4", "name": "슬라이딩 거울 도어", "qty": 2, "memo": "우측"},
                                       {"key": "r8", "qty": "2.5"}], "customs": [{"text": "하부 300 띄움"}]},
                            "슬라이딩", SHEET, no=1)
    assert ok["state"] == "chosen" and ok["base_key"] == "r2"
    assert [(l["key"], l["name"], l["qty"], l["memo"]) for l in ok["lines"]] == [
        ("r4", "슬라이딩 거울 도어", "2", "우측"), ("r8", "라인 조명 추가 (1m 당)", "2.5", "")]
    assert options_summary(ok, SHEET) == "슬라이딩 거울 도어 2짝(우측) · 라인 조명 추가 (1m 당) 2.5m · 커스텀: 하부 300 띄움"
    assert clean_item_options({"state": "none", "lines": [{"key": "r4"}]}, "몰딩 여닫이", SHEET, no=1) == {
        "state": "none", "base_key": "r1", "lines": [], "customs": []}
    assert clean_item_options({"state": "later"}, "직접 쓴 이름", SHEET, no=1)["base_key"] is None
    for raw, needle in [({}, "항목 2 옵션을 골라"), ({"state": "chosen"}, "골라"),
                        ({"lines": [{"key": "r99"}]}, "고를 수 없는 옵션"), ({"lines": [{"key": "r9"}]}, "고를 수 없는 옵션"),
                        ({"lines": [{"key": "r7"}]}, "옵션은 침대 붙박이장에만"), ({"lines": [{"key": "r4", "qty": "1.5"}]}, "소수점 없이"),
                        ({"lines": [{"key": "r4", "qty": 0}]}, "1부터 999까지")]:
        with pytest.raises(ItemOptionsError) as exc:
            clean_item_options(raw, "슬라이딩", SHEET, no=2)
        assert needle in str(exc.value), raw
    assert clean_item_options({"lines": [{"key": "r7"}]}, "침대 붙박이장", SHEET, no=1)["lines"][0]["key"] == "r7"


# ── 새 주문 · 품목 고치기 ───────────────────────────────────────────────
def test_new_order_saves_partner_and_current_rows_per_item_uid(app, priced):
    items = [_item(lines=[{"key": "r4", "name": "슬라이딩 거울 도어", "qty": 1, "memo": "우측"}],
                   customs=[{"text": "하부 300 띄움"}]),
             _item("몰딩 여닫이", state="later")]
    resp = _create(app, priced["partner_a"], {**_PAYLOAD, "items": items})
    assert resp.status_code == 200, resp.get_json()
    oid = resp.get_json()["data"]["order_id"]
    order = db_session.get(Order, oid)
    uids = [it["uid"] for it in order.structured_data["items"]]
    rows = _rows(oid)
    assert sorted((r.item_uid, r.stage) for r in rows) == sorted((u, s) for u in uids for s in ("PARTNER", "CURRENT"))
    first = [r for r in rows if r.item_uid == uids[0] and r.stage == "CURRENT"][0]
    assert (first.state, first.base_key, first.customs) == ("chosen", "r2", [{"text": "하부 300 띄움"}])
    assert first.lines == [{"key": "r4", "name": "슬라이딩 거울 도어", "qty": "1", "memo": "우측"}]
    assert first.price_list_id is not None
    assert [it["option_detail"] for it in order.structured_data["items"]] == [
        "슬라이딩 거울 도어 1짝(우측) · 커스텀: 하부 300 띄움", "상담 후 정함"]
    assert order.structured_data["partner_intake"]["items"][1]["option_detail"] == "상담 후 정함"


def test_new_order_without_options_is_refused_when_price_list_exists(app, priced):
    resp = _create(app, priced["partner_a"], {**_PAYLOAD, "items": [_item(state="none"), {"product_name": "슬라이딩"}]})
    assert resp.status_code == 400
    assert "항목 2 옵션을 골라" in resp.get_json()["error"]
    assert db_session.query(Order).count() == 0 and db_session.query(OrderItemOption).count() == 0


def test_partner_without_price_list_keeps_free_text_options(app, priced):
    resp = _create(app, priced["partner_b"], {**_PAYLOAD, "items": [{"product_name": "붙박이장", "option_detail": "LED 바"}]})
    assert resp.status_code == 200, resp.get_json()  # 대조군: 단가표가 없는 회사는 지금 그대로
    order = db_session.get(Order, resp.get_json()["data"]["order_id"])
    assert order.structured_data["items"][0]["option_detail"] == "LED 바" and db_session.query(OrderItemOption).count() == 0


def test_item_edit_rewrites_rows_and_drops_removed_items(app, priced):
    resp = _create(app, priced["partner_a"], {**_PAYLOAD, "items": [_item(state="none"), _item("몰딩 여닫이", state="later")]})
    oid = resp.get_json()["data"]["order_id"]
    uids = [it["uid"] for it in db_session.get(Order, oid).structured_data["items"]]
    client = _client(app, db_session.get(User, priced["partner_a"]))
    edit = client.put(f"/api/partner/orders/{oid}/items", json={"items": [
        {**_item(lines=[{"key": "r5", "qty": 2, "memo": "양쪽"}]), "uid": uids[0]}]})
    assert edit.status_code == 200, edit.get_json()
    rows = _rows(oid, "CURRENT")
    assert [(r.item_uid, r.state, r.lines[0]["key"], r.lines[0]["name"]) for r in rows] == [
        (uids[0], "chosen", "r5", "측면 마감판(EP)")]
    assert {r.item_uid for r in _rows(oid)} == {uids[0]}
    bad = client.put(f"/api/partner/orders/{oid}/items", json={"items": [{"product_name": "슬라이딩", "uid": uids[0]}]})
    assert bad.status_code == 400 and "옵션을 골라" in bad.get_json()["error"]
    assert _rows(oid, "CURRENT")[0].state == "chosen"  # 거절된 저장은 아무것도 바꾸지 않는다


def test_staff_structured_save_leaves_option_rows_alone(app, priced):
    resp = _create(app, priced["partner_a"], {**_PAYLOAD, "items": [_item(lines=[{"key": "r4", "qty": 1}])]})
    oid = resp.get_json()["data"]["order_id"]
    before = [(r.item_uid, r.stage, r.state, r.lines) for r in _rows(oid)]
    order = db_session.get(Order, oid)
    sd = dict(order.structured_data)
    sd["items"] = [{**sd["items"][0], "option_detail": "직원이 고친 글"}]
    staff = _client(app, db_session.get(User, priced["admin"]))
    put = staff.put(f"/api/orders/{oid}/structured", json={"structured_data": sd})
    assert put.status_code == 200, put.get_json()
    assert [(r.item_uid, r.stage, r.state, r.lines) for r in _rows(oid)] == before


# ── 화면 ────────────────────────────────────────────────────────────────
def _attr(html: str, name: str) -> str:
    """data-* JSON 칸을 풀어 글로(tojson 은 한글을 유니코드 이스케이프로 적는다)."""
    match = re.search(name + r"='([^']*)'", html)
    return json.dumps(json.loads(htmllib.unescape(match.group(1))), ensure_ascii=False) if match else ""


def test_product_tree_groups_classified_products_and_puts_the_rest_under_etc():
    # 3단 고르기(설계서 2026-11-04-partner-product-tree §2.2) — 분류 없는 제품은 맨 뒤 "기타", 금액은 싣지 않는다.
    assert pick_lists(SHEET)["tree"] == [{"label": "기타", "groups": [
        {"label": "여닫이 / 몰딩, 무몰딩", "items": ["몰딩 여닫이", "무몰딩 여닫이"]},
        {"label": "기본 제품 가격", "items": ["슬라이딩", "침대 붙박이장"]}]}]
    sheet = copy.deepcopy(SHEET)
    sheet["categories"][0]["rows"][1]["items"][0]["tree"] = ["붙박이장", "슬라이딩"]
    sheet["categories"][0]["rows"][0]["items"][0]["tree"] = ["붙박이장", "여닫이"]
    tree = pick_lists(sheet)["tree"]
    assert tree == [{"label": "붙박이장", "groups": [{"label": "여닫이", "items": ["몰딩 여닫이", "무몰딩 여닫이"]},
                                                  {"label": "슬라이딩", "items": ["슬라이딩"]}]},
                    {"label": "기타", "groups": [{"label": "기본 제품 가격", "items": ["침대 붙박이장"]}]}]
    assert not any(price in repr(tree) for price in PRICES)
    # 한 줄의 이름마다 다른 분류(같은 단가 — TV 월플렉스 · 침대 붙박이 따로) · 대분류 차례(tree_order)
    sheet["categories"][0]["rows"][0]["items"][0]["tree_by_name"] = {"무몰딩 여닫이": ["무몰딩", "무몰딩"]}
    sheet["tree_order"] = ["무몰딩", "붙박이장"]
    assert [(b["label"], [(g["label"], g["items"]) for g in b["groups"]]) for b in pick_lists(sheet)["tree"]] == [
        ("무몰딩", [("무몰딩", ["무몰딩 여닫이"])]),
        ("붙박이장", [("여닫이", ["몰딩 여닫이"]), ("슬라이딩", ["슬라이딩"])]),
        ("기타", [("기본 제품 가격", ["침대 붙박이장"])])]


def test_new_order_page_ships_names_only(app, priced):
    html = _client(app, db_session.get(User, priced["partner_a"])).get("/partner/orders/new").get_data(as_text=True)
    assert "data-pp-option-catalog" in html and "data-pp-optfield" in html and "partner-item-options.js" in html
    assert "몰딩 여닫이" in _attr(html, "data-pp-product-names") and "측면 마감판(EP)" in _attr(html, "data-pp-option-catalog")
    assert '"tree"' in _attr(html, "data-pp-product-names") and "partner-product-picker.js" in html  # 3단 고르기 창
    assert not any(price in html for price in PRICES)
    other = _client(app, db_session.get(User, priced["partner_b"])).get("/partner/orders/new").get_data(as_text=True)
    assert "data-pp-option-catalog" not in other and "data-pp-optfield" not in other  # 대조군


def test_order_page_prefills_current_options_while_editable(app, priced):
    resp = _create(app, priced["partner_a"], {**_PAYLOAD, "items": [_item(lines=[{"key": "r4", "qty": 2}])]})
    oid = resp.get_json()["data"]["order_id"]
    uid = db_session.get(Order, oid).structured_data["items"][0]["uid"]
    html = _client(app, db_session.get(User, priced["partner_a"])).get(f"/partner/orders/{oid}").get_data(as_text=True)
    assert "data-pp-item-options" in html and uid in html and "data-pp-optfield" in html
    assert not any(price in html for price in PRICES)
