"""WD 계산기 엔진 v2 확장(E1~E5) 구조 계약.

E1: MINE(직접) 행 제품명 필드 + 저장 왕복(compData 보존)
E3: '직접'→'CUSTOM', '추가금 추가'→'직접입력' 리네임
E4: 행별 직접입력 표기에서 '추가금' 접미사 제거(이름 있을 때)
E5: 견적 계산 버튼 전 플랫폼 삭제(계산은 전 입력 경로 자동)
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRIMARY = (ROOT / "static/js/wdcalculator/primary-form.js").read_text(encoding="utf-8")
PRICING = (ROOT / "static/js/wdcalculator/pricing-core.js").read_text(encoding="utf-8")
MOBILE = (ROOT / "static/js/wdcalculator/mobile-enhance.js").read_text(encoding="utf-8")
BODY = (ROOT / "templates/wdcalculator/partials/wdcalculator_body.html").read_text(encoding="utf-8")
SHARED = (ROOT / "static/js/wdcalculator/shared.js").read_text(encoding="utf-8")
LIFECYCLE = (ROOT / "static/js/wdcalculator/estimate-lifecycle.js").read_text(encoding="utf-8")
SETTINGS_HTML = (ROOT / "templates/wdcalculator/product_settings.html").read_text(encoding="utf-8")


def test_e1_manual_name_field_rendered_and_collected():
    assert PRIMARY.count("base-manual-name") >= 2  # 템플릿 렌더 + 수집
    assert "manualName" in PRIMARY


def test_e1_manual_name_survives_pricing_normalization():
    # compData 재구성(1m·30cm·폴백)에서 manualName 보존
    assert PRICING.count("manualName") >= 3


def test_e3_mode_button_renamed_to_custom():
    # 모드 라벨 SSOT: 커스텀 (레거시 CUSTOM/MINE 문자열 금지)
    assert 'data-mode="manual">커스텀<' in PRIMARY
    assert 'data-mode="manual">CUSTOM<' not in PRIMARY
    assert 'data-mode="manual">MINE<' not in PRIMARY


def test_base_mode_select_ssot():
    assert "base-mode-select" in PRIMARY
    assert ">제품선택<" in PRIMARY
    assert ">커스텀<" in PRIMARY
    assert '>직접</option>' in PRIMARY or ">직접<" in PRIMARY
    assert "base-mode-btn-hooks" in PRIMARY
    assert "btn-group w-100" not in PRIMARY.split("renderBaseComponentRow")[1].split("function ensureBaseComponentsUI")[0]


def test_t4_direct_mode_three_buttons():
    # 숨김 hook 버튼: tablet/legacy click 위임용 — 라벨은 select와 동일
    for pin in (
        'data-mode="select">제품선택<',
        'data-mode="manual">커스텀<',
        'data-mode="direct">직접<',
    ):
        assert pin in PRIMARY, pin


def test_apply_base_mode_extracted():
    assert "function applyBaseMode(rowEl, newMode)" in PRIMARY
    assert "applyBaseMode(rowEl, modeBtn.dataset.mode)" in PRIMARY
    assert 'e.target.classList.contains("base-mode-select")' in PRIMARY


def test_direct_mode_ensures_one_fee_input_row():
    # 직접 선택 시 ＋직접입력 클릭 없이 입력란 1행 즉시 노출
    assert "function ensureDirectFeeInputRow(rowEl)" in PRIMARY
    assert 'if (newMode === "direct")' in PRIMARY
    assert "ensureDirectFeeInputRow(rowEl)" in PRIMARY


def test_leave_direct_clears_empty_fee_rows():
    # 직접 → 제품선택/커스텀 전환 시 빈 fee 입력칸 제거
    assert "function clearEmptyAdditionalFeeRows(rowEl)" in PRIMARY
    assert "clearEmptyAdditionalFeeRows(rowEl)" in PRIMARY


def test_mobile_manual_name_full_width_guard():
    mobile = (ROOT / "static/css/wdcalculator/mobile.css").read_text(encoding="utf-8")
    stack = mobile.split("wd-field-stack: Field Form vertical stack marker")[1].split("직접 fee")[0]
    assert "base-manual-area > .mb-2" in stack
    assert ".base-manual-name" in stack
    assert "width: 100%" in stack


def test_wd_line_container_query_primitive():
    line = (ROOT / "static/css/wdcalculator/wd-line.css").read_text(encoding="utf-8")
    calc = (ROOT / "templates/wdcalculator/calculator.html").read_text(encoding="utf-8")
    assert "container-name: wd-line" in line
    assert "@container wd-line" in line
    assert "--wd-line-touch-h" in line
    assert "wd-line.css" in calc
    assert "wd-line.css') }}?v=20260723a" in calc or "wd-line.css') }}?v=" in calc


def test_t4_direct_mode_serializes_null_product():
    # direct 행은 fees-only — 숨은 select 잔존값 직렬화 금지(제품가 혼입·mode 클로버 방지)
    assert 'mode === "direct"' in PRIMARY


def test_t5_comma_helpers_and_delegated_formatter():
    # 공용 헬퍼 + 문서 위임 리스너 1개(싱글톤 가드)
    assert "wdcParseAmount" in SHARED
    assert "wdcFormatAmountInput" in SHARED
    assert "__WDC_AMOUNT_COMMA_BOUND" in SHARED
    # W(mm) 는 콤마 자동포맷 제외(복합식 구분자 예약)
    assert ".base-width-input" not in SHARED.split("WDC_AMOUNT_INPUT_SELECTOR")[1].split("].join")[0]


def test_t5_comma_tolerant_parsing():
    # 콤마 입력 시 NaN/오파싱 나던 경로들의 strip 내성
    assert PRICING.count('replace(/,/g, "")') >= 1  # shipping (calculateTotalEstimates)
    assert LIFECYCLE.count('replace(/,/g, "")') >= 1  # shipping (readShippingState)
    assert PRIMARY.count("parsePrice(") >= 5  # fee·price30·price1m·자동1cm×2 (+옵션 기존)
    assert 'replace(/,/g, "")' in PRIMARY  # getCouponValue parseInt strip


def test_t5_amount_inputs_converted_to_text():
    # type="number" 는 콤마 표기 불가 → text + inputmode=numeric 전환
    assert 'type="number"' not in BODY
    assert 'id="globalCouponValue"' in BODY and 'inputmode="numeric"' in BODY
    assert 'type="number"' not in SETTINGS_HTML
    # JS 렌더 금액 입력도 전환(콤마 표시 필수)
    assert 'type="number" class="form-control form-control-sm base-manual-price30' not in PRIMARY
    assert 'type="number" class="form-control form-control-sm base-additional-fee-amount' not in PRIMARY


def test_e3_fee_button_renamed():
    assert "추가 항목" in PRIMARY  # fee section label
    assert "직접입력" in PRIMARY  # base-add-fee-btn 라벨
    assert "추가금 추가" not in PRIMARY


def test_e4_fee_suffix_removed_when_named():
    # 이름 있으면 이름만, 이름 없을 때만 '추가금' 폴백
    assert 'name + " " :' not in PRICING or "추가금 " in PRICING
    assert PRICING.count('feeName + "추가금') == 0
    assert PRICING.count('feeNameA + "추가금') == 0


def test_e5_calculate_button_removed_from_template():
    assert "calculateBtn" not in BODY


def test_e5_binding_null_guard_kept():
    # 버튼 부재 시 무해해야 함 — 가드 존치 확인
    assert "if (!calculateBtn)" in PRIMARY


def test_mobile_manual_name_fallback():
    assert MOBILE.count("manualName") >= 2  # 1m·30cm 분기


def test_mobile_mode_segment_toolbar_contract():
    """모바일 툴바: 세그먼트 클래스 + select 숨김 클래스 + buildBaseToolbar 존재."""
    assert "function buildBaseToolbar" in MOBILE
    assert "wd-bc-mode-seg" in MOBILE
    assert "wd-bc-mode-select-hidden" in MOBILE
    assert "base-mode-btn" in MOBILE


def test_mobile_field_form_stack_css_contract():
    css = (ROOT / "static/css/wdcalculator/mobile.css").read_text(encoding="utf-8")
    assert ".wd-bc-mode-seg" in css
    assert ".wd-bc-mode-select-hidden" in css
    assert "wd-field-price" in css or "base-manual-price30" in css
    # 한줄 압착(contents로 30cm|1cm|W) 대신 전폭 스택 마커
    assert "wd-field-stack" in css
    assert "min-height: 48px" in css
    assert "flex-direction: column" in css
    assert "base-manual-area" in css
    # Kill regression of one-line squeeze via display:contents
    assert "display: contents !important" not in css
    assert css.count("display: contents") == 0
    # Legacy no-segment fallback: visible select fills toolbar row
    assert ".wd-bc-toolbar .base-mode-select:not(.wd-bc-mode-select-hidden)" in css
