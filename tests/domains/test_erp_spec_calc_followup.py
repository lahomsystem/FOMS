"""후속 요구 1~6: ERP 현장 스펙 즉시견적 UX/동작 보강 계약(정적).

- req1/2: 스택형 드롭다운 제거 → 기존 입력칸을 datalist 콤보박스(1칸)로 강화.
          모바일 textarea 칸은 강화 시점에만 단일행 input으로 치환.
- req3:  추가옵션 가격 0원 등록 허용(프런트 검증 + 백엔드 None만 거부).
- req4:  내부 칸 값은 추가옵션 '내부구성' 카테고리에서만.
- req5:  제품 선택 시 손잡이 자동입력(슬라이딩/피닉스바/푸쉬).
- req6:  옵션 다중선택 → 콤마 누적 표기 + 가격 합산.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SPEC_CALC_JS = ROOT / "static/js/orders/erp-spec-calc.js"
SPEC_CALC_CSS = ROOT / "static/css/orders/erp-spec-calc.css"
PRODUCT_SETTINGS = ROOT / "templates/wdcalculator/product_settings.html"
WDC_BLUEPRINT = ROOT / "foms/api/wdcalculator/blueprint.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ----- req1/2: 단일칸 datalist 콤보박스 -----
def test_spec_fields_use_datalist_combobox_single_box() -> None:
    js = _read(SPEC_CALC_JS)
    assert "_attachDatalist" in js
    assert "createElement('datalist')" in js
    assert "setAttribute('list'" in js
    assert "erp-calc-combo" in js


def test_mobile_textarea_converted_to_single_line_input() -> None:
    js = _read(SPEC_CALC_JS)
    # 모바일 textarea → 값/속성 보존 단일행 input 치환
    assert "_ensureInputControl" in js
    assert "replaceChild" in js


def test_legacy_stacked_selects_removed() -> None:
    """더 이상 별도 select를 입력칸 위에 쌓지 않는다(모바일 정리 핵심)."""
    js = _read(SPEC_CALC_JS)
    assert "erp-calc-product-select" not in js
    assert "erp-calc-preset-select" not in js
    assert "erp-calc-option-select" not in js  # 옵션은 -adder로 대체


def test_combo_affordance_styled() -> None:
    css = _read(SPEC_CALC_CSS)
    assert ".erp-calc-combo" in css


# ----- req3: 0원 옵션 등록 허용 -----
def test_product_settings_allows_zero_price_option() -> None:
    html = _read(PRODUCT_SETTINGS)
    assert "optionPrice < 0" in html       # 음수만 거부
    assert "optionPrice <= 0" not in html  # 0원 거부 로직 제거


def test_backend_option_save_rejects_only_missing_price() -> None:
    src = _read(WDC_BLUEPRINT)
    # 가격 미입력(None)만 거부 — 0은 허용
    assert "data.get('price') is None" in src


# ----- req4: 내부 = '내부구성' 카테고리 -----
def test_internal_field_sourced_from_internal_composition_category() -> None:
    js = _read(SPEC_CALC_JS)
    assert "INTERNAL_CATEGORY" in js
    assert "내부구성" in js
    assert "_optionsByCategory" in js


# ----- req5: 제품 → 손잡이 자동입력 -----
def test_handle_autofill_from_product_name() -> None:
    js = _read(SPEC_CALC_JS)
    assert "_autoFillHandle" in js
    for handle in ("슬라이딩", "피닉스바", "푸쉬"):
        assert handle in js


# ----- req6: 옵션 다중선택 + 콤마 + 합산 -----
def test_option_multi_select_comma_and_sum() -> None:
    js = _read(SPEC_CALC_JS)
    assert "erp-calc-option-adder" in js
    assert "_parseOptionRows" in js
    assert "_onOptionAdderPick" in js
    assert "tokens.join(', ')" in js
    # 카테고리별 그룹핑(가독성)
    assert "optgroup" in js
