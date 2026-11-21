"""생산 화면 품목 줄의 W×D×H — 주문 마법사 주문은 치수가 ``items[].spec_rows`` 에만 있다(2026-11-21 운영 흉내 시험에서 발견).

``_production_spec_display`` 가 품목 자체 칸(spec_width 등)만 읽어 마법사 주문은 '내 공정' 판 · 날짜 탭 · 찾기 탭 ·
파트 카드 · 옛 칸반 · 시공 대시보드에서 치수가 비었다. 작업 시트(``_prod_item_whd``)는 맞게 보였다.
규칙은 하나(``production_dashboard_display._whd_text`` · ``_spec_rows_whd``)를 생산 줄 글과 작업 시트가 같이 쓴다.
"""
from __future__ import annotations

import copy

from db import db_session
from foms.api.erp_order_draft import _draft_payload_to_structured
from foms.services.construction_dashboard_display import _workmode_display_fields
from foms.services.orders.structured_item_uid import ITEM_UID_KEY, ensure_item_uids
from foms.services.production.home_step_panel import _KEYS, production_home_step_panel
from foms.services.production.part_board import card_item_text
from foms.services.production_dashboard_display import (
    _production_spec_display,
    build_production_enriched_rows,
)
from foms.services.production_sheet_view import _prod_item_whd
from models import Order


# --------------------------------------------------------------------------- #
# ① 규칙
# --------------------------------------------------------------------------- #
def test_top_level_keys_unchanged():
    assert _production_spec_display({"spec_width": "2400", "spec_depth": "600", "spec_height": "2300"}) == "W2400 × D600 × H2300"
    assert _production_spec_display({"width": 1800, "height": "-", "depth": ""}) == "W1800"
    # 품목 자체 칸이 있으면 spec_rows 보다 먼저(지금 동작 그대로)
    item = {"spec_width": "900", "spec_rows": [{"spec_width": "1200", "spec_depth": "600", "spec_height": "2400"}]}
    assert _production_spec_display(item) == "W900"


def test_spec_string_fallback_unchanged():
    assert _production_spec_display({"spec": " 2400*600*2400 "}) == "2400*600*2400"
    assert _production_spec_display({}) == ""
    assert _production_spec_display(None) == ""


def test_spec_rows_only_single_row():
    item = {"product_name": "붙박이장", "spec_rows": [{"spec_width": "2740", "spec_depth": "700", "spec_height": "2330"}]}
    assert _production_spec_display(item) == "W2740 × D700 × H2330"


def test_spec_rows_short_keys():
    assert _production_spec_display({"spec_rows": [{"w": "1500", "d": "620", "h": "2100"}]}) == "W1500 × D620 × H2100"


def test_spec_rows_multiple_rows_join_like_sheet():
    item = {"spec_rows": [
        {"spec_width": "2400", "spec_depth": "600", "spec_height": "2400"},
        {"spec_width": "900", "spec_depth": "600", "spec_height": ""},
    ]}
    expected = "W2400 × D600 × H2400 / W900 × D600"
    assert _production_spec_display(item) == expected
    assert _prod_item_whd(item) == expected  # 작업 시트와 같은 글


def test_spec_rows_empty_or_garbage_rows():
    assert _production_spec_display({"spec_rows": []}) == ""
    assert _production_spec_display({"spec_rows": "W100"}) == ""
    garbage = {"spec_rows": [None, "x", 3, {}, {"spec_width": "", "spec_depth": "-", "spec_height": "  "},
                             {"spec_width": "1000"}]}
    assert _production_spec_display(garbage) == "W1000"
    # 줄이 다 비면 spec 원문으로 내려간다
    assert _production_spec_display({"spec_rows": [{"spec_width": ""}], "spec": "현장 실측"}) == "현장 실측"


def test_sheet_whd_unchanged():
    assert _prod_item_whd({"spec_width": "3100", "spec_depth": "500", "spec_height": "2300"}) == "W3100 × D500 × H2300"
    # 시트는 spec_rows 가 있으면 그것만 읽는다(지금 동작 그대로)
    assert _prod_item_whd({"spec_width": "1", "spec_rows": [{"w": "2"}]}) == "W2"
    assert _prod_item_whd({}) == ""


# --------------------------------------------------------------------------- #
# ② 화면 자료 — 마법사 저장 모양 그대로(_draft_payload_to_structured)
# --------------------------------------------------------------------------- #
_DRAFT = {
    "customer_name": "시험손님",
    "phone": "010-0000-0000",
    "address": "서울시 시험구 1",
    "items": [{
        "product_name": "붙박이장",
        "color": "그레이",
        "spec_rows": [
            {"spec_width": "2740", "spec_depth": "700", "spec_height": "2330"},
            {"spec_width": "900", "spec_depth": "700", "spec_height": "2330"},
        ],
    }],
}
_WHD = "W2740 × D700 × H2330 / W900 × D700 × H2330"


def _wizard_sd() -> dict:
    sd = _draft_payload_to_structured(copy.deepcopy(_DRAFT))
    item = sd["items"][0]
    assert not any(k in item for k in ("spec_width", "spec_depth", "spec_height", "spec"))  # 치수는 spec_rows 에만
    sd["workflow"]["stage"] = "PRODUCTION"
    return sd


def test_wizard_order_step_panel_and_kanban_show_whd(app):
    with app.app_context():
        sd = _wizard_sd()
        order = Order(received_date="2026-11-21", customer_name="시험손님", phone="010-0000-0000",
                      address="서울시 시험구 1", product="붙박이장", status="IN_PRODUCTION",
                      is_erp_order=True, structured_data=sd)
        db_session.add(order)
        db_session.commit()
        rows = build_production_enriched_rows([db_session.get(Order, order.id)], {})
        assert len(rows) == 1
        row = rows[0]
        assert row["v3_spec_display"] == _WHD  # 옛 칸반 · 날짜 탭 · 찾기 탭이 읽는 칸
        panel = production_home_step_panel(row, _KEYS[0], None)
        assert panel["sub"] == f"붙박이장 · {_WHD}"


def test_wizard_order_part_card_and_construction_show_whd(app):
    with app.app_context():
        sd = _wizard_sd()
    # 파트 카드: 도면이 품목에 이어지면 그 품목 치수를 직접 읽는다(_production_spec_display)
    ensure_item_uids(None, sd)
    name, spec = card_item_text(sd, {"item_uids": [sd["items"][0][ITEM_UID_KEY]]}, {})
    assert (name, spec) == ("붙박이장", _WHD)
    _, construction_spec = _workmode_display_fields(sd)
    assert construction_spec == _WHD
