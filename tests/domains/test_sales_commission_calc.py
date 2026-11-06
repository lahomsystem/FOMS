"""프리랜서 영업 수수료 계산 순수 함수 시험(FCOMM-01 §11.1).

요율 · 금액 · 이름은 모두 가짜 값이다(저장소 공개 — 실제 요율은 설정에만 있다).
"""

from __future__ import annotations

import datetime

import pytest

from foms.services.erp_display import erp_shipping_price_from_structured
from foms.services.sales_commission import calc

FREELANCER_ID = 101
OTHER_FREELANCER_ID = 202
MATCH_MAP = {"가짜프리": FREELANCER_ID, " 다른프리 ": OTHER_FREELANCER_ID}


# ---------------------------------------------------------------------------
# 금액 — §11.1 표
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("shipping", "install", "deduction", "bp", "expected"),
    [
        (2_500_000, 1_000_000, 0, 400, 60_000),  # 라홈
        (3_000_000, 1_000_000, 500_000, 600, 90_000),  # 하우드
        (2_000_000, 500_000, 0, 800, 120_000),  # 개인영업
        (1_000_000, 1_000_000, 1, 600, 0),  # 출고가 < 시공비 + 차감
        (1_000_000, 900_000, 500_000, 600, 0),
    ],
)
def test_line_commission_table(shipping, install, deduction, bp, expected):
    assert calc.line_commission(shipping, install, deduction, bp) == expected


def test_commission_rounds_half_up_like_excel():
    # 1,000,025 × 6% = 60,001.5원 → 60,002(엑셀과 같음)
    assert calc.commission_amount(1_000_025, 600) == 60_002
    # 파이썬 round() 라면 짝수 쪽 60,004 로 내려가는 경우: 1,000,075 × 6% = 60,004.5 → 60,005
    assert calc.commission_amount(1_000_075, 600) == 60_005
    assert calc.commission_amount(-5, 600) == 0


def test_line_commission_none_when_install_or_rate_missing():
    assert calc.line_commission(2_000_000, None, 0, 600) is None
    assert calc.line_commission(None, 1_000_000, 0, 600) is None
    assert calc.line_commission(2_000_000, 1_000_000, 0, None) is None
    assert calc.line_commission(2_000_000, 1_000_000, None, 500) == 50_000


# ---------------------------------------------------------------------------
# 요율
# ---------------------------------------------------------------------------

RATES = [
    {"effective_month": "2026-12", "lahom_bp": 650, "haud_bp": 660, "personal_bp": 850},
    {"effective_month": "2026-11", "lahom_bp": 600, "haud_bp": 610, "personal_bp": 800},
]


def test_rate_history_picks_latest_effective_month():
    assert calc.rate_bp_for(RATES, "2026-12", calc.DEAL_LAHOM, None) == 650
    assert calc.rate_bp_for(RATES, "2027-03", calc.DEAL_HAUD, None) == 660
    assert calc.rate_bp_for(RATES, "2026-11", calc.DEAL_PERSONAL, None) == 800
    assert calc.rate_bp_for(RATES, "2026-10", calc.DEAL_LAHOM, None) is None
    assert calc.rate_bp_for([], "2026-12", calc.DEAL_LAHOM, None) is None


def test_manual_deal_uses_only_override():
    assert calc.rate_bp_for(RATES, "2026-12", calc.DEAL_MANUAL, None) is None
    assert calc.rate_bp_for(RATES, "2026-12", calc.DEAL_MANUAL, 600) == 600
    bp = calc.rate_bp_for(RATES, "2026-12", calc.DEAL_MANUAL, 600)
    assert calc.line_commission(2_000_000, 1_000_000, 0, bp) == 60_000
    assert calc.line_commission(2_000_000, 1_000_000, 0, None) is None


def test_override_wins_for_regular_deal():
    assert calc.rate_bp_for(RATES, "2026-12", calc.DEAL_LAHOM, 700) == 700


# ---------------------------------------------------------------------------
# 달 · 대상 여부
# ---------------------------------------------------------------------------


def test_completion_month_requires_main_stage():
    # 메인 단계 PRODUCTION 이면 AS 가 접수돼 있어도(호출자가 AS 축을 넘기지 않는다) 대상 아님(J1)
    assert calc.completion_month("PRODUCTION", "2026-11-20") is None
    assert calc.completion_month(None, "2026-11-20") is None
    assert calc.completion_month("CS", "2026-11-20") == "2026-11"
    assert calc.completion_month("COMPLETED", "2026-12-01") == "2026-12"


def test_completion_month_first_date_of_multi_day():
    assert calc.completion_month("CS", "2026-11-30,2026-12-01") == "2026-11"
    assert calc.completion_month("CS", "2026-11-30 ~ 2026-12-01") == "2026-11"
    assert calc.completion_month("CS", "") is None
    assert calc.completion_month("CS", "미정") is None
    assert calc.completion_month("CS", "2026-13-01") is None


def test_measurement_before_start_month_not_eligible():
    assert calc.is_eligible("2026-10-31", "2026-10-01", None, "2026-11") is False
    assert calc.is_eligible("2026-11-01", "2026-10-01", None, "2026-11") is True


def test_empty_measurement_falls_back_to_received_date():
    assert calc.eligibility_date("", "2026-11-02", None) == "2026-11-02"
    assert calc.is_eligible("", "2026-11-02", None, "2026-11") is True
    assert calc.is_eligible(None, "", datetime.datetime(2026, 11, 3, 9, 0), "2026-11") is True
    assert calc.is_eligible(None, "", None, "2026-11") is False
    assert calc.is_eligible("2026-11-05", "", None, "bad") is False


def test_measurement_month():
    assert calc.measurement_month("2026-10-31", "2026-11-02", None) == "2026-10"
    assert calc.measurement_month(None, "2026-11-02", None) == "2026-11"
    assert calc.measurement_month(None, None, None) is None


# ---------------------------------------------------------------------------
# 주인 · 거래구분
# ---------------------------------------------------------------------------


def test_manager_is_non_freelancer_staff():
    assert calc.resolve_owner("라홈", "다른직원", is_naver=False, match_map=MATCH_MAP) == (None, None)


def test_orderer_match_is_personal_even_if_manager_is_other_freelancer():
    owner = calc.resolve_owner("가짜프리", "다른프리", is_naver=False, match_map=MATCH_MAP)
    assert owner == (FREELANCER_ID, calc.DEAL_PERSONAL)


def test_manager_match_deal_by_orderer():
    assert calc.resolve_owner("라홈 인테리어", "가짜프리", is_naver=False, match_map=MATCH_MAP) == (
        FREELANCER_ID, calc.DEAL_LAHOM)
    assert calc.resolve_owner("하우드", " 가짜프리 ", is_naver=False, match_map=MATCH_MAP) == (
        FREELANCER_ID, calc.DEAL_HAUD)
    assert calc.resolve_owner("숨고", "다른프리", is_naver=False, match_map=MATCH_MAP) == (
        OTHER_FREELANCER_ID, calc.DEAL_MANUAL)


def test_naver_order_with_empty_orderer_is_lahom():
    assert calc.resolve_owner("", "가짜프리", is_naver=True, match_map=MATCH_MAP) == (
        FREELANCER_ID, calc.DEAL_LAHOM)


def test_exact_match_only():
    assert calc.resolve_owner("", "가짜프리2", is_naver=False, match_map=MATCH_MAP) == (None, None)
    assert calc.resolve_owner("", "", is_naver=False, match_map={"": 1}) == (None, None)


def test_extract_order_fields():
    sd = {"parties": {"orderer": {"name": " 라홈 "}, "manager": {"name": "가짜프리"}},
          "schedule": {"measurement": {"date": "2026-11-02"}, "construction": {"date": "2026-11-20"}}}
    assert calc.extract_order_fields(sd) == {
        "orderer_name": "라홈", "manager_name": "가짜프리",
        "measurement_date": "2026-11-02", "construction_date": "2026-11-20"}
    assert calc.extract_order_fields(None)["orderer_name"] == ""


# ---------------------------------------------------------------------------
# 출고가(수수료용)
# ---------------------------------------------------------------------------

EQUIVALENCE_SHAPES = [
    {"items": [{"price": 1_000_000}, {"price": "500,000"}]},
    {"totals": {"items_total": 1_500_000}},  # 품목 없는 옛 모양
    {"totals": {"items_total": "1,200,000", "free_input_amount": 30_000},
     "payment": {"discount": 100_000}},
    {"items": [{"price": 800_000}], "totals": {"items_total": 800_000},
     "payment": {"free_input": "배송: 50,000", "discount": "20,000"}},
    {"totals": {"items_total": "bad"}, "items": [{"price": 300_000}]},
    {"items": [{"price": 100_000}], "payment": {"discount": 500_000}},  # 0 미만 없음
    {"items": [{"price": 100_000, "cancel": "not-a-dict"}]},  # 취소 표시는 dict 만
    {},
    {"items": []},
]


@pytest.mark.parametrize("sd", EQUIVALENCE_SHAPES)
def test_shipping_price_equals_screen_when_nothing_cancelled(sd):
    assert calc.commission_shipping_price(sd) == erp_shipping_price_from_structured(sd)


def test_cancelled_item_excluded():
    sd = {
        "items": [{"price": 1_000_000}, {"price": 500_000, "cancel": {"at": "2026-11-05"}}],
        "totals": {"items_total": 1_500_000, "free_input_amount": 50_000},
        "payment": {"discount": 100_000},
    }
    assert erp_shipping_price_from_structured(sd) == 1_450_000  # 주문 화면 숫자는 그대로
    assert calc.commission_shipping_price(sd) == 950_000


def test_cancelled_item_without_totals():
    sd = {"items": [{"price": "700,000"}, {"price": 300_000, "cancel": {}}]}
    assert calc.commission_shipping_price(sd) == 700_000


def test_all_items_cancelled_keeps_free_input_minus_discount():
    sd = {"items": [{"price": 300_000, "cancel": {}}], "totals": {"free_input_amount": 50_000}}
    assert calc.commission_shipping_price(sd) == 50_000


# ---------------------------------------------------------------------------
# 차감
# ---------------------------------------------------------------------------


def _deduction(**over):
    base = {"id": "d1", "department": "SALES", "amount": -100_000, "reason": "가짜 사유",
            "charge_to_user_id": FREELANCER_ID}
    base.update(over)
    return base


def test_sales_deduction_total_filters():
    sd = {"settlement": {"deductions": [
        _deduction(),
        _deduction(id="d2", amount=-50_000, charge_to_user_id=str(FREELANCER_ID)),
        _deduction(id="d3", voided_at="2026-11-06T10:00:00"),  # 취소된 차감
        _deduction(id="d4", department="CS"),  # 다른 부서
        _deduction(id="d5", charge_to_user_id=OTHER_FREELANCER_ID),  # 다른 사람
        _deduction(id="d6", charge_to_user_id=None),
        "broken",
    ]}}
    assert calc.sales_deduction_total(sd, FREELANCER_ID) == 150_000
    assert calc.sales_deduction_total(sd, str(OTHER_FREELANCER_ID)) == 100_000


@pytest.mark.parametrize("sd", [None, {}, {"settlement": None}, {"settlement": {"deductions": "x"}}])
def test_sales_deduction_total_malformed(sd):
    assert calc.sales_deduction_total(sd, FREELANCER_ID) == 0


# ---------------------------------------------------------------------------
# 세금
# ---------------------------------------------------------------------------


def test_withholding_3_3():
    assert calc.tax_breakdown(1_234_567, calc.TAX_WITHHOLD_3_3) == {
        "gross": 1_234_567, "tax_income": 37_030, "tax_local": 3_700, "vat": 0, "net": 1_193_837}


def test_vat_10():
    assert calc.tax_breakdown(1_234_567, calc.TAX_VAT_10) == {
        "gross": 1_234_567, "tax_income": 0, "tax_local": 0, "vat": 123_456, "net": 1_358_023}


def test_tax_none_and_zero():
    assert calc.tax_breakdown(1_000, calc.TAX_NONE)["net"] == 1_000
    for tax_type in calc.TAX_TYPES:
        result = calc.tax_breakdown(0, tax_type)
        assert result["tax_income"] == result["tax_local"] == result["vat"] == result["net"] == 0
    assert calc.tax_breakdown(-10, calc.TAX_VAT_10)["net"] == 0


def test_unknown_tax_type_rejected():
    with pytest.raises(ValueError):
        calc.tax_breakdown(1_000, "OTHER")
