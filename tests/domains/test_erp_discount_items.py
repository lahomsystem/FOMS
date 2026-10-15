"""할인 항목 줄(payment.discounts) — 서버 정규화·projection·화면 배선 계약."""

from __future__ import annotations

from pathlib import Path

from foms.services.orders.discount_items import (
    MAX_DISCOUNT_ITEMS,
    clean_discount_items,
    normalize_payment_discounts,
)
from foms.services.orders.structured_form_projection import project_structured_form

ROOT = Path(__file__).resolve().parents[2]


def test_clean_drops_zero_rows_and_defaults_label() -> None:
    rows = clean_discount_items([
        {"label": " 오픈 특가 ", "amount": "100,000원"},
        {"label": "", "amount": 5000},
        {"label": "빈 줄", "amount": 0},
        "깨진 값",
        {"label": "음수", "amount": -3},
    ])
    assert rows == [
        {"label": "오픈 특가", "amount": 100000},
        {"label": "할인", "amount": 5000},
    ]


def test_clean_caps_row_count() -> None:
    rows = clean_discount_items([{"label": str(i), "amount": 1} for i in range(50)])
    assert len(rows) == MAX_DISCOUNT_ITEMS


def test_normalize_overrides_client_total_with_list_sum() -> None:
    sd = {"payment": {"discount": 999, "discounts": [
        {"label": "a", "amount": 100000}, {"label": "b", "amount": 50000}]}}
    normalize_payment_discounts(sd)
    assert sd["payment"]["discount"] == 150000


def test_legacy_order_without_list_is_untouched() -> None:
    sd = {"payment": {"discount": 30000}}
    normalize_payment_discounts(sd, {"payment": {"discount": 30000}})
    assert sd["payment"] == {"discount": 30000}


def test_screen_without_list_keeps_saved_list_when_total_matches() -> None:
    """태블릿처럼 목록을 모르는 화면이 합계를 그대로 보내면 저장된 목록이 살아남는다."""
    old = {"payment": {"discount": 150000, "discounts": [
        {"label": "a", "amount": 100000}, {"label": "b", "amount": 50000}]}}
    sd = {"payment": {"discount": 150000}}
    normalize_payment_discounts(sd, old)
    assert [r["label"] for r in sd["payment"]["discounts"]] == ["a", "b"]


def test_screen_without_list_changing_total_drops_list() -> None:
    old = {"payment": {"discount": 150000, "discounts": [{"label": "a", "amount": 150000}]}}
    sd = {"payment": {"discount": 70000}}
    normalize_payment_discounts(sd, old)
    assert "discounts" not in sd["payment"]
    assert sd["payment"]["discount"] == 70000


def test_projection_balance_uses_list_sum() -> None:
    sd = {
        "items": [{"price": 1000000}],
        "payment": {"deposit": 200000, "discount": 0, "discounts": [
            {"label": "지인 할인", "amount": 50000}, {"label": "현장 할인", "amount": 30000}]},
    }
    project_structured_form({}, sd)
    assert sd["payment"]["discount"] == 80000
    assert sd["totals"]["discount_amount"] == 80000
    assert sd["totals"]["balance_amount"] == 1000000 - 200000 - 80000


def test_templates_wire_discount_list_on_pc_and_mobile() -> None:
    for rel in (
        "templates/orders/partials/erp_order_tab.html",
        "templates/orders/partials/erp_order_tab_mobile.html",
    ):
        html = (ROOT / rel).read_text(encoding="utf-8")
        assert 'id="erp-discount-list"' in html, rel
        assert 'id="erp-discount-add"' in html, rel
        # 기존 잔금 계산은 숨은 합계 칸을 읽는다.
        assert '<input type="hidden" id="erp-discount-amount"' in html, rel
    js_partial = (ROOT / "templates/orders/partials/erp_order_js.html").read_text(encoding="utf-8")
    # 공용 스크립트보다 먼저 로드돼야 불러오기 때 erpSetDiscountItems 가 있다.
    assert js_partial.index("erp-discount-items.js") < js_partial.index("erp-order-shared.js")


def test_shared_js_saves_and_loads_discount_list() -> None:
    shared = (ROOT / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")
    assert "discounts: window.erpGetDiscountItems()" in shared
    assert "window.erpSetDiscountItems(paymentData.discounts, paymentData.discount)" in shared
    assert "discounts: Array.isArray(pay.discounts) ? pay.discounts : null" in shared
    autosave = (ROOT / "static/js/orders/erp-order-autosave.js").read_text(encoding="utf-8")
    assert "window.erpSetDiscountItems(payment.discounts, payment.discount)" in autosave
