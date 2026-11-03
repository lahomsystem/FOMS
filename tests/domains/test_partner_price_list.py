"""협력사 단가표 판(설계서 docs/specs/2026-11-03-partner-statement_SPEC.md §3.1 · §5.1 · §8).

불러오기(단가표 HTML 의 <script id="data">) → 품목마다 열쇠 · 기본 계산 정보, 다시 불러와도 같은 이름은 같은 열쇠 ·
검사(금액 글자 · 겹치는 고르는 이름 · 없는 제품 이름) · 판 저장(새 판 ACTIVE · 옛 판 RETIRED 값 그대로 · 지운 줄은
retired 로 남음 · 그 사이 저장되면 막음). 단가 · 이름은 모두 가짜다(저장소 공개).
"""
from __future__ import annotations

import copy
import datetime as dt
import json

import pytest

from db import db_session
from foms.services.partners.price_list import (
    PriceListConflict,
    PriceListError,
    active_price_list,
    clean_sheet,
    import_sheets,
    iter_items,
    item_name,
    save_price_list,
)
from foms.services.partners.statement_calc import calc_item
from models import PartnerOrg, PartnerPriceList

SOURCE = {"brands": {
    "test": [
        {"id": "h0", "side": "left", "kind": "custom", "title": "기본 제품 가격", "headers": ["제품명", "자당 단가"],
         "types": ["text", "price"], "rowCells": [2, 2],
         "rows": [["여닫이 / 몰딩, 무몰딩", 90000], ["슬라이딩", 100000.0], ["서랍장 (3단)", 200000],
                  ["단독 파우더장 (600 이하) / 조명 콘센트 포함", 300000], ["단독 파우더장 (900 이하) / 조명 콘센트 포함", 400000],
                  ["주방 (상하부장) (1m 당)", 500000], ["", ""]]},
        {"id": "h1", "side": "left", "kind": "single", "title": "제품 추가 옵션", "headers": ["품목", "추가 금액"],
         "types": ["text", "price"],
         "rows": [["피닉스바", 10000], ["슬라이딩 거울 도어", 150000], ["측면 EP 마감 (폭 300mm 이하)", 30000],
                  ["측면 EP 마감 (폭 301~600mm)", 40000], ["측면 EP 마감 (폭 800mm 이상)", 60000]]},
        {"id": "h2", "side": "right", "kind": "paired", "title": "타입 및 내부 옵션",
         "headers": ["품목", "추가 금액", "품목", "추가 금액"], "types": ["text", "price", "text", "price"],
         "rows": [["TYPE A", 0, "TYPE B", 0], ["깊이 줄임 (통당)", "", "여닫이 통 추가 (한통)", ""],
                  ["넓이 추가 (100mm 당)", 100000, "", ""]]},
    ],
    "other": [{"id": "l0", "side": "left", "kind": "base", "title": "기본 제품 가격", "headers": ["제품명", "자당 단가", "1cm"],
               "types": ["text", "price", "price"], "rows": [["슬라이딩", 80000, 2700]]}],
}}


def _html(data=SOURCE) -> str:
    return ('<!doctype html><html><body><main>단가표</main><script id="data" type="application/json">'
            + json.dumps(data, ensure_ascii=False) + "</script></body></html>")


def _items(sheet):
    return {item_name(row, item): item for _c, row, item in iter_items(sheet)}


@pytest.fixture
def org(app):
    row = PartnerOrg(name="라운즈")
    db_session.add(row)
    db_session.commit()
    return row


def test_import_reads_both_brands_and_infers_calc_defaults():
    data = import_sheets(_html())
    assert data["brands"] == ["test", "other"]
    sheet = data["sheets"]["test"]
    items = _items(sheet)
    assert len(items) == 16  # 빈 줄 · 빈 짝 칸은 품목이 아니다
    assert [i["key"] for i in items.values()] == [f"r{n}" for n in range(1, 17)] and sheet["seq"] == 16
    assert (items["슬라이딩"]["role"], items["슬라이딩"]["kind"], items["슬라이딩"]["unit"]) == ("product", "ja", "자")
    assert items["서랍장 (3단)"]["kind"] == "fixed"
    assert items["주방 (상하부장) (1m 당)"]["kind"] == "meter"
    powder = items["단독 파우더장 (900 이하) / 조명 콘센트 포함"]
    assert powder["kind"] == "band" and powder["cond"] == {"dim": "width", "max": 900, "min": 601, "group": "단독 파우더장"}
    ep = items["측면 EP 마감 (폭 800mm 이상)"]
    assert ep["role"] == "option" and ep["cond"] == {"dim": "depth", "min": 801, "group": "측면 EP 마감"}
    assert items["넓이 추가 (100mm 당)"]["kind"] == "over"
    assert items["슬라이딩 거울 도어"]["unit"] == "짝" and items["피닉스바"]["pick_names"] == ["피닉스바"]
    assert items["TYPE A"]["pickable"] is False and items["여닫이 통 추가 (한통)"]["pickable"] is False
    assert sheet["categories"][0]["rows"][1]["cells"] == ["슬라이딩", 100000]  # 소수점 0 은 정수 금액으로
    other = _items(data["sheets"]["other"])["슬라이딩"]
    assert (other["name_col"], other["price_col"]) == (0, 1)  # 1cm 칸은 품목이 아니다


@pytest.mark.parametrize("html, needle", [
    ("", "골라"), ("<html><body>no data</body></html>", "찾지 못했"),
    ('<script id="data">{not json</script>', "깨져"), ('<script id="data">{"brands": {}}</script>', "브랜드"),
])
def test_import_rejects_files_without_price_data(html, needle):
    with pytest.raises(PriceListError) as exc:
        import_sheets(html)
    assert needle in exc.value.errors[0]


def test_reimport_keeps_keys_for_same_names_and_new_names_get_new_keys():
    first = import_sheets(_html())["sheets"]["test"]
    changed = copy.deepcopy(SOURCE)
    changed["brands"]["test"][1]["rows"].insert(0, ["내부 전신경", 50000])
    again = import_sheets(_html(changed), current=first)["sheets"]["test"]
    before, after = _items(first), _items(again)
    assert all(after[name]["key"] == before[name]["key"] for name in before)
    assert after["내부 전신경"]["key"] == "r17"


def test_clean_sheet_turns_typed_prices_into_won_and_blocks_bad_values():
    sheet = import_sheets(_html())["sheets"]["test"]
    sheet["categories"][1]["rows"][0]["cells"][1] = "12,000"
    assert clean_sheet(sheet)["categories"][1]["rows"][0]["cells"][1] == 12000
    bad = copy.deepcopy(sheet)
    bad["categories"][1]["rows"][0]["cells"][1] = "150,000~"
    bad["categories"][1]["rows"][1]["items"][0]["pick_names"] = ["슬라이딩"]
    bad["categories"][1]["rows"][1]["items"][0]["role"] = "product"
    bad["categories"][1]["rows"][0]["items"][0]["for_products"] = ["없는 제품"]
    with pytest.raises(PriceListError) as exc:
        clean_sheet(bad)
    text = " | ".join(exc.value.errors)
    assert "숫자가 아닌 값" in text and "여러 줄에 겹칩니다: 슬라이딩" in text and "없는 제품" in text


def test_band_group_may_share_one_pick_name():
    sheet = import_sheets(_html())["sheets"]["test"]
    for _c, row, item in iter_items(sheet):
        if item["kind"] == "band" and item["role"] == "option":
            item["pick_names"] = ["측면 마감판(EP)"]
    clean_sheet(sheet)  # 같은 구간 묶음은 한 이름(깊이로 줄을 고른다)


def test_save_first_and_next_version_snapshots_old_values(org):
    draft = import_sheets(_html())["sheets"]["test"]
    first = save_price_list(db_session, org.id, draft, label="11월판", effective_from="2026-11-01", base_id=None, user_id=None)
    db_session.commit()
    assert (first.version, first.status, first.effective_from) == (1, "ACTIVE", dt.date(2026, 11, 1))
    old_slide = _items(first.sheet)["슬라이딩"]
    edited = copy.deepcopy(first.sheet)
    edited["categories"][0]["rows"][1]["cells"][1] = 110000
    edited["categories"][1]["rows"].pop(0)  # 피닉스바 줄을 지운다
    second = save_price_list(db_session, org.id, edited, label="12월판", effective_from="2026-12-01",
                             base_id=first.id, user_id=None)
    db_session.commit()
    db_session.refresh(first)
    assert (second.version, second.status, first.status) == (2, "ACTIVE", "RETIRED")
    assert first.sheet["categories"][0]["rows"][1]["cells"][1] == 100000  # 옛 판 값은 그대로
    assert active_price_list(db_session, org.id).id == second.id
    retired = {r["key"]: r for r in second.sheet["retired"]}
    phoenix_key = _items(first.sheet)["피닉스바"]["key"]
    assert retired[phoenix_key]["name"] == "피닉스바" and retired[phoenix_key]["price"] == 10000
    group = calc_item(second.sheet, {"uid": "u", "title": "슬라이딩", "base_key": old_slide["key"],
                                     "spec_rows": [{"width": "3000"}], "lines": [{"key": phoenix_key, "qty": 2}]})
    assert [(line["name"], line["amount"]) for line in group["lines"]] == [("슬라이딩", 1100000), ("피닉스바", 20000)]


def test_save_refuses_stale_base_and_missing_fields(org):
    draft = import_sheets(_html())["sheets"]["test"]
    first = save_price_list(db_session, org.id, draft, label="11월판", effective_from="2026-11-01", base_id=None, user_id=None)
    db_session.commit()
    with pytest.raises(PriceListConflict):
        save_price_list(db_session, org.id, draft, label="또", effective_from="2026-11-02", base_id=None, user_id=None)
    db_session.rollback()
    for label, start in [("", "2026-11-02"), ("판", ""), ("판", "11월")]:
        with pytest.raises(PriceListError):
            save_price_list(db_session, org.id, draft, label=label, effective_from=start, base_id=first.id, user_id=None)
        db_session.rollback()
    assert db_session.query(PartnerPriceList).count() == 1
    assert active_price_list(db_session, org.id).id == first.id
