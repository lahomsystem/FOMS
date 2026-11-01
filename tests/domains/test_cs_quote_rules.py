"""AI 견적 규칙 층(사장님 결정 D73) · 서버 숫자 읽기 맞춤(검수 R17-7) · 경계(R17-9).

화면 계산(``compute_estimate`` = pricing-core.js, 계약 시험)은 그대로이고, AI 견적 길만 30cm 제품의 남는 mm 를 cm 로 올리고
최소 길이 규칙(여닫이 1500 · 슬라이딩 2400 · 모름 2400)을 얹는다. 기대값: 여닫이 · 슬라이딩 · 모름 · 최소 없음은 **고친
가로로 node 화면 계산을 돌린 값**, cm 비례는 합성 단가(가짜 값)로 식을 본다. 공개 단가 숫자는 적지 않는다.
"""

from __future__ import annotations

import math

import pytest

from foms.services.cs_agent import quote_brain as qb, quote_calc as qc, quote_rules as qr
from foms.services.wdcalculator import catalog as cat
from foms.services.wdcalculator import pricing
from tests.contracts.wdcalculator.test_server_pricing_contract import _node
from tests.support.cs_quote_support import (
    CATEGORIES, HAUD, LAHOM, MOLD, OPTION, OTHER, SLIDING, ask, catalog, evaluate, rule_item, space, won,
)

HINGE = dict(MOLD, id=990101, quote_rule="hinge")
NONE = dict(MOLD, id=990102, quote_rule="none")
PRODUCTS = [*LAHOM, HINGE, NONE]


def _screen(product, widths):
    """고친 가로로 node 화면 계산을 돌린 값(원) 목록."""
    cases = [{"kind": "estimate", "products": PRODUCTS, "options": [],
              "components": [{"mode": "select", "productId": product["id"], "widthMm": w}]} for w in widths]
    return [row["won_total"] for row in _node(cases)]


def test_the_brand_field_beats_the_name():
    tagged = dict(MOLD, id=990301, brand="HAUD")  # 이름은 라홈 같지만 브랜드 칸이 하우드
    renamed = dict(HAUD, id=990302, brand="LAHOM")  # 이름은 '하우드…'지만 브랜드 칸이 라홈
    odd = dict(MOLD, id=990303, brand="OTHER")  # 모르는 브랜드 값은 빈 칸처럼(이름으로)
    assert [p["id"] for p in catalog(products=[MOLD, tagged, renamed, odd]).products_of()] == [
        MOLD["id"], 990302, 990303]
    assert [p["id"] for p in catalog(products=[tagged, HAUD]).products_of("HAUD")] == [990301, HAUD["id"]]


def test_rule_of_reads_the_field_then_the_name():
    assert [qr.rule_of(dict(MOLD, quote_rule=rule)) for rule in qr.RULES] == list(qr.RULES)
    assert qr.rule_of(MOLD) == qr.RULE_UNKNOWN and qr.rule_of(SLIDING) == qr.RULE_SLIDE  # 칸이 비면 이름으로
    assert qr.rule_of(dict(MOLD, quote_rule="sideways")) == qr.RULE_UNKNOWN  # 모르는 값은 빈 칸처럼
    assert qr.rule_of(dict(SLIDING, quote_rule="hinge")) == qr.RULE_HINGE  # 칸이 이름보다 앞선다
    assert [qr.rounded_width(w) for w in (2400, 2401, 2409, 2410, 5)] == [2400, 2410, 2410, 2410, 10]


@pytest.mark.parametrize(("product", "widths"), [
    (HINGE, {1500: 1500, 1501: 1510, 2399: 2400, 3005: 3010}),
    (SLIDING, {10: 2400, 1800: 2400, 2399: 2400, 2400: 2400, 2401: 2410, 4795: 4800}),
    (MOLD, {2400: 2400, 2401: 2410, 3605: 3610}),
    (NONE, {5: 10, 1005: 1010, 2400: 2400}),
])
def test_hinge_slide_unknown_and_none_equal_the_screen_at_the_fixed_width(product, widths):
    screen = _screen(product, list(widths.values()))
    for (width, fixed), expected in zip(widths.items(), screen):
        got = qr.price(product, width, [], PRODUCTS)
        same = (got.amount, got.width_used) == (expected, fixed)  # 비교 결과만 단언한다(실패 글에 금액을 찍지 않게)
        assert same, (product["id"], width)


@pytest.mark.parametrize(("product", "width"), [(HINGE, 1499), (HINGE, 1), (MOLD, 2399), (MOLD, 1500)])
def test_below_the_minimum_goes_to_a_human(product, width):
    with pytest.raises(qr.NeedsHuman) as caught:
        qr.price(product, width, [], PRODUCTS)
    assert caught.value.args == (qr.HUMAN_MIN_WIDTH,)
    outcome = evaluate(ask(space(product["id"], width)), catalog(extra=[HINGE, NONE]))
    assert (outcome.status, outcome.code, outcome.allowed) == (qc.STATUS_HUMAN, qr.HUMAN_MIN_WIDTH, ())


def test_linear_is_round_half_up_of_the_30cm_price_times_cm_over_30():
    def linear(price_30, width):
        product = {"id": 990201, "name": "합성 cm 비례", "pricing_type": "30cm", "price_30cm": price_30,
                   "price_1cm": 1, "quote_rule": "linear"}
        return qr.price(product, width, [], [product])

    # 합성 단가(가짜 값)로 식을 본다 — cm = 올림(가로 ÷ 10), 값 = 반올림(30cm 값 × cm ÷ 30)
    assert [linear(1000, w).amount for w in (300, 301, 455, 2400)] == [1000, 1033, 1533, 8000]
    assert (linear(15, 5).amount, linear(15, 5).width_used) == (1, 10)  # 0.5 는 올린다
    assert linear(45, 10).amount == 2 and linear(44, 10).amount == 1  # 1.5 → 2 · 1.4666 → 1
    with pytest.raises(ValueError):
        linear(0, 300)
    with_option = dict(MOLD, id=990202, quote_rule="linear")
    rows = pricing.option_rows([(OPTION, 2)], CATEGORIES)
    base = qr.price(with_option, 2405, [], [with_option]).amount
    extra = pricing.compute_estimate([], [], rows).additional_price
    assert qr.price(with_option, 2405, rows, [with_option]).amount == pricing.won(base + extra)


def test_one_meter_products_use_the_screen_value_as_is():
    (expected,) = _screen(OTHER, [1805])
    got = qr.price(OTHER, 1805, [], PRODUCTS)
    assert (got.amount == expected, got.width_used, got.note) == (True, 1805, "")


def test_the_calculator_line_says_which_width_was_priced():
    slide = evaluate(ask(space(SLIDING["id"], 1800)))
    assert slide.status == qc.STATUS_OK and "계산 가로 2,400mm — 슬라이딩 최소 2,400mm 값" in slide.allowed[0]
    assert slide.allowed[0].endswith(f"= {won(SLIDING['id'], 2400):,}원")
    mold = evaluate(ask(space(width=2405)))
    assert "계산 가로 2,410mm — 10mm 단위 올림" in mold.allowed[0]
    assert mold.allowed[0].endswith(f"= {won(MOLD['id'], 2410):,}원")
    assert "계산 가로" not in evaluate(ask(space(width=2410))).allowed[0]


# ── 서버 숫자 읽기 · 깨진 설정(R17-7) ────────────────────────────────────
@pytest.mark.parametrize(("text", "number"), [
    ("１２", math.nan), ("١٢", math.nan), ("﻿12", 12.0), ("0b11", 3.0), ("0o17", 15.0),
    ("0X1f", 31.0), ("-0x10", math.nan), ("0b2", math.nan), (" 12　", 12.0), ([5], 5.0), (["7"], 7.0), ([], 0.0),
    ([1, 2], math.nan), (None, 0.0), ({}, math.nan), ("1_000", math.nan), ("Infinity", math.inf),
])
def test_js_number_matches_javascript(text, number):
    got = pricing.js_number(text)
    assert (math.isnan(got) and math.isnan(number)) or got == number


def test_an_infinite_width_does_not_crash_and_goes_to_a_human():
    comp = {"mode": "select", "productId": MOLD["id"], "widthMm": "Infinity", "additionalFees": []}
    assert not math.isfinite(pricing.compute_estimate([comp], LAHOM, []).total_price_collect)
    with pytest.raises(pricing.EstimateInputError):
        pricing.compute_estimate([dict(comp, widthMm=2400, additionalFees=[None])], LAHOM, [])


def test_broken_option_entries_are_skipped_not_fatal():
    broken = {"id": 991, "name": "합성", "options": ["깨진 칸", None, 5]}
    assert evaluate(ask(), catalog(categories=[broken, "깨진 카테고리"])).status == qc.STATUS_OK
    assert pricing.option_rows([(OPTION, 1)], [broken, *CATEGORIES])[0]["quantity"] == 1


def test_a_lahom_candidate_never_prices_a_haud_row_with_the_same_id():
    twin = dict(HAUD, id=int(MOLD["id"]))
    lahom = dict(MOLD, id=str(MOLD["id"]))
    catalog_ = cat.Catalog((twin, lahom), tuple(CATEGORIES))
    asked = qb.read_ask('{"quote_request": true, "brand": "LAHOM", "unknown": [], "spaces": [{"space": "안방", '
                        f'"product_ids": ["{MOLD["id"]}"], "width_mm": 2400, "width_max_mm": 0, "height_mm": 0, '
                        '"door": "unknown", "handle": "unknown", "options": []}]}', catalog_)
    outcome = evaluate(asked, catalog_)
    assert outcome.status == qc.STATUS_OK
    haud_name = " ".join(str(HAUD["name"]).split())
    assert haud_name not in outcome.lines[1], "라홈 후보 줄에 하우드 제품 이름이 있다"


# ── 경계(R17-9) ──────────────────────────────────────────────────────────
def test_rounding_and_rule_boundaries():
    below_half = 0.5 - 2 ** -54  # 0.5 바로 아래 실수(JS Math.round 는 0) — 긴 숫자 글은 전화 꼴 검사에 걸려 실행 때 만든다
    assert [pricing.won(v) for v in (2.5, 1.5 - 1e-10, -0.5, below_half, 3.0)] == [3, 1, 0, 0, 3]
    rules = qc.build_rules([rule_item("검사: max_width=4800 min_width=600")])
    assert evaluate(ask(space(width=4800)), rules=rules).status == qc.STATUS_OK  # 최대 가로와 같으면 된다
    assert evaluate(ask(space(width=4801)), rules=rules).code == qc.HUMAN_RULE
    weird = dict(MOLD, id="abc")  # 목록에서는 찾지만 화면은 그 id 를 숫자로 못 읽어 견적에 담지 않는다
    outcome = evaluate(ask(space("abc")), cat.Catalog((weird,), tuple(CATEGORIES)))
    assert (outcome.status, outcome.code) == (qc.STATUS_HUMAN, qc.HUMAN_FAILED)  # 0원이 아니라 계산 실패


@pytest.mark.parametrize("width", [-500, 0, -1, 100_001])
def test_extracted_widths_at_or_below_zero_or_too_large_are_unknown(width):
    asked = qb.read_ask('{"quote_request": true, "brand": "LAHOM", "unknown": [], "spaces": [{"space": "안방", '
                        f'"product_ids": ["{MOLD["id"]}"], "width_mm": {width}, "width_max_mm": {width}, '
                        f'"height_mm": {width}, "door": "unknown", "handle": "unknown", "options": []}}]}}', catalog())
    (only,) = asked.spaces
    assert (only.width_mm, only.width_max_mm, only.height_mm) == (0, 0, 0)
    assert evaluate(asked).code == "width"  # 모르는 가로 → 한 가지만 묻기
