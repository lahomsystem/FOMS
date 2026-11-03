"""견적 계산기 목록 보이는 차례 — 한글(ㄱㄴㄷ) 먼저, 그다음 영문(abc), 숫자는 수로 견줌(사장님 11-03)."""

from __future__ import annotations

import copy

from foms.services.wdcalculator.display_order import name_key, sorted_by_name, sorted_categories


def _names(rows):
    return [row["name"] for row in rows]


def test_korean_comes_before_english_then_digits():
    rows = [{"name": n} for n in ("beta", "다리", "Alpha", "가방", "9칸", "나무", "")]
    assert _names(sorted_by_name(rows)) == ["가방", "나무", "다리", "Alpha", "beta", "9칸", ""]


def test_numbers_inside_names_compare_as_numbers():
    rows = [{"name": n} for n in ("폭 1200mm", "폭 300mm", "폭 601mm")]
    assert _names(sorted_by_name(rows)) == ["폭 300mm", "폭 601mm", "폭 1200mm"]


def test_type_letters_follow_alphabet_and_korean_option_comes_first():
    rows = [{"name": n} for n in ("TYPE K", "TYPE B", "상담", "TYPE A")]
    assert _names(sorted_by_name(rows)) == ["상담", "TYPE A", "TYPE B", "TYPE K"]


def test_categories_and_their_options_are_sorted_without_touching_input():
    categories = [
        {"id": 2, "name": "Mirror", "options": [{"id": 1, "name": "b"}, {"id": 2, "name": "a"}]},
        {"id": 1, "name": "내부구성", "options": [{"id": 3, "name": "TYPE J"}, {"id": 4, "name": "TYPE B"}]},
    ]
    before = copy.deepcopy(categories)
    out = sorted_categories(categories)
    assert [c["name"] for c in out] == ["내부구성", "Mirror"]
    assert _names(out[0]["options"]) == ["TYPE B", "TYPE J"]
    assert _names(out[1]["options"]) == ["a", "b"]
    assert categories == before  # 저장 차례는 그대로(대조군)


def test_non_dict_rows_go_last_and_key_is_stable_for_none():
    assert sorted_by_name([None, {"name": "가"}]) == [{"name": "가"}, None]
    assert name_key(None) == name_key("")


def test_settings_page_and_categories_api_show_korean_first(wdcalculator_settings_env, login):
    client = login
    for name in ("Zeta 옵션", "가나 옵션"):
        payload = {"name": name, "options": [{"name": "TYPE B", "price": 0}, {"name": "기본", "price": 0}]}
        assert client.post("/api/wdcalculator/additional-options/categories", json=payload).get_json()["success"]

    body = client.get("/wdcalculator/product-settings").get_data(as_text=True)
    assert body.index("가나 옵션") < body.index("Zeta 옵션")

    listed = client.get("/api/wdcalculator/additional-options/categories").get_json()["categories"]
    names = [c["name"] for c in listed]
    assert names.index("가나 옵션") < names.index("Zeta 옵션")
    zeta = next(c for c in listed if c["name"] == "Zeta 옵션")
    assert _names(zeta["options"]) == ["기본", "TYPE B"]
    assert all(o["price"] == 0 for o in zeta["options"])  # 0원 옵션도 저장된다(D136)
