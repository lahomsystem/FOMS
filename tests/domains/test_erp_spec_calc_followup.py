"""후속 요구 + UX 재설계: ERP 현장 스펙 즉시견적 계약(정적).

재설계 핵심: 모바일에서 열리지 않는 native <datalist>를 폐기하고, 앱에 이미 검증된
피커 패턴(category-picker=단일, multi-add-picker=다중)을 재사용하는 ErpSpecPicker +
입력칸 우측 ▾ 트리거로 교체한다. 기존 입력 컨트롤(autosize textarea/제품명 input)은
그대로 보존(직접입력·자동높이 유지). 카드 풀폭화 + 주문상세 타이포 벤치마킹.

- req1/2: ▾ 트리거 + ErpSpecPicker(단일/다중). datalist 제거, textarea 보존(autosize=R4).
- req3:   추가옵션 0원 등록 허용(프런트 검증 + 백엔드 None만 거부).
- req4:   내부 칸 값 = 추가옵션 '내부구성' 카테고리.
- req5:   제품 선택 시 손잡이 자동입력(슬라이딩/피닉스바/푸쉬).
- req6:   옵션 다중선택(검색+체크박스, wdcalculator 방식) → 콤마 누적 + 가격 합산.
- R5:     좁은 코호트 편집 카드 풀폭화 + 좌우 패딩 축소.
- R7:     주문상세(.foms-kv-row) 타이포 벤치마크(라벨 13px / 입력 16px iOS 줌가드).
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SPEC_CALC_JS = ROOT / "static/js/orders/erp-spec-calc.js"
SPEC_PICKER_JS = ROOT / "static/js/orders/erp-spec-picker.js"
SPEC_CALC_CSS = ROOT / "static/css/orders/erp-spec-calc.css"
ORDER_JS_TPL = ROOT / "templates/orders/partials/erp_order_js.html"
EDIT_BODY_TPL = ROOT / "templates/orders/partials/edit_order_body.html"
FORM_FIELD_CSS = ROOT / "static/css/components/foms-form-field.css"
PRODUCT_SETTINGS = ROOT / "templates/wdcalculator/product_settings.html"
WDC_BLUEPRINT = ROOT / "foms/api/wdcalculator/blueprint.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ----- req1/2: ▾ 트리거 + 피커(단일/다중), native datalist 폐기 -----
def test_spec_fields_use_trigger_and_picker_not_datalist() -> None:
    js = _read(SPEC_CALC_JS)
    assert "_attachTrigger" in js
    assert "erp-calc-trigger" in js
    assert "ErpSpecPicker.openSingle" in js
    assert "ErpSpecPicker.openMulti" in js
    # native datalist 흔적 제거(모바일 미동작이 R1의 근본 원인)
    assert "createElement('datalist')" not in js
    assert "_attachDatalist" not in js
    assert "erp-calc-combo" not in js


def test_picker_module_exists_and_reuses_validated_patterns() -> None:
    js = _read(SPEC_PICKER_JS)
    assert "window.ErpSpecPicker" in js
    assert "openSingle" in js and "openMulti" in js
    # 단일 바인딩 가드(G4)
    assert "__erpSpecPickerBound" in js
    # 검증된 WDC 피커 CSS 클래스 재사용(룩앤필 통일)
    assert "wd-cat-" in js   # category-picker(단일)
    assert "wd-madd-" in js  # multi-add-picker(다중)
    # 데스크톱 드롭다운 / 모바일 바텀시트
    assert "wd-cat-panel--sheet" in js
    assert "wd-cat-panel--dropdown" in js


def test_picker_assets_loaded_under_flag_gate() -> None:
    tpl = _read(ORDER_JS_TPL)
    gated = tpl.split("{% if flag_spec_calc %}", 1)[1]
    assert "css/wdcalculator/category-picker.css" in gated
    assert "css/wdcalculator/multi-add-picker.css" in gated
    assert "js/orders/erp-spec-picker.js" in gated


# ----- R4: autosize 보존(textarea를 input으로 치환하지 않음) -----
def test_autosize_textarea_preserved_no_input_conversion() -> None:
    js = _read(SPEC_CALC_JS)
    assert "_ensureInputControl" not in js
    assert "replaceChild" not in js
    assert "erp-calc-converted" not in js
    # autosize/타이포 훅 클래스(.erp-flex-textarea)가 폼필드 CSS에 존재(보존 전제)
    assert "erp-flex-textarea" in _read(FORM_FIELD_CSS)


def test_trigger_affordance_styled_without_datalist_arrow() -> None:
    css = _read(SPEC_CALC_CSS)
    assert ".erp-calc-trigger" in css
    assert ".erp-calc-field" in css
    assert ".erp-calc-combo" not in css  # datalist 화살표 스타일 제거


def test_legacy_stacked_controls_removed() -> None:
    """더 이상 입력칸 위에 별도 select/adder를 쌓지 않는다(모바일 정리 핵심)."""
    js = _read(SPEC_CALC_JS)
    assert "erp-calc-product-select" not in js
    assert "erp-calc-preset-select" not in js
    assert "erp-calc-option-select" not in js
    assert "erp-calc-option-adder" not in js  # adder도 다중 피커로 대체


# ----- req3: 0원 옵션 등록 허용 -----
def test_product_settings_allows_zero_price_option() -> None:
    html = _read(PRODUCT_SETTINGS)
    assert "optionPrice < 0" in html       # 음수만 거부
    assert "optionPrice <= 0" not in html  # 0원 거부 로직 제거


def test_backend_option_save_rejects_only_missing_price() -> None:
    # 가격 미입력(None)만 거부 — 0은 허용
    assert "data.get('price') is None" in _read(WDC_BLUEPRINT)


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


# ----- req6: 옵션 다중선택 + 콤마 + 합산 (wdcalculator 다중 입력 방식) -----
def test_option_multi_select_comma_and_sum() -> None:
    js = _read(SPEC_CALC_JS)
    assert "_buildOptionGroups" in js
    assert "_parseOptionRows" in js
    assert "_applyOptionSelection" in js
    assert "selectedKeys" in js
    assert "combined.join(', ')" in js
    # 검색 + 체크박스(다중) 피커 = wdcalculator 방식
    picker = _read(SPEC_PICKER_JS)
    assert "wd-madd-search-input" in picker
    assert "wd-madd-opt__cb" in picker


# ----- R5: 좁은 코호트에서 편집 카드 폭 최대화 -----
def test_edit_card_full_width_in_mobile_cohort() -> None:
    html = _read(EDIT_BODY_TPL)
    assert "erp-edit-col" in html
    css = _read(FORM_FIELD_CSS)
    assert ".erp-edit-col" in css
    assert "max-width: 100%" in css  # 코호트(≤991.98px) 풀폭화


# ----- R7: 주문상세 타이포 밀도 벤치마크 -----
def test_typography_benchmarks_order_detail_density() -> None:
    css = _read(FORM_FIELD_CSS)
    # 라벨 13px (주문상세 .foms-kv-row 기준), 입력 16px(iOS 포커스 줌 방지)
    assert "font-size: 13px" in css
    assert "max(16px" in css
