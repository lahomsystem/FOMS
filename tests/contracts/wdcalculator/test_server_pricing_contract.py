"""서버 계산 = 화면 계산 CI 계약(플랜 C10-6 · 설계서 17.4 길 3 · 원장 R10-24).

같은 입력 묶음을 node 로 ``static/js/wdcalculator/pricing-core.js``(직원 화면 계산 — 정본)에 돌린 값과 서버
:func:`foms.services.wdcalculator.pricing.compute_estimate` 값이 배정밀도 그대로 · 원 단위로 같아야 한다. 입력은 제품 id ·
치수 · 수량 같은 합성 값이고, 단가는 이미 공개된 처음 채우기 파일(``data/products.json`` · ``data/additional_options.json``)을
읽어 쓴다 — 이 파일에는 금액 숫자를 적지 않는다(기대값은 node 가 그 자리에서 낸다).

node 가 없으면 건너뛰지 않고 실패한다 — CI(ubuntu-latest)에는 node 가 있고, 같은 스위트의
``tests/domains/test_drawing_bom_calc.py`` 도 node 를 꼭 요구한다.
"""

from __future__ import annotations

import copy
import json
import math
import shutil
import subprocess
from pathlib import Path

from foms.services.wdcalculator import pricing

REPO_ROOT = Path(__file__).resolve().parents[3]
NODE_SCRIPT = REPO_ROOT / "tests" / "support" / "wdcalculator_server_pricing_contract_node.js"
WIDTHS = (300, 1234, 2400, 3601, 4799, 999, 10, 7, 1800.5, 2999, 600, 4500)
FIELDS = ("base_calculate", "base_collect", "additional", "total_calculate", "total_collect")


def _seed(name: str, key: str) -> list[dict]:
    return json.loads((REPO_ROOT / "data" / name).read_text(encoding="utf-8"))[key]


PRODUCTS = _seed("products.json", "products")
CATEGORIES = _seed("additional_options.json", "categories")
OPTION_REFS = [f"{c['id']}:{o['id']}" for c in CATEGORIES for o in c.get("options") or () if (o.get("price") or 0) > 0]
OPTION_PRICES = [o["price"] for c in CATEGORIES for o in c.get("options") or () if (o.get("price") or 0) > 0]


def _select(product_id, width, fees=()) -> dict:
    return {"mode": "select", "productId": product_id, "widthMm": width, "widthInput": str(width),
            "additionalFees": [{"name": f"추가{i}", "amount": amount} for i, amount in enumerate(fees)]}


def _estimate(components, *, options=(), products=None) -> dict:
    return {"kind": "estimate", "components": list(components), "products": products or PRODUCTS,
            "options": list(options)}


def _cases() -> list[dict]:
    cases = [_estimate([_select(p["id"], WIDTHS[i % len(WIDTHS)])]) for i, p in enumerate(PRODUCTS)]
    for k, qty in enumerate((1, 2, 0, 3, "2")):  # 수량 0 · 글 수량도 화면 규칙 그대로(0 → 1)
        refs = [(OPTION_REFS[(k * 3 + j) % len(OPTION_REFS)], qty) for j in range(1 + k % 3)]
        cases.append(_estimate([_select(PRODUCTS[k]["id"], WIDTHS[k])], options=pricing.option_rows(refs, CATEGORIES)))
    one_m = next(p for p in PRODUCTS if p["pricing_type"] == "1m")
    thirty = next(p for p in PRODUCTS if p["pricing_type"] == "30cm")
    manual_30 = {"mode": "manual", "widthMm": 2700, "widthInput": "2700", "additionalFees": [], "manualName": "합성",
                 "manualPricing": {"pricing_type": "30cm", "price_30cm": thirty["price_30cm"],
                                   "price_1cm": thirty["price_1cm"]}}
    manual_1m = {"mode": "manual", "widthMm": 1650, "widthInput": "1650", "additionalFees": [],
                 "manualPricing": {"pricing_type": "1m", "price_1m": one_m["price_1m"]}}
    cases += [  # 구성품 여럿 · 구성품 추가금(단가는 옵션 목록 값을 빌린다)
        _estimate([_select(PRODUCTS[0]["id"], 2400), _select(PRODUCTS[4]["id"], 1200, fees=OPTION_PRICES[:2])]),
        _estimate([manual_30, manual_1m, _select(one_m["id"], 3050)],
                  options=pricing.option_rows([(OPTION_REFS[1], 2)], CATEGORIES)),
        _estimate([_select(thirty["id"], 900, fees=OPTION_PRICES[2:5]), manual_30]),
    ]
    odd = dict(copy.deepcopy(thirty), id=987654, pricing_type="2m")  # 모르는 가격 방식 — 화면도 0
    empty = {"id": 987655, "name": "합성 빈 값", "pricing_type": "30cm"}  # 단가 칸 없음 — 0
    cases += [
        _estimate([_select(999999, 2400, fees=OPTION_PRICES[:1])]),  # 없는 제품 + 추가금
        _estimate([{"mode": "select", "productId": None, "widthMm": 0, "widthInput": "0", "additionalFees": []}]),
        _estimate([{"mode": "select", "productId": PRODUCTS[1]["id"], "widthMm": 0, "widthInput": "abc",
                    "additionalFees": []}]),  # 가로 글 못 읽음 — 둘 다 계산하지 않는다
        _estimate([_select(str(PRODUCTS[2]["id"]), 2100)]),  # 글 id
        _estimate([_select(odd["id"], 2400)], products=[*PRODUCTS, odd]),
        _estimate([_select(empty["id"], 2400)], products=[*PRODUCTS, empty]),
        _estimate([{"mode": "direct", "productId": None, "widthMm": 1500, "widthInput": "1500",
                    "additionalFees": [{"name": "", "amount": OPTION_PRICES[3]}]}]),
    ]
    return cases + _odd_cases(thirty)


def _odd_cases(thirty: dict) -> list[dict]:
    """JS ``Number()`` · 예외 규칙 맞춤(검수 R17-7) — 글 숫자(BOM · 0b · 0o · 전각 · 아랍 숫자 · 무한) · 배열 · 빈 칸."""
    widths = ["﻿2400", "0b100101100000", "0o4540", "0B101", "-0x10", "２４００",
              "٢٤٠٠", "Infinity", " 2400\n", [2400], ["2400"], [2400, 1]]
    out = [_estimate([{"mode": "select", "productId": thirty["id"], "widthMm": w, "widthInput": "",
                       "additionalFees": []}]) for w in widths]
    arrays = dict(thirty, id=987656, price_30cm=[thirty["price_30cm"]], price_1cm=[thirty["price_1cm"]])
    option = pricing.option_rows([(OPTION_REFS[0], 1)], CATEGORIES)[0]
    out += [
        _estimate([_select(arrays["id"], 2410)], products=[*PRODUCTS, arrays]),  # 배열 단가
        _estimate([_select(thirty["id"], 2400)], options=[dict(option, quantity=[2]), dict(option, price=[option["price"]])]),
        _estimate([dict(_select(thirty["id"], 2400), additionalFees=[None])]),  # 빈 추가금 칸 — 둘 다 계산하지 않는다
        _estimate([None]),  # 빈 구성품 칸 — 둘 다 계산하지 않는다
        _estimate([5, dict(_select(thirty["id"], 2400), additionalFees=[5, "x", {"amount": "﻿7"}])],
                  options=["깨진 줄", None, option]),
    ]
    return out


def _aggregate_cases(estimates: list[dict]) -> list[dict]:
    rows = [{"basePrice": e["base_collect"], "additionalPrice": e["additional"]} for e in estimates
            if e["ok"] and math.isfinite(e["base_collect"]) and math.isfinite(e["additional"])]  # JSON 에 NaN 을 못 싣는다
    return [{"kind": "aggregate", "estimates": rows[:3], "coupon": 0, "shipping": 0, "included": False},
            {"kind": "aggregate", "estimates": rows[3:9], "coupon": 0, "shipping": OPTION_PRICES[0], "included": True},
            {"kind": "aggregate", "estimates": rows, "coupon": 0, "shipping": OPTION_PRICES[1], "included": False}]


def _server(case: dict) -> dict:
    if case["kind"] == "aggregate":
        return pricing.aggregate_totals(case["estimates"], case["coupon"], case["shipping"], case["included"])
    try:
        got = pricing.compute_estimate(case["components"], case["products"], case["options"])
    except pricing.EstimateInputError:  # 가로 글 · 빈 칸 — 화면도 예외를 낸다
        return {"ok": False}
    values = (got.base_price_calculate, got.base_price_collect, got.additional_price, got.total_price_calculate,
              got.total_price_collect)
    return {"ok": True, **dict(zip(FIELDS, values)), "components": got.components,
            "won_total": pricing.won(got.total_price_collect) if math.isfinite(got.total_price_collect) else None}


def _node(cases: list[dict]) -> list[dict]:
    node = shutil.which("node")
    assert node, "node 가 PATH 에 있어야 한다 — 계약 시험은 건너뛰지 않는다(CI ubuntu-latest 에는 있다)"
    proc = subprocess.run([node, str(NODE_SCRIPT)], input=json.dumps({"cases": cases}, ensure_ascii=False),
                          capture_output=True, text=True, encoding="utf-8", timeout=60, cwd=str(REPO_ROOT))
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _same(server, screen) -> bool:
    if isinstance(server, float) and not math.isfinite(server):
        return screen is None  # JSON 에서 NaN · 무한은 null
    return server == screen


def test_server_pricing_equals_screen_pricing_to_the_won():
    cases = _cases()
    screen = _node(cases)
    server = [_server(case) for case in cases]
    cases += _aggregate_cases(server)
    screen += _node(cases[len(screen):])
    server += [_server(case) for case in cases[len(server):]]
    assert len(cases) >= 20 and len(screen) == len(cases)
    for index, (mine, theirs) in enumerate(zip(server, screen)):
        assert set(mine) == set(theirs), index
        for key in mine:
            assert _same(mine[key], theirs[key]), (index, key)
    priced = [s for s in server if s.get("ok") and (s.get("won_total") or 0) > 0]
    assert len(priced) >= 20  # 금액이 난 견적만 세어도 20건 이상 원 단위로 같다
    assert any(s.get("ok") is False for s in server)  # 계산 실패도 같이 갈린다


def test_option_rows_use_server_option_list():
    ref = OPTION_REFS[0]
    category_id, option_id = ref.split(":")
    category = next(c for c in CATEGORIES if str(c["id"]) == category_id)
    option = next(o for o in category["options"] if str(o["id"]) == option_id)
    assert pricing.option_rows([(ref, 2)], CATEGORIES) == [
        {"name": f"{category['name']} > {option['name']}", "price": option["price"], "quantity": 2}]
    try:
        pricing.option_rows([("0:0", 1)], CATEGORIES)
    except KeyError:
        pass
    else:
        raise AssertionError("모르는 옵션 id 를 받았다")
