"""ERP '추가 입력'(extra_input)의 모바일 주문 상세 노출 계약."""

from __future__ import annotations

from pathlib import Path

from foms.services import erp_mobile_order_display as display

ROOT = Path(__file__).resolve().parents[2]


def test_mobile_product_items_exposes_extra_input() -> None:
    """항목 extra_input 이 모바일 KV 행 값으로 노출되고, 없으면 '-' 로 떨어진다."""
    sd = {
        "items": [
            {"product_name": "A", "extra_input": "  현장 특이사항\n2층 계단 좁음  "},
            {"product_name": "B"},
        ]
    }
    rows = display.mobile_product_items(sd)
    assert rows[0]["extra_input"] == "현장 특이사항\n2층 계단 좁음"
    assert rows[1]["extra_input"] == "-"


def test_mobile_detail_partial_renders_extra_input_row() -> None:
    """모바일 v2 상세 파셜이 추가입력 KV 행을 그리고, 줄바꿈 보존 클래스를 쓴다."""
    partial = (
        ROOT / "templates" / "orders" / "partials" / "order_detail_mobile_v2.html"
    ).read_text(encoding="utf-8")
    assert "item.extra_input" in partial
    assert "'추가입력'" in partial
    assert "'pre_line': True" in partial

    macro = (ROOT / "templates" / "macros" / "foms_kv.html").read_text(encoding="utf-8")
    assert "pre_line=row.pre_line|default(false)" in macro
    assert "foms-kv-row__text--pre" in macro

    css = (
        ROOT / "static" / "css" / "components" / "foms-kv-row.css"
    ).read_text(encoding="utf-8")
    assert ".foms-kv-row__text--pre" in css
    assert "white-space: pre-line" in css
def test_v3_shell_css_carries_pre_line_rule() -> None:
    """v3 셸은 foms-mobile-surfaces 번들을 로드하지 않으므로 줄바꿈 규칙이 v3 CSS 에도 있어야 한다."""
    v3 = (ROOT / "static" / "css" / "v3" / "foms-mobile-v3.css").read_text(encoding="utf-8")
    assert ".foms-kv-row__text--pre" in v3
    assert "white-space: pre-line" in v3

    layout_head = (
        ROOT / "templates" / "partials" / "shared" / "layout_head.html"
    ).read_text(encoding="utf-8")
    assert "css/v3/foms-mobile-v3.css') }}?v=20260826a" in layout_head
