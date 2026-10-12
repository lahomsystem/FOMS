"""취소 품목(items[].cancel)은 생산·출고·일정·고객 안내·요약에서 빠진다 (DRAWING-PARTIAL-CONFIRM 4단계).

설계: docs/specs/2026-10-12-drawing-confirm-partial-cancel_SPEC.md §6. 금액(결제·정산)은
"표시만" 결정(§9-3)이라 여기서 바꾸지 않는다.
"""
from __future__ import annotations

from types import SimpleNamespace

KEEP = {"uid": "a" * 36, "product_name": "몰딩 여닫이장", "width": "2400", "quantity": "1",
        "construction_date": "2026-11-02", "measurement_date": "2026-10-20"}
GONE = {"uid": "b" * 36, "product_name": "보테가 슬라이딩장", "width": "1800", "quantity": "1",
        "construction_date": "2026-11-09", "measurement_date": "2026-10-27",
        "cancel": {"reason": "customer_change", "source": "drawing_confirm"}}


def _sd():
    return {"items": [dict(GONE), dict(KEEP)]}  # 취소 품목이 맨 앞 — 대표 품목이 바뀌는지 본다


def test_production_first_item_and_label_skip_cancelled():
    from foms.services.production_dashboard_display import _production_first_item, _production_product_label
    first, items = _production_first_item(_sd())
    assert first["product_name"] == "몰딩 여닫이장"
    assert _production_product_label(items) == "몰딩 여닫이장"


def test_shipment_visible_items_and_units_skip_cancelled():
    from foms.services.shipment_dashboard_helpers import order_spec_units, visible_items_for_dates
    order = SimpleNamespace(structured_data=_sd(), is_erp_order=True, construction_date=None)
    assert [it["product_name"] for it in visible_items_for_dates(order)] == ["몰딩 여닫이장"]
    only_keep = SimpleNamespace(structured_data={"items": [dict(KEEP)]}, is_erp_order=True)
    assert order_spec_units(SimpleNamespace(structured_data=_sd(), is_erp_order=True)) == order_spec_units(only_keep)


def test_packing_derivation_skips_cancelled_but_keeps_original_index_keys():
    from foms.api.shipment.packing import _derive_packing_items
    keys = {row["key"] for row in _derive_packing_items(_sd())}
    assert keys and all(k.startswith("item1_") for k in keys)


def test_alimtalk_product_list_skips_cancelled():
    from foms.services.kakao_alimtalk import build_variables
    text = build_variables(_sd())["#{품목내역}"]
    assert "몰딩 여닫이장" in text and "보테가" not in text


def test_channel_measure_items_block_skips_cancelled():
    from foms.services.channel_measure_message import _items_block
    out = _items_block("", _sd())
    assert "몰딩 여닫이장" in out and "보테가" not in out


def test_display_product_summary_skips_cancelled():
    from foms.services.erp_display import apply_erp_display_fields
    order = SimpleNamespace(structured_data=_sd(), is_erp_order=True, product="", address="",
                            customer_name="", phone="", measurement_date=None, measurement_time=None,
                            construction_date=None, manager_name="", status="RECEIVED")
    apply_erp_display_fields(order)
    assert order.product == "몰딩 여닫이장"


def test_construction_date_candidates_skip_cancelled():
    from foms.services.notifications.shipment_change import _current_construction_date
    assert _current_construction_date({"items": [dict(GONE)]}) == ""
    assert _current_construction_date({"items": [dict(GONE), dict(KEEP)]}) != ""


def test_order_copy_revives_items_and_drops_excluded_drawings():
    from foms.services.order_copy import _copy_structured_data
    import datetime
    sd = _sd()
    sd["flags"] = {"estimate_needs_update": True, "urgent": True}
    sd["drawing_excluded_files"] = [{"key": "x"}]
    original = SimpleNamespace(id=1, structured_data=sd)
    out = _copy_structured_data(original, datetime.datetime(2026, 10, 12))
    assert all("cancel" not in it for it in out["items"]) and len(out["items"]) == 2
    assert out["flags"] == {"urgent": True}
    assert "drawing_excluded_files" not in out
    assert "cancel" in sd["items"][0], "원본은 그대로"


def test_mobile_detail_rows_keep_cancelled_with_badge():
    from foms.services.erp_mobile_order_display import mobile_product_items
    rows = mobile_product_items(_sd())
    assert [r["title"] for r in rows] == ["보테가 슬라이딩장", "몰딩 여닫이장"]  # 상세는 줄을 지우지 않는다
    assert rows[0]["cancel_label"] == "취소 · 고객 변심" and rows[1]["cancel_label"] == ""
