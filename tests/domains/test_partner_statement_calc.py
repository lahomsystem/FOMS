"""협력사 거래명세서 금액 계산(설계서 docs/specs/2026-11-03-partner-statement_SPEC.md §4 · §8) — 순수 함수.

자 수 반올림 경계(12.33 → 12.3 · 9.33 → 9.3 · 12.35 → 12.4 · 3,000 → 10.0) · 복합 폭 · 구간 경계(900 · 901) ·
넘친 만큼(1000 → 1번, 1001 → 2번) · 원 단위 · 공급가액 + 세액 = 합계 · 기본 포함(빈칸 · 0원은 줄 없이 비고,
값이 생기면 줄) · 커스텀(금액 빈 줄) · 못 찾은 줄. 단가는 모두 가짜 값이다(저장소 공개).
"""
from __future__ import annotations

import copy

import pytest

from foms.services.partners.statement_calc import calc_item, parse_mm, summarize


def _item(key, name, price, **meta):
    base = {"key": key, "name_col": 0, "price_col": 1, "role": "option", "unit": "개", "kind": "count",
            "cond": {}, "partner_label": "", "pick_names": [name], "for_products": [], "pickable": True}
    base.update(meta)
    return {"cells": [name, price], "items": [base]}


SHEET = {"schema": 1, "brand": "test", "seq": 20, "retired": [], "categories": [
    {"id": "c0", "side": "left", "title": "기본 제품 가격", "headers": ["제품명", "자당 단가"], "types": ["text", "price"],
     "layout": {}, "rows": [
         _item("r1", "슬라이딩", 100000, role="product", kind="ja", unit="자"),
         _item("r2", "주방 (1m 당)", 500000, role="product", kind="meter", unit="m"),
         _item("r3", "파우더장 (600 이하)", 300000, role="product", kind="band",
               cond={"dim": "width", "max": 600, "group": "파우더장"}),
         _item("r4", "파우더장 (900 이하)", 400000, role="product", kind="band",
               cond={"dim": "width", "min": 601, "max": 900, "group": "파우더장", "over_key": "r9"}),
         _item("r5", "서랍장 (3단)", 250000, role="product", kind="fixed"),
     ]},
    {"id": "c1", "side": "left", "title": "제품 추가 옵션", "headers": ["품목", "추가 금액"], "types": ["text", "price"],
     "layout": {}, "rows": [
         _item("r6", "내부서랍 1단 (대)", 40000),
         _item("r7", "측면 EP 마감 (폭 300mm 이하)", 30000, kind="band",
               cond={"dim": "depth", "max": 300, "group": "EP"}),
         _item("r8", "측면 EP 마감 (폭 301~800mm)", 60000, kind="band",
               cond={"dim": "depth", "min": 301, "max": 800, "group": "EP"}),
         _item("r9", "넓이 추가 (100mm 당)", 100000, kind="over", cond={"per": 100}),
         _item("r10", "깊이 줄임", ""),
         _item("r11", "TYPE A", 0, pickable=False),
         _item("r12", "피닉스바", 15000),
     ]},
]}


def _calc(width="3700", depth="620", base_key="r1", lines=(), customs=(), internal="", sheet=SHEET, spec_rows=None):
    item = {"uid": "u-1", "title": "슬라이딩", "base_key": base_key, "internal": internal,
            "spec_rows": spec_rows if spec_rows is not None else [{"width": width, "depth": depth, "height": "2290"}],
            "lines": list(lines), "customs": list(customs)}
    return calc_item(sheet, item)


@pytest.mark.parametrize("width, qty, amount", [
    ("3700", "12.3", 1230000),   # 12.333 → 12.3
    ("2800", "9.3", 930000),     # 9.333 → 9.3 (사람이 9.4 로 쓰던 것 — 결정 3)
    ("3705", "12.4", 1240000),   # 12.35 → 12.4 (0.5 는 위로)
    ("3000", "10.0", 1000000),
    ("5700(2402+1864+1434)", "19.0", 1900000),  # 복합 폭은 괄호 앞 값
])
def test_ja_quantity_rounds_half_up_at_one_decimal(width, qty, amount):
    group = _calc(width=width)
    line = group["lines"][0]
    assert (line["key"], line["unit"], line["qty"], line["amount"]) == ("r1", "자", qty, amount)
    assert group["needs"] == []


def test_parse_mm_shapes():
    assert parse_mm("5700(2402+1864+1434)") == 5700
    assert parse_mm("2400+1200") == 3600
    assert parse_mm("2,400") == 2400
    assert parse_mm("") is None and parse_mm("상담") is None and parse_mm(None) is None


def test_each_spec_row_is_its_own_base_line():
    group = _calc(spec_rows=[{"width": "2400"}, {"width": "1800"}])
    assert [(line["qty"], line["amount"]) for line in group["lines"]] == [("8.0", 800000), ("6.0", 600000)]
    assert group["subtotal"] == 1400000


def test_meter_quantity_uses_same_rounding():
    line = _calc(width="2450", base_key="r2")["lines"][0]
    assert (line["unit"], line["qty"], line["amount"]) == ("m", "2.5", 1250000)


@pytest.mark.parametrize("width, key, extra", [
    ("600", "r3", None), ("601", "r4", None), ("900", "r4", None),
    ("1000", "r4", ("r9", "1", 100000)), ("1001", "r4", ("r9", "2", 200000)),
])
def test_band_picks_row_by_width_and_adds_over_lines(width, key, extra):
    group = _calc(width=width, base_key="r3")  # 묶음 어느 줄을 골라도 가로로 다시 고른다
    assert group["lines"][0]["key"] == key
    over = [(line["key"], line["qty"], line["amount"]) for line in group["lines"][1:]]
    assert over == ([extra] if extra else [])


def test_band_over_without_link_is_a_need_not_a_guess():
    sheet = copy.deepcopy(SHEET)
    sheet["categories"][0]["rows"][3]["items"][0]["cond"].pop("over_key")
    group = _calc(width="1000", base_key="r3", sheet=sheet)
    assert [line["key"] for line in group["lines"]] == ["r4"]
    assert any("100mm" in need for need in group["needs"])


def test_option_lines_count_and_ep_band_by_depth():
    group = _calc(depth="620", lines=[{"key": "r6", "qty": 2, "memo": "2번 통"}, {"key": "r7", "qty": 1, "memo": "왼쪽"},
                                      {"key": "r12", "qty": 3}])
    rows = [(line["key"], line["qty"], line["amount"], line["spec"]) for line in group["lines"][1:]]
    assert rows == [("r6", "2", 80000, "2번 통"), ("r8", "1", 60000, "왼쪽"), ("r12", "3", 45000, "")]
    assert group["subtotal"] == 1230000 + 80000 + 60000 + 45000


def test_included_rows_make_no_line_but_a_note_until_they_get_a_price():
    group = _calc(internal="A A J", lines=[{"key": "r10", "qty": 1}, {"key": "r11", "qty": 1}])
    assert [line["key"] for line in group["lines"]] == ["r1"]
    assert group["lines"][0]["note"] == "내부 A A J 포함 · 깊이 줄임 포함 · TYPE A 포함"
    priced = copy.deepcopy(SHEET)
    priced["categories"][1]["rows"][4]["cells"][1] = 20000  # 다음 판에서 값이 생기면 줄이 된다
    group = _calc(lines=[{"key": "r10", "qty": 2}], sheet=priced)
    assert [(line["key"], line["amount"]) for line in group["lines"]] == [("r1", 1230000), ("r10", 40000)]


def test_undecided_internal_text_is_not_a_note():
    assert _calc(internal="상담")["notes"] == []


def test_custom_is_an_empty_amount_line_and_summary_is_incomplete():
    group = _calc(customs=[{"text": "하부 300 띄움 시공"}])
    custom = group["lines"][-1]
    assert (custom["source"], custom["amount"], custom["unit_price"]) == ("custom", None, None)
    assert summarize([group])["complete"] is False
    custom["amount"] = 230000
    assert summarize([group])["complete"] is True


def test_missing_base_and_unknown_option_are_needs():
    group = _calc(base_key=None, lines=[{"key": "r99", "qty": 1}])
    assert group["lines"] == [] and len(group["needs"]) == 2
    assert summarize([group])["complete"] is False


def test_retired_row_still_prices_old_selection():
    sheet = copy.deepcopy(SHEET)
    sheet["retired"] = [{"key": "r50", "name": "옛 옵션", "price": 10000, "kind": "count", "unit": "개", "cond": {},
                         "pickable": False}]
    group = _calc(lines=[{"key": "r50", "qty": 2}], sheet=sheet)
    assert (group["lines"][-1]["name"], group["lines"][-1]["amount"]) == ("옛 옵션", 20000)


@pytest.mark.parametrize("total, supply, vat", [(1934500, 1758636, 175864), (100000, 90909, 9091), (0, 0, 0), (11, 10, 1)])
def test_supply_and_vat_add_up_to_total(total, supply, vat):
    group = {"lines": [{"amount": total}], "needs": []}
    summary = summarize([group])
    assert (summary["total"], summary["supply"], summary["vat"]) == (total, supply, vat)
    assert summary["supply"] + summary["vat"] == summary["total"]
