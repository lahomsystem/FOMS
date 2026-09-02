"""실측방 PUSH 본문 서버 조립기 골든 계약 (WIZ-SEND-01 T2).

``build_measure_push_text`` 는 PC 클라이언트 조립기 ``erpGenerateConversionText``
(:file:`static/js/orders/erp-order-shared.js`)의 서버 미러다. 두 경로가 같은 주문에
서로 다른 문구를 내보내면 발주방이 갈리므로, 여기서는 **기대 본문 전문을 문자열
리터럴로 박아 완전 일치**로 고정한다(라벨의 공백까지 계약이다 — ``시   간``·``규 격``).

DB 픽스처가 필요 없는 순수 함수 테스트다.
"""
import copy

from foms.services.channel_measure_message import build_measure_push_text

# 마법사 초안 sd(= _draft_payload_to_structured 결과)와 같은 모양의 대표 표본.
_SINGLE_SD = {
    "parties": {
        "customer": {"name": "홍길동", "phone": "010-1234-5678"},
        "orderer": {"name": "숨고"},
        "manager": {"name": "문정현"},
    },
    "site": {"address_full": "서울시 강남구 테헤란로 1"},
    "schedule": {
        "measurement": {"date": "2026-09-10", "time": "오후 2시"},
        "construction": {"date": "2026-09-20", "time": "오전 9시"},
    },
    "items": [
        {
            "product_name": "붙박이장",
            "spec_rows": [{"spec_width": "2400", "spec_depth": "600", "spec_height": "2400"}],
            "internal": "무늬목",
            "color": "화이트",
            "option_detail": "서랍 2개",
            "handle": "히든",
            "misc": "천장 마감",
            "price": "1200000",
            "extra_input": "현장 확인 필요",
        }
    ],
    "flags": {"factory2": False, "urgent": False, "urgent_reason": ""},
    "payment": {"deposit": 200000},
    "totals": {
        "items_total": 1200000,
        "deposit_amount": 200000,
        "discount_amount": 0,
        "balance_amount": 1000000,
        "final_amount": 1000000,
    },
}

_MULTI_SD = {
    "parties": {
        "customer": {"name": "홍길동", "phone": "010-1234-5678"},
        "orderer": {"name": ""},
        "manager": {"name": "문정현"},
    },
    "site": {"address_full": "서울시 강남구 테헤란로 1"},
    "schedule": {"measurement": {"date": "2026-09-10", "time": "오후 2시"}},
    "items": [
        {
            "product_name": "붙박이장",
            "spec_rows": [
                {"spec_width": "2400", "spec_depth": "600", "spec_height": "2400"},
                {"spec_width": "900", "spec_depth": "", "spec_height": "2400"},
            ],
            "internal": "",
            "color": "화이트",
            "option_detail": "",
            "handle": "",
            "misc": "",
            "price": "1200000",
            "extra_input": "",
        },
        {
            "product_name": "중문",
            "spec_rows": [{"spec_width": "1000", "spec_depth": "", "spec_height": "2100"}],
            "internal": "",
            "color": "블랙",
            "option_detail": "3연동",
            "handle": "",
            "misc": "",
            "price": "800000",
            "extra_input": "손잡이 별도\n실측 후 확정",
        },
    ],
    "flags": {"factory2": True, "urgent": False, "urgent_reason": ""},
    "payment": {"deposit": 500000},
    "totals": {
        "items_total": 2000000,
        "deposit_amount": 500000,
        "discount_amount": 0,
        "balance_amount": 1500000,
        "final_amount": 1500000,
    },
}

# 실측일과 고객명만 있는 최소 초안(마법사 1단계 직후 상태).
_MINIMAL_SD = {
    "parties": {"customer": {"name": "김최소"}},
    "site": {},
    "schedule": {"measurement": {"date": "2026-09-11"}},
    "items": [],
    "flags": {"factory2": False},
    "payment": {"deposit": 0},
    "totals": {
        "items_total": 0,
        "deposit_amount": 0,
        "discount_amount": 0,
        "balance_amount": 0,
        "final_amount": 0,
    },
}

_SINGLE_GOLDEN = (
    "실측일 : 9월 10일\n"
    "시   간 : 오후 2시\n"
    "\n"
    "고객명 : 홍길동\n"
    "발주사 : 숨고\n"
    "시공일 : 9월 20일\n"
    "시공시간 : 오전 9시\n"
    "주  소 : 서울시 강남구 테헤란로 1\n"
    "연락처 : 010-1234-5678\n"
    "\n"
    "제품명 : 붙박이장\n"
    "규 격 : 2400*600*2400\n"
    "내 부 : 무늬목\n"
    "색 상 : 화이트\n"
    "옵 션 : 서랍 2개\n"
    "손잡이 : 히든\n"
    "기 타 : 천장 마감\n"
    "항목 견적 : 1,200,000원\n"
    "추가 입력 : 현장 확인 필요\n"
    "\n"
    "담당자 : 문정현\n"
    "\n"
    "출고가 : 1,200,000원\n"
    "예약금(선금) : 200,000원\n"
    "잔금 : 1,000,000원"
)

_MULTI_GOLDEN = (
    "★★\n"
    "실측일 : 9월 10일\n"
    "시   간 : 오후 2시\n"
    "\n"
    "고객명 : 홍길동\n"
    "발주사 : 라홈\n"
    "시공일 : 상담\n"
    "주  소 : 서울시 강남구 테헤란로 1\n"
    "연락처 : 010-1234-5678\n"
    "\n"
    "1.\n"
    "제품명 : 붙박이장\n"
    "규 격 : 2400*600*2400, 900*2400\n"
    "색 상 : 화이트\n"
    "항목 견적 : 1,200,000원\n"
    "\n"
    "2.\n"
    "제품명 : 중문\n"
    "규 격 : 1000*2100\n"
    "색 상 : 블랙\n"
    "옵 션 : 3연동\n"
    "항목 견적 : 800,000원\n"
    "추가 입력 : 손잡이 별도\n"
    "실측 후 확정\n"
    "\n"
    "담당자 : 문정현\n"
    "\n"
    "출고가 : 2,000,000원\n"
    "예약금(선금) : 500,000원\n"
    "잔금 : 1,500,000원"
)

_MINIMAL_GOLDEN = "실측일 : 9월 11일\n\n고객명 : 김최소\n발주사 : 라홈\n시공일 : 상담"


def _sd(base: dict, **overrides) -> dict:
    """표본 sd 의 깊은 사본에 최상위 키를 덮어쓴다(테스트 간 오염 방지)."""
    sd = copy.deepcopy(base)
    sd.update(copy.deepcopy(overrides))
    return sd


# ---------------------------------------------------------------------------
# 골든 텍스트 계약 (대표 sd 3종)
# ---------------------------------------------------------------------------


def test_single_item_golden_text():
    """단일 품목 초안 — 헤더·품목·푸터 전문이 PC 변환 텍스트와 완전 일치한다."""
    assert build_measure_push_text(_sd(_SINGLE_SD)) == _SINGLE_GOLDEN


def test_multi_item_golden_text():
    """복수 품목 — ``1.``/``2.`` 번호 줄과 다중 규격 join 까지 계약으로 고정한다."""
    assert build_measure_push_text(_sd(_MULTI_SD)) == _MULTI_GOLDEN


def test_minimal_fields_golden_text():
    """최소 필드 초안 — 값 없는 줄은 통째로 사라진다(빈 라벨 줄 금지)."""
    assert build_measure_push_text(_sd(_MINIMAL_SD)) == _MINIMAL_GOLDEN


# ---------------------------------------------------------------------------
# 개별 규칙
# ---------------------------------------------------------------------------


def test_factory2_prepends_stars():
    """``flags.factory2`` 참이면 맨 앞 줄이 ``★★`` 다(라홈시스템 표기)."""
    text = build_measure_push_text(_sd(_SINGLE_SD, flags={"factory2": True}))
    assert text.startswith("★★\n실측일 : 9월 10일\n")
    assert build_measure_push_text(_sd(_SINGLE_SD)).startswith("실측일")


def test_missing_construction_date_falls_back_to_consult():
    """시공일이 없으면 ``상담`` 으로 나간다(줄 자체는 유지)."""
    text = build_measure_push_text(_sd(_SINGLE_SD, schedule={"measurement": {"date": "2026-09-10"}}))
    assert "시공일 : 상담\n" in text
    assert "시공시간" not in text


def test_draft_body_is_identical_to_saved_order_body():
    """초안 발송이라고 머리말이 붙지 않는다 — 실측방이 받는 글은 한 벌이어야 한다.

    D5(초안 머리말 ``※ 등록 전 초안 실측 공유``)는 사용자 결정으로 철회됐다(2026-09-02).
    조립기가 발송 경로를 구분하지 않는다는 것을 인자 목록으로 못 박는다 — 경로별 분기
    인자가 되살아나면 본문이 다시 두 벌이 된다.
    """
    import inspect

    text = build_measure_push_text(_sd(_SINGLE_SD))
    assert text == _SINGLE_GOLDEN
    assert not text.lstrip().startswith("※")
    assert list(inspect.signature(build_measure_push_text).parameters) == ["sd"]


def test_empty_sd_keeps_only_default_lines():
    """빈 sd 는 기본값 두 줄만 남는다(PC 가 빈 폼에서 내는 결과와 같다)."""
    assert build_measure_push_text({}) == "발주사 : 라홈\n시공일 : 상담"


def test_empty_values_are_omitted_entirely():
    """빈 문자열 필드는 ``라벨 : `` 줄을 만들지 않는다."""
    sd = _sd(
        _SINGLE_SD,
        parties={"customer": {"name": "홍길동", "phone": ""}, "manager": {"name": ""}},
        site={"address_full": "", "address_main": ""},
    )
    text = build_measure_push_text(sd)
    assert "연락처" not in text
    assert "주  소" not in text
    assert "담당자" not in text
    assert "고객명 : 홍길동\n" in text


def test_zero_amounts_drop_money_lines():
    """0원 금액 줄은 생략한다(``항목 견적``·``출고가``·``잔금`` 공통)."""
    sd = _sd(
        _SINGLE_SD,
        items=[{"product_name": "붙박이장", "price": "0"}],
        payment={"deposit": 0},
        totals={"items_total": 0, "deposit_amount": 0, "final_amount": 0},
    )
    text = build_measure_push_text(sd)
    assert "항목 견적" not in text
    assert "출고가" not in text
    assert "예약금(선금)" not in text
    assert "잔금" not in text
    assert "제품명 : 붙박이장\n" in text


def test_single_item_has_no_number_line():
    """품목이 1건이면 번호 줄(``1.``)을 붙이지 않는다."""
    assert "1.\n" not in build_measure_push_text(_sd(_SINGLE_SD))


def test_address_main_fallback():
    """``site.address_full`` 이 없으면 ``address_main`` 을 쓴다."""
    sd = _sd(_SINGLE_SD, site={"address_main": "경기도 성남시 분당구 1"})
    assert "주  소 : 경기도 성남시 분당구 1\n" in build_measure_push_text(sd)


def test_multi_date_measurement_is_korean_joined():
    """콤마 다중 실측일도 각각 한글로 바꿔 ``, `` 로 잇는다."""
    sd = _sd(_SINGLE_SD, schedule={"measurement": {"date": "2026-09-10,2026-09-11"}})
    assert "실측일 : 9월 10일, 9월 11일\n" in build_measure_push_text(sd)


def test_spec_string_wins_over_spec_rows():
    """직접 입력된 ``spec`` 문자열이 spec_rows 조립값보다 우선한다(PC 와 동일 우선순위)."""
    sd = _sd(
        _SINGLE_SD,
        items=[
            {
                "product_name": "붙박이장",
                "spec": "현장 실측 후 확정",
                "spec_rows": [{"spec_width": "2400", "spec_depth": "600", "spec_height": "2400"}],
            }
        ],
    )
    assert "규 격 : 현장 실측 후 확정\n" in build_measure_push_text(sd)


def test_erp_notes_and_payment_extras_render():
    """ERP 주문 sd 의 특이사항·자유입력·잔금메모·현금영수증도 PC 순서로 실린다."""
    sd = _sd(
        _SINGLE_SD,
        notes={
            "measurement_note": "엘리베이터 없음",
            "construction_note": "오전만 가능",
            "address_note": "정문 주차",
            "phone_note": "부재 시 문자",
        },
        payment={
            "deposit": 200000,
            "free_input": "배송비:50000",
            "balance_note": "시공 후 입금",
            "cash_receipt": "010-1234-5678",
            "balance_confirmed": True,
        },
    )
    text = build_measure_push_text(sd)
    assert "실측 특이사항 : 엘리베이터 없음\n" in text
    assert "시공 특이사항 : 오전만 가능\n" in text
    assert "주소 특이사항 : 정문 주차\n" in text
    assert "연락처 특이사항 : 부재 시 문자\n" in text
    assert "배송비 : 50,000원(총견적 포함)\n" in text
    assert "잔금 : 1,000,000원(결제 완)\n" in text
    assert "잔금메모 : 시공 후 입금\n" in text
    assert text.endswith("\n현금영수증 : 010-1234-5678")


def test_string_notes_do_not_crash():
    """``sd['notes']`` 가 문자열인 마법사 초안에서도 특이사항 줄 없이 정상 조립된다."""
    sd = _sd(_MINIMAL_SD, notes="고객 요청 메모")
    assert build_measure_push_text(sd) == _MINIMAL_GOLDEN


def test_shipping_price_prefers_totals_then_derives():
    """출고가는 ``totals.shipping_price`` 우선, 없으면 품목합에서 파생한다."""
    with_direct = _sd(_SINGLE_SD, totals=dict(_SINGLE_SD["totals"], shipping_price=1300000))
    assert "출고가 : 1,300,000원\n" in build_measure_push_text(with_direct)
    assert "출고가 : 1,200,000원\n" in build_measure_push_text(_sd(_SINGLE_SD))


def test_non_dict_input_does_not_crash():
    """sd 가 dict 가 아니어도 500 없이 기본값 본문을 돌려준다."""
    assert build_measure_push_text(None) == "발주사 : 라홈\n시공일 : 상담"
