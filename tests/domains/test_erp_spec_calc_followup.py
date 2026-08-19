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
# Batch 6: product_settings inline JS가 static 모듈로 이동 → JS 계약은 모듈에서 검사
PRODUCT_SETTINGS_JS = ROOT / "static/js/wdcalculator/product-settings.js"
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


def test_picker_assets_parse_no_premature_comment_close() -> None:
    """근본원인 회귀 가드: 블록 주석(/* … */) 안에 '*/' 시퀀스가 있으면 주석이 조기
    종료되어 SyntaxError(Unexpected token)로 모듈 전체가 죽는다(라이브 콘솔에서
    erp-spec-picker.js:10 'Unexpected token *'로 입증). CSS도 같은 원리로 .erp-calc-field
    position:relative가 무효화되어 5030px 세로 트리거를 만든다."""
    for path in (SPEC_PICKER_JS, SPEC_CALC_JS, SPEC_CALC_CSS):
        js = _read(path)
        # 정상적인 주석 종료는 한 줄에서 ' */'(닫기) 또는 '*/' 단독. 본문 중간 '*/'(앞에
        # 공백 없이 토큰이 붙은 형태, 예: 'wd-cat-*/')는 주석 조기 종료 위험 → 금지.
        for lineno, line in enumerate(js.splitlines(), start=1):
            idx = line.find("*/")
            if idx <= 0:
                continue  # 미존재 또는 줄 첫머리 닫기(' */' 정렬형은 idx>0이지만 앞이 공백)
            prev = line[idx - 1]
            assert prev in " \t", (
                f"{path.name}:{lineno} 주석 본문에 종료유발 '*/'가 붙어 있음: {line.strip()!r}"
            )


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
    gated = tpl.split("{% if flag_spec_picker %}", 1)[1]
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
    html = _read(PRODUCT_SETTINGS) + "\n" + _read(PRODUCT_SETTINGS_JS)
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
    assert "_buildCategoryOptionGroups(INTERNAL_CATEGORY)" in js
    assert "_currentCategoryOptionKeys(ctrl, INTERNAL_CATEGORY)" in js
    assert "_applyCategoryOptionSelection(row, ctrl, INTERNAL_CATEGORY, payloads)" in js
    assert "_parseCategoryOptionRows(row, 'internal', INTERNAL_CATEGORY)" in js
    assert 't.matches(\'[data-erp="internal"]\')' in js
    assert "_aggregateOptionRows" in js
    assert "title: '내부 선택'" in js
    assert "combined.join(', ')" in js


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
    assert "e.price >= 0" in js
    assert "selectedKeys" in js
    assert "combined.join(', ')" in js
    # 검색 + 체크박스(다중) 피커 = wdcalculator 방식
    picker = _read(SPEC_PICKER_JS)
    assert "wd-madd-search-input" in picker
    assert "wd-madd-opt__cb" in picker


def test_option_duplicate_tokens_are_aggregated_as_quantity() -> None:
    """B, B처럼 같은 옵션을 반복 입력하면 가격엔진 quantity=2로 전달하고 삭제 시 재집계한다."""
    js = _read(SPEC_CALC_JS)
    assert "function _optionTokenCounts" in js
    assert "counts.set(e.token, (counts.get(e.token) || 0) + 1)" in js
    assert "function _aggregateOptionRows" in js
    assert "byName.get(row.name).quantity += qty" in js
    assert "var n = counts.get(p.token) || 1" in js
    assert "_aggregateOptionRows(\n      _parseCategoryOptionRows(row, 'internal', INTERNAL_CATEGORY)" in js


# ----- R5: 좁은 코호트에서 편집 카드 폭 최대화 -----
def test_edit_card_full_width_in_mobile_cohort() -> None:
    html = _read(EDIT_BODY_TPL)
    assert "erp-edit-col" in html
    css = _read(FORM_FIELD_CSS)
    assert ".erp-edit-col" in css
    assert "max-width: 100%" in css  # 코호트(≤991.98px) 풀폭화


def test_mobile_spec_aux_fields_stack_label_above_input() -> None:
    """모바일 스펙 보조 필드(내부/색상/손잡이/옵션/기타)는 라벨+입력 2줄로 폭을 확보한다."""
    css = _read(FORM_FIELD_CSS)
    inline_rule = css.split("body.erp-mobile-v2-layout .erp-order-mobile-form .erp-mobile-inline", 1)[1].split("}", 1)[0]
    assert "#erp-items .erp-mobile-full-row" not in inline_rule
    assert "#erp-items .erp-mobile-full-row {\n    display: block;" in css
    assert "#erp-items .erp-mobile-full-row > .form-label" in css
    assert "display: block;\n    margin: 0 0 2px;" in css


# ----- R7: 주문상세 타이포 밀도 벤치마크 -----
def test_typography_benchmarks_order_detail_density() -> None:
    css = _read(FORM_FIELD_CSS)
    # 라벨 13px (주문상세 .foms-kv-row 기준), 입력 16px(iOS 포커스 줌 방지)
    assert "font-size: 13px" in css
    assert "max(16px" in css


# ----- 캐시버스팅 회귀 가드(근본원인): 통합 진입점은 버전 쿼리 필수 -----
def test_shared_integration_script_is_cache_busted() -> None:
    """erp-order-shared.js가 enhanceItemRow를 호출하는 통합 진입점인데, <script>에
    ?v= 버전이 없으면 과거 immutable 캐시본이 영구히 stale로 남아 spec-calc가 통째로
    dormant가 된다(라이브 콘솔에서 'flag ON·스크립트 로드됨'인데 트리거 전무로 입증).
    버전 쿼리 부재 재발을 구조적으로 차단한다."""
    tpl = _read(ORDER_JS_TPL)
    assert "js/orders/erp-order-shared.js') }}?v=" in tpl
    # spec-calc 자산도 동일하게 버전으로 신선화(휴면 호출자 갱신과 한 묶음)
    assert "js/orders/erp-spec-calc.js') }}?v=" in tpl
    assert "js/orders/erp-spec-picker.js') }}?v=" in tpl


def test_form_field_css_chain_cache_busted_for_redesign() -> None:
    """R5/R7(폰트·폭)은 foms-form-field.css에 있고, 편집 페이지는 mobile-surfaces
    번들의 @import로 이를 받는다. 내용만 바꾸고 버전을 안 올리면 stale 캐시로 미반영되므로,
    @import 버전(번들 내부)과 외곽 <link> 버전이 함께 신선해야 한다."""
    surfaces = _read(ROOT / "static/css/foundation/foms-mobile-surfaces.css")
    layout_head = _read(ROOT / "templates/partials/shared/layout_head.html")
    assert "../components/foms-form-field.css?v=20260723i" in surfaces
    assert "foms-mobile-surfaces.css') }}?v=20260819a" in layout_head


def test_spec_calc_self_heals_rows_created_before_module_load() -> None:
    """fragment/full-page 로드 순서 차이로 erp-order-shared.js가 먼저 row를 만들면
    enhanceItemRow 호출이 skip될 수 있다. spec-calc 모듈 로드 후 기존 row를 재스캔해
    ▾ 트리거가 반드시 붙도록 한다."""
    js = _read(SPEC_CALC_JS)
    assert "function _enhanceExistingRows(root)" in js
    assert "querySelectorAll('#erp-items .erp-item-row')" in js
    assert "ErpSpecCalc.enhanceItemRow(row, {})" in js
    assert "foms:main-content-swapped" in js


def test_primary_section_and_open_item_purple_highlight_restored() -> None:
    """사용자 요청: 61d4cd64에서 neutral로 바꾼 primary/open item 강조는 원상 복귀한다."""
    css = _read(FORM_FIELD_CSS)
    assert "box-shadow: 0 0 0 1px var(--foms-interactive-primary, #4f46e5), 0 1px 3px rgba(79, 70, 229, 0.1);" in css

    selector = "body.erp-mobile-v2-layout .erp-order-mobile-form #erp-items .erp-item-row.is-open"
    open_rule = css.split(selector, 1)[1].split("}", 1)[0]
    assert "var(--foms-interactive-primary, #4f46e5)" in open_rule
    assert "rgba(79, 70, 229, 0.12)" in open_rule
