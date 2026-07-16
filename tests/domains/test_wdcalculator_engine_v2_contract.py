"""WD 계산기 엔진 v2 확장(E1~E5) 구조 계약.

E1: MINE(직접) 행 제품명 필드 + 저장 왕복(compData 보존)
E3: '직접'→'MINE', '추가금 추가'→'직접입력' 리네임
E4: 행별 직접입력 표기에서 '추가금' 접미사 제거(이름 있을 때)
E5: 견적 계산 버튼 전 플랫폼 삭제(계산은 전 입력 경로 자동)
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRIMARY = (ROOT / "static/js/wdcalculator/primary-form.js").read_text(encoding="utf-8")
PRICING = (ROOT / "static/js/wdcalculator/pricing-core.js").read_text(encoding="utf-8")
MOBILE = (ROOT / "static/js/wdcalculator/mobile-enhance.js").read_text(encoding="utf-8")
BODY = (ROOT / "templates/wdcalculator/partials/wdcalculator_body.html").read_text(encoding="utf-8")


def test_e1_manual_name_field_rendered_and_collected():
    assert PRIMARY.count("base-manual-name") >= 2  # 템플릿 렌더 + 수집
    assert "manualName" in PRIMARY


def test_e1_manual_name_survives_pricing_normalization():
    # compData 재구성(1m·30cm·폴백)에서 manualName 보존
    assert PRICING.count("manualName") >= 3


def test_e3_mode_button_renamed_to_mine():
    assert 'data-mode="manual">MINE<' in PRIMARY
    assert 'data-mode="manual">직접<' not in PRIMARY


def test_e3_fee_button_renamed():
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
