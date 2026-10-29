"""보내기 전 검사(플랜 C2-2) — 손으로 꾸민 합성 문장만 쓴다(손님 글 · 실제 가격표 값 · 실제 이름 · 주소 없음).

전화 · 계좌 꼴 숫자는 저장소에 글자로 두지 않는다(플랜 공통 규칙, 2026-10-18 점검 · R6-19) — 같은 숫자를 되풀이해
실행 때 만든다.

(a) PC 시범 검사 10개: 막을 것 하나 + 거의 같지만 통과할 것 하나씩.
(b) 우회 묶음: 한글 숫자 · 띄어 쓴 금액 · 돌려 말한 할인 · 링크 돌려 쓰기 — 막을 것이 하나도 빠지면 안 된다(BAD 0).
(c) 직원이 늘 쓰는 좋은 문장은 어느 매체에서나 통과.
(d) 톡톡과 카카오의 차이(D30).
(e) 말투 꼴은 알림만(D35 — 막지 않음).
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest

from foms.services.cs_agent.checks import (
    MEDIUM_NAVER_TALK,
    REASONS,
    CheckResult,
    audit_staff_reply,
    check_draft,
    is_naver_talk,
    numbers_in,
    tone_warnings,
)
from foms.services.cs_agent.checks_read import id_code
from foms.services.cs_agent.masking import MASK_TOKENS

KAKAO = "appKakao"
TALK = MEDIUM_NAVER_TALK
ACCOUNT = "-".join(("0" * 3, "0" * 3, "0" * 6))  # 꾸민 기본 안내 계좌 꼴(D11 — 이 계좌만 허용, 실행 때 만든다)
OTHER_ACCOUNT = "-".join(("0" * 3, "0" * 3, "1" * 6))
BACKSLASH = chr(92)
CENTER = "1" + "5" * 3 + "-" + "0" * 4  # 꾸민 대표 번호(실행 때 만든다)
PHONE = "-".join(("0" + "1" * 2, "1" * 4, "1" * 4))  # 꾸민 휴대 전화 꼴(실행 때 만든다)


def run(text: str, brand: str = "LAHOM", medium=KAKAO, **kw) -> CheckResult:
    return check_draft(text, brand=brand, medium=medium, **kw)


# ── (a) PC 시범 검사 10개 ────────────────────────────────────────────────
PILOT = [
    ("other_brand", "하우드 제품과 같은 자재입니다", "예금주는 주식회사 하우드시스템입니다", {}),
    ("discount_promise", "이번에는 할인해 드리겠습니다", "할인은 어렵습니다", {}),
    ("refund_promise", "환불해 드리겠습니다", "환불 규정은 스토어 안내를 따릅니다", {}),
    ("date_promise", "내일 시공 가능합니다", "토요일도 시공 가능하십니다", {}),
    ("contact_time_promise", "내일 오전 중으로 연락드리겠습니다", "확인 후 안내드리겠습니다", {}),
    ("internal_words", "[사람] 담당자가 정하는 부분입니다", "담당자가 정하는 부분입니다", {}),
    ("mask_marker", "[이름] 고객님 안녕하세요", "고객님 안녕하세요", {}),
    ("talktalk_outside", "카톡으로 사진 보내 주세요", "톡톡으로 사진 보내 주세요", {"medium": TALK}),
    ("talktalk_link", "https://open.kakao.com/o/sample 로 와 주세요", "https://smartstore.naver.com/sample 에서 보실 수 있습니다",
     {"medium": TALK}),
    ("talktalk_phone_ask", "연락처 남겨 주시면 확인해 드리겠습니다", "고객센터로 전화 주시면 도와 드리겠습니다", {"medium": TALK}),
]


@pytest.mark.parametrize("code,bad,good,kw", PILOT, ids=[p[0] for p in PILOT])
def test_pilot_check_blocks_bad_and_passes_near_miss(code, bad, good, kw):
    assert code in run(bad, **kw).codes
    result = run(good, **kw)
    assert result.ok, result.codes


def test_pilot_reasons_kept_and_never_echo_the_draft():
    draft = "[이름] 고객님 내일 오전 중으로 연락드리고 할인해 드리겠습니다"
    result = run(draft)
    assert set(result.codes) == {"mask_marker", "contact_time_promise", "discount_promise"}
    assert all(p.reason == REASONS[p.code] for p in result.problems)
    assert REASONS["other_brand"] == "다른 브랜드 이름" and REASONS["contact_time_promise"] == "연락 시간 약속"


def test_empty_draft_blocked_but_short_staff_reply_passes():
    assert run("").codes == ("empty",)
    assert run("  ~~ !! ").codes == ("empty",)
    assert run("네네 가능하세요~").ok  # 9자 — 시범의 '10자 미만은 빈 답' 규칙은 이 말을 막았다


MORE_BAD = [
    ("date_promise", "모레 설치해 드릴게요", {}),
    ("date_promise", "11/3 설치 가능합니다", {}),
    ("date_promise", "이번 주 토요일도 가능합니다", {}),
    ("date_promise", "다음 주 화요일로 확정해 드리겠습니다", {}),
    ("date_promise", "토요일에 방문드리겠습니다", {}),
    ("date_promise", "3일에 방문드리겠습니다", {"allowed_numbers": [3]}),
    ("contact_time_promise", "오늘 중으로 안내드리겠습니다", {}),
    ("contact_time_promise", "3시까지 답변드릴게요", {"allowed_numbers": [3]}),
    ("contact_time_promise", "퇴근 전에 전화드리겠습니다", {}),
    ("contact_time_promise", "30분 안에 회신드리겠습니다", {"allowed_numbers": [30]}),
    ("contact_time_promise", "내일 확인해 보겠습니다", {}),
    ("contact_time_promise", "월요일에 다시 연락드리겠습니다", {}),
    ("internal_words", "직원 참고: 운임은 담당 확인", {}),
    ("internal_words", "FOMS 에서 확인해 보니 진행 중입니다", {}),
    ("internal_words", "내부 메모로 남겨 두었습니다", {}),
    ("internal_words", "손님께 보낼 답(초안) 입니다", {}),
    ("internal_words", "고객님께 보내지 마세요", {}),
    ("internal_words", "Jev 판정으로는 맞습니다", {}),
    ("mask_marker", "[단지명] [동호수] 맞으실까요", {}),
    ("mask_marker", "[고객 이름] 님 주문 건입니다", {}),
    ("mask_marker", "견적은 [금액] 입니다", {}),
    ("refund_promise", "전액 돌려 드리겠습니다", {}),
    ("refund_promise", "결제 취소해 드릴게요", {}),
    ("refund_promise", "환불 처리 도와 드리겠습니다", {}),
    ("refund_promise", "차액은 다시 입금해 드리겠습니다", {}),
]


@pytest.mark.parametrize("code,bad,kw", MORE_BAD, ids=[f"{c}-{i}" for i, (c, _, _) in enumerate(MORE_BAD)])
def test_wider_forms_of_pilot_rules_are_blocked(code, bad, kw):
    assert code in run(bad, **kw).codes


# ── (b) 우회 묶음 ────────────────────────────────────────────────────────
AMOUNT_FORMS = [
    ("십오만 원", 150000), ("15 만원", 150000), ("15.0만", 150000), ("150,000원", 150000), ("₩150000", 150000),
    ("KRW 150,000", 150000), ("１５만 원", 150000), ("15\u200b만 원", 150000), ("일십오만 원", 150000),
    ("십오만이에요", 150000), ("십오만 정도", 150000), ("150.000원", 150000), ("15\u842c 원", 150000),
    ("1만 5천 원", 15000), ("만 오천 원", 15000), ("15만5천원", 155000), ("십오만오천 원", 155000), ("1만 5000원", 15000),
]


@pytest.mark.parametrize("form,value", AMOUNT_FORMS, ids=[f[0] for f in AMOUNT_FORMS])
def test_amount_bypass_forms_read_as_one_value(form, value):
    draft = f"견적은 {form}"
    assert numbers_in(draft) == {Decimal(value)}
    assert "number_not_allowed" in run(draft, allowed_numbers=[value + 1000]).codes  # BAD: 다른 값
    assert run(draft, allowed_numbers=[value]).ok, run(draft, allowed_numbers=[value]).codes  # 대조군: 같은 값


ROUNDABOUT_DISCOUNT = [
    "서비스로 빼 드릴게요", "가격 맞춰 드릴게요", "조금 더 저렴하게 해 드릴게요", "운임은 안 받겠습니다", "배송비는 저희가 부담하겠습니다",
    "네고 가능합니다", "에누리 해 드릴게요", "할인된 금액으로 진행해 드리겠습니다", "할 인 해 드릴게요", "무료로 해 드리겠습니다",
    "끝자리는 빼 드릴게요", "단가 조정해 드리겠습니다", "특가로 해 드릴게요", "할인 적용 가능하십니다", "견적 금액에서 조금 빼 드릴게요",
    "만 원 덜 받을게요", "이번 주문은 2만 원 할인입니다", "추가금 없이 해 드릴게요", "쿠폰 드릴게요", "적립금으로 돌려 드릴게요",
    "디씨해 드릴게요", "네네 네고 해 드릴게요",
    # R6-1 — 흔한 동사 꼴 · 돈 항목에 붙은 무료 · 안 받 · 맞춰 드리
    "할인 진행해 드리겠습니다", "할인 처리해 드리겠습니다", "할인 혜택을 드리겠습니다", "할인 쿠폰 보내 드리겠습니다",
    "특별 할인가로 안내드리겠습니다", "할인해서 보내 드릴게요", "DC 해 드릴게요", "반 가격에 드리겠습니다", "배송비는 무료입니다",
    "설치비는 받지 않겠습니다", "무상 교체해 드리겠습니다", "예산에 맞춰 드리겠습니다",
]


@pytest.mark.parametrize("bad", ROUNDABOUT_DISCOUNT)
def test_roundabout_discount_is_blocked(bad):
    assert "discount_promise" in run(bad).codes


ROUNDABOUT_OTHER = [
    ("refund_promise", "환불 바로 해 드릴게요"), ("refund_promise", "주문 취소해 드릴게요"), ("refund_promise", "환불 접수 도와 드리겠습니다"),
    ("date_promise", "3일 뒤 방문 가능합니다"), ("date_promise", "다음 달 설치 가능합니다"), ("date_promise", "11월 중 설치 가능합니다"),
    ("date_promise", "주말에 방문드리겠습니다"), ("date_promise", "내일 뵙겠습니다"), ("date_promise", "일주일 뒤 시공 가능합니다"),
    ("contact_time_promise", "오후에 회신 예정입니다"), ("contact_time_promise", "내일 오전 중으로 연락이 갈 예정입니다"),
    ("mask_marker", "견적은 {금액} 입니다"), ("mask_marker", "<이름> 고객님 안녕하세요"),
    ("internal_words", "손님에게는 말하지 마세요"), ("internal_words", "AI 초안입니다"),
    # R6-1 환불 · 취소 동사 꼴
    ("refund_promise", "환불 처리하겠습니다"), ("refund_promise", "환불 진행하겠습니다"), ("refund_promise", "카드 취소 처리하겠습니다"),
    ("refund_promise", "취소 처리해 드리겠습니다"), ("refund_promise", "결제 취소 진행하겠습니다"),
    ("refund_promise", "환불 처리 완료되었습니다"),
    # R6-2 낱말 날짜 + 평서 · 앞일 동사 · 이달 · 월말 · 연내
    ("date_promise", "내일 설치하겠습니다"), ("date_promise", "다음 주에 시공하겠습니다"), ("date_promise", "내일 출고합니다"),
    ("date_promise", "내일 방문합니다"), ("date_promise", "내일 시공 들어갑니다"), ("date_promise", "모레 받아 보실 수 있습니다"),
    ("date_promise", "이달 안에 설치됩니다"), ("date_promise", "이번 주 금요일까지 보내겠습니다"),
    ("date_promise", "다음 주에 받아 보실 수 있게 하겠습니다"), ("date_promise", "내일 기사님이 방문합니다"),
    ("date_promise", "월말에 설치 가능합니다"), ("date_promise", "연내 시공 가능합니다"),
    # R6-4 한글 숫자 때 말 · 답 · 문자 드리
    ("contact_time_promise", "한 시간 안에 연락드리겠습니다"), ("contact_time_promise", "두 시간 내로 회신 드리겠습니다"),
    ("contact_time_promise", "삼십 분 뒤 전화드리겠습니다"), ("contact_time_promise", "내일 답 드리겠습니다"),
    ("contact_time_promise", "내일 문자 드리겠습니다"), ("contact_time_promise", "이틀 안에 연락드리겠습니다"),
    ("contact_time_promise", "내일 연락해 드리겠습니다"),
    # R6-8 모델이 남긴 빈칸 꼴
    ("mask_marker", "[고객명]님 안녕하세요"), ("mask_marker", "○○ 고객님 안녕하세요"), ("mask_marker", "{{customer_name}} 님"),
    ("mask_marker", "(이름)님 안녕하세요"), ("mask_marker", "[NAME] 님"), ("mask_marker", "[ 이 름 ] 님"),
    ("mask_marker", "OO님 안녕하세요"),
]


@pytest.mark.parametrize("code,bad", ROUNDABOUT_OTHER, ids=[b for _, b in ROUNDABOUT_OTHER])
def test_roundabout_refund_date_contact_internal_are_blocked(code, bad):
    assert code in run(bad, allowed_numbers=[3, 11]).codes


# 사장님 D15 · 10-29 — 직원이 보내는 글이라 AI 자기소개 · 표시는 막는다(영어 낱말 속 AI 는 아니다)
@pytest.mark.parametrize("bad", ["안녕하세요 고객님, 라홈 AI 상담사입니다", "챗봇이 안내해 드렸습니다",
                                 "자동 응답으로 안내드립니다", "인공지능이 답변드립니다", "AI가 확인해 보겠습니다"])
def test_ai_self_mention_is_blocked(bad):
    assert "ai_mention" in run(bad).codes


def test_english_words_with_ai_inside_are_not_ai_mentions():
    assert "ai_mention" not in run("AIR 매트리스 문의 감사합니다").codes


# R6-3 — 문장 안 다른 말의 부정 · 묻는 끝은 약속을 지우지 않는다(AI 가 먼저 묻는 것도 제안이다)
NEGATION_ELSEWHERE = [
    ("discount_promise", "할인해 드리고 추가금 없어요"), ("refund_promise", "환불 가능하고 수수료 없습니다"),
    ("discount_promise", "할인 가능하니 걱정 없으세요"), ("discount_promise", "할인 적용해 드릴까요?"),
    ("refund_promise", "환불해 드릴까요?"),
]


@pytest.mark.parametrize("code,bad", NEGATION_ELSEWHERE, ids=[b for _, b in NEGATION_ELSEWHERE])
def test_negation_elsewhere_or_a_question_does_not_cancel_the_promise(code, bad):
    assert code in run(bad).codes


LINK_OBFUSCATION = [
    "kakao . com 에서 보세요", "open 점 kakao 점 com 으로 오세요", "kakao닷컴 으로 오세요", "hxxps://sample.example.com 참고해 주세요",
    "bit.ly/sample 참고해 주세요", "www.sample-shop.co.kr 참고해 주세요", "sample [.] com 참고해 주세요", "sample。com 참고해 주세요",
    "sample(dot)com 참고해 주세요", "https://naver.me@sample.com 참고해 주세요", "smartstore.naver.com.sample.com 참고해 주세요",
    "HTTPS://SAMPLE.COM 참고해 주세요",
    "ｓａｍｐｌｅ．ｃｏｍ 참고해 주세요",  # 전각 글자 링크 — NFKC 가 있어야 잡힌다
]


@pytest.mark.parametrize("bad", LINK_OBFUSCATION)
@pytest.mark.parametrize("medium", [KAKAO, TALK])
def test_obfuscated_or_outside_links_are_blocked(bad, medium):
    assert "link_not_allowed" in run(bad, medium=medium).codes


def test_link_gaps_backslash_unknown_endings_and_lookalikes_are_closed():
    # R6-7 — 브라우저는 역슬래시를 '/' 로 본다 · 끝 이름 목록 밖('.dev') · 키릴 닮은꼴 · 한글 도메인
    for bad in (f"https://sample.example{BACKSLASH}@smartstore.naver.com/abc 참고해 주세요", "sample.dev 에서 보세요",
                "sample.online/a 참고해 주세요", f"exampl{chr(0x435)}.com 참고해 주세요", "라홈닷컴 에서 보세요"):
        assert "link_not_allowed" in run(bad).codes, bad
    assert run("A.S 접수 부탁드립니다").ok  # 마지막 마디가 한 글자면 링크가 아니다
    assert run("폭은 1.5m 입니다", allowed_numbers=["1.5m"]).ok


@pytest.mark.parametrize("good", ["naver . me/sample 에서 보실 수 있습니다", "m.smartstore.naver.com/sample 에서 보실 수 있습니다",
                                  "https://smartstore.naver.com/sample/products/12345 확인해 주세요"])
def test_store_links_pass_even_spaced_and_their_digits_are_not_amounts(good):
    assert run(good, medium=TALK).ok, run(good, medium=TALK).codes


@pytest.mark.parametrize("text", ["사진만 원하시면 보내 주세요", "천장 높이를 재 주세요", "그럼 이만 마치겠습니다", "천만에요",
                                  "만약 어려우시면 말씀 주세요", "이천 지역도 시공 가능하십니다", "실측일 기준입니다", "일정 확인 부탁드립니다"])
def test_words_with_number_syllables_are_not_numbers(text):
    assert numbers_in(text) == frozenset()
    assert run(text).ok, run(text).codes


# ── (c) 직원이 늘 쓰는 좋은 문장 ──────────────────────────────────────────
STAFF_GOOD = [
    ("네네 가능하세요~", {}),
    ("잠시만 기다려 주시면 안내 도와 드리겠습니다!", {}),
    ("확인해 보겠습니다!", {}),
    ("실측일로부터 주말 · 공휴일 제외 5~7일 내외 시공 가능하십니다!", {"allowed_numbers": ["5~7일"]}),
    ("한 번 더 확인해 보겠습니다", {}),
    ("네 고객님 확인 후 안내드리겠습니다", {}),
    ("네고객님 확인해 보겠습니다", {}),  # 붙여 쓴 '네 고객님' — 할인 낱말 '네고' 가 아니다
    ("네네고객님 감사합니다", {}),
    ("사진 보내 주시면 확인해 드리겠습니다", {}),
    ("평일 · 토요일 시공 가능하십니다", {}),
    ("월~토요일 시공 가능하시고 일요일 · 공휴일은 어렵습니다", {}),
    ("매주 토요일 시공 가능하십니다", {}),
    ("월요일부터 금요일까지 상담 가능하십니다", {}),
    ("내일은 방문이 어렵습니다", {}),
    ("할인 가능 여부는 확인 후 안내드리겠습니다", {}),
    ("수납장 내부 깊이도 맞춰 제작 가능하십니다", {}),
    ("도면 초안 받아 보시고 말씀 주세요", {}),
    ("배송 메모에 적어 주세요", {}),
    ("내일 전화 주시면 안내 도와 드리겠습니다", {}),
    ("오늘 문의 주신 내용 확인해 보겠습니다", {}),
    ("평일 오전 9시부터 오후 5시까지 상담 가능하십니다", {"allowed_numbers": [9, 5]}),
    ("오후 5시 이후 문의는 다음 날 순차적으로 답변드립니다", {"allowed_numbers": [5]}),
    ("시공 당일 기사님이 연락드립니다", {}),
    ("실측 기사님이 방문 전에 연락드릴 예정입니다", {}),
    ("주말에도 시공 가능하십니다", {}),
    ("할인 가능하신지 확인해 보겠습니다", {}),
    ("환불 처리 기간은 스토어 규정을 따릅니다", {}),
    ("무료로 실측 가능하십니다", {}),
    ("다음 주에 다시 말씀 주세요", {}),
    # R6-20 · 부정이 약속에 붙은 꼴 · 늘 그런 안내 · 낱말이 겹치는 대조군
    ("토요일 오전에도 상담 가능하세요", {}),
    ("1/2 가격입니다", {"allowed_numbers": ["1/2 가격"]}),  # 분수(날짜 아님) — 숫자라서 허용 목록에는 있어야 한다
    ("토요일에도 시공 가능하십니다", {}),
    ("결제 취소는 어렵습니다", {}),
    ("할인해 드릴 수는 없습니다", {}),
    ("배송비는 무료가 아닙니다", {}),
    ("실측 비용은 무료입니다", {}),
    ("추가 비용 없이 진행 가능한지 확인해 보겠습니다", {}),
    ("환불 규정은 아래 링크를 참고 부탁드립니다", {}),
    ("금일 휴무입니다", {}),
    ("DC 모터라 조용합니다", {}),
    ("포인트 컬러로 제작 가능하십니다", {}),
    ("화이트 라인으로 제작 가능하십니다", {}),
    ("[공지] 영업시간 안내드립니다", {}),
    ("1. 실측\n2. 도면 확인\n3. 시공 순서로 진행됩니다", {}),
    ("\u2460 실측 ② 시공 순서입니다", {}),
]


@pytest.mark.parametrize("text,kw", STAFF_GOOD, ids=[s[0][:12] for s in STAFF_GOOD])
def test_staff_typical_sentences_pass_on_every_medium(text, kw):
    for medium in (KAKAO, TALK, None):
        result = check_draft(text, brand="LAHOM", medium=medium, **kw)
        assert result.ok, (medium, result.codes)


# ── 허용 목록 ────────────────────────────────────────────────────────────
def test_every_number_must_come_from_calculator_or_confirmed_values():
    draft = "가로 1200 기준 견적은 15만 원입니다"
    assert run(draft, allowed_numbers=[1200, 150000]).ok
    assert run(draft, allowed_numbers=[150000]).codes == ("number_not_allowed",)
    assert run(draft, allowed_numbers=["가로 1,200mm · 견적 150,000원"]).ok  # 계산기 글도 같은 규칙으로 읽는다


def test_allow_list_compares_kind_and_unit_not_just_the_value():
    # R6-5 — 수량 숫자가 시각 · 비율 · 예산 약속을 통과시키지 않는다
    assert "number_not_allowed" in run("오후 3시에 방문 예정입니다", allowed_numbers=["서랍 3개"]).codes
    assert "number_not_allowed" in run("3일 뒤 출고합니다", allowed_numbers=["선반 3개"]).codes
    assert "number_not_allowed" in run("10% 빠진 가격입니다", allowed_numbers=["가로 10cm"]).codes
    assert "number_not_allowed" in run("2배 저렴합니다", allowed_numbers=["2개"]).codes
    assert "discount_promise" in run("150만 원에 맞춰 드리겠습니다", allowed_numbers=["예산 150만"]).codes
    # 대조군: 같은 종류 · 단위면 통과, 숫자 값(계산기 값)은 단위를 가리지 않는다
    assert run("서랍 3개 구성입니다", allowed_numbers=["서랍 3개"]).ok
    assert run("가로 10cm 늘어납니다", allowed_numbers=["가로 10cm"]).ok
    assert run("오후 3시 방문 예정이십니다", allowed_numbers=["오후 3시"]).ok
    assert run("오후 3시 방문 예정이십니다", allowed_numbers=[3]).ok


def test_fraction_is_a_ratio_not_a_date():
    # R6-20 — '1/2 가격' 은 1월 2일이 아니다. 숫자라서 허용 목록은 그대로 본다
    assert run("1/2 가격입니다").codes == ("number_not_allowed",)
    assert numbers_in("1/2 가격입니다") == {Decimal("0.5")}
    assert "human_only_amount" in run("1/2 가격입니다", allowed_numbers=["1/2 가격"], human_only_amounts=True).codes
    assert run("1/2 가격입니다", allowed_numbers=[Decimal("0.5")]).ok


def test_range_unit_is_shared_with_the_first_number():
    assert numbers_in("15~20만 원 사이입니다") == {Decimal(150000), Decimal(200000)}
    assert run("15~20만 원 사이입니다", allowed_numbers=[150000, 200000]).ok
    assert "number_not_allowed" in run("15~20만 원 사이입니다", allowed_numbers=[15, 200000]).codes


def test_dates_pass_only_when_confirmed():
    confirmed = [datetime.date(2026, 11, 3)]
    for draft in ("11월 3일 방문으로 확정되셨습니다", "2026-11-03 방문으로 확정되셨습니다", "11/3 방문 예정이십니다"):
        assert run(draft, confirmed_dates=confirmed).ok, (draft, run(draft, confirmed_dates=confirmed).codes)
        assert {"date_promise", "date_not_confirmed"} <= set(run(draft).codes)
        assert "date_not_confirmed" in run(draft, confirmed_dates=[datetime.date(2026, 11, 4)]).codes


def test_relative_day_promise_is_blocked_even_with_confirmed_dates():
    result = run("내일 방문 가능합니다", confirmed_dates=[datetime.date(2026, 11, 3)])
    assert result.codes == ("date_promise",)


def test_human_only_amounts_block_even_allowed_amounts():
    draft = "운임은 1.7배 정도로 12만 원 추가됩니다"
    assert run(draft, allowed_numbers=[1.7, 120000]).ok
    result = run(draft, allowed_numbers=[1.7, 120000], human_only_amounts=True)
    assert result.problems[0].code == "human_only_amount" and result.problems[0].count == 2
    assert run("5~7일 정도 걸립니다", allowed_numbers=[5, 7], human_only_amounts=True).ok  # 금액 아닌 숫자는 그대로


def test_account_number_passes_only_for_the_basic_account():
    assert "account_number" in run(f"입금 계좌는 {ACCOUNT} 입니다").codes
    assert run(f"입금 계좌는 {ACCOUNT} 입니다", allowed_accounts=[ACCOUNT]).ok
    assert run(f"입금 계좌는 {ACCOUNT} 입니다", brand="HAUD", allowed_accounts=[ACCOUNT]).ok  # 계좌는 섞여도 됨(D11)
    assert "account_number" in run(f"입금 계좌는 {OTHER_ACCOUNT} 입니다", allowed_accounts=[ACCOUNT]).codes


def test_phone_numbers_need_the_allow_list_and_get_their_own_code():
    assert run(f"고객센터 {CENTER} 로 전화 주세요", medium=TALK, allowed_numbers=[CENTER]).ok
    assert "phone_number" in run(f"고객센터 {CENTER} 로 전화 주세요", medium=TALK).codes
    assert "phone_number" in run(f"{PHONE} 로 연락 주세요").codes
    assert id_code(PHONE.replace("-", ""), True) == "account_number"  # 계좌 앞말이 있으면 계좌로 본다
    assert id_code("0" * 12, False) == "account_number"


# ── 비공개 메모 · 예시 낱말 ──────────────────────────────────────────────
def test_private_memo_sentence_leak_is_blocked():
    memo = "고객 성향 까다로움. 통화는 실장님이 직접 하기로 함, 확인 필요"
    assert "private_memo_leak" in run("고객 성향 까다로움 참고해 주세요", private_snippets=[memo]).codes
    assert "private_memo_leak" in run("네 통화는 실장님이 직접 하기로 했습니다", private_snippets=[memo]).codes
    assert run("실장님이 직접 연락드릴 예정입니다", private_snippets=[memo]).ok  # 짧은 공통 말만 겹침
    assert run("확인 필요하시면 말씀 주세요", private_snippets=[memo]).ok  # 8자 아래 마디는 보지 않는다


def test_example_only_word_is_blocked():
    words = ["노을오크", "가"]  # 한 글자는 보지 않는다
    assert run("해당 색상은 노을오크로 진행됩니다", example_only_words=words).codes == ("example_only_word",)
    assert run("해당 색상은 화이트로 진행됩니다", example_only_words=words).ok


# ── (d) 톡톡 · 카카오 ────────────────────────────────────────────────────
TALK_ONLY = [
    "카톡으로 사진 보내 주세요", "카카오톡 채널로 문의 주세요", "인스타 DM 주세요", "문자로 보내 드리겠습니다", "이메일로 도면 보내 드리겠습니다",
    "홈페이지에서 확인해 주세요", "연락처 남겨 주세요", "전화번호 알려 주시면 연락드리겠습니다", "성함과 연락처 부탁드립니다", "오픈채팅으로 오세요",
    "번호 주시면 연락드릴게요", "연락처가 필요합니다", "카 톡으로 주세요", "개인 메신저로 주세요", "SNS로 문의 주세요",
    # R6-6 — 앞말 예외에 묻히던 연락처 · '문자 · 메일 주세요' · 라인 · 띄어 쓴 카카오 · 바깥 사이트
    "주문 번호와 연락처 남겨 주세요", "문자 주세요", "메일 주세요", "라인으로 연락 주세요", "카 카 오 톡 채널",
    "저희 사이트에서 확인해 주세요",
]


@pytest.mark.parametrize("text", TALK_ONLY)
def test_talktalk_blocks_moving_outside_but_kakao_allows(text):
    assert not run(text, medium=TALK).ok
    assert run(text, medium=KAKAO).ok, run(text, medium=KAKAO).codes


def test_extra_link_host_counts_only_outside_talktalk():
    text = "https://pf.kakao.com/sample 에서 채널 추가해 주세요"
    assert run(text, medium=KAKAO, allowed_link_hosts=["pf.kakao.com"]).ok
    assert "link_not_allowed" in run(text, medium=KAKAO).codes
    assert "talktalk_link" in run(text, medium=TALK, allowed_link_hosts=["https://pf.kakao.com/"]).codes


def test_talktalk_number_words_that_are_not_customer_numbers_pass():
    for text in ("주문 번호 알려 주시면 확인해 드리겠습니다", "고객센터 번호로 전화 주시면 도와 드리겠습니다", "송장 번호 알려 드리겠습니다"):
        assert run(text, medium=TALK).ok, (text, run(text, medium=TALK).codes)


def test_unknown_medium_gets_talktalk_rules():
    assert "talktalk_outside" in check_draft("카톡으로 사진 보내 주세요", brand="LAHOM").codes
    assert "talktalk_outside" in check_draft("카톡으로 사진 보내 주세요", brand="LAHOM", medium="").codes
    assert is_naver_talk("appNaverTalk") and is_naver_talk("naverTalk") and not is_naver_talk("appKakao")


# ── (e) 말투 꼴 ──────────────────────────────────────────────────────────
def test_tone_warnings_do_not_block():
    result = run("확인해 드릴게요 😊😊")
    assert result.ok and {w.code for w in result.warnings} == {"tone_emoji", "tone_haeyo"}
    long_block = run("상담 안내 " * 25)
    assert long_block.ok and [w.code for w in long_block.warnings] == ["tone_long_block"]
    assert tone_warnings(("상담 안내 " * 10 + "\n\n") * 3) == ()  # 빈 줄로 나눈 짧은 덩어리
    assert tone_warnings("네네 가능하세요~ 😊") == () and tone_warnings("필요 하시면 말씀 주세요") == ()


# ── 브랜드 · 사람 답 점검 ────────────────────────────────────────────────
@pytest.mark.parametrize("token", MASK_TOKENS)
def test_every_mask_token_from_masking_is_blocked_in_a_draft(token):
    # 가림(C2-3)이 넣는 표시가 초안에 남으면 막는다 — 두 모듈의 표시 목록이 어긋나지 않게 한 시험으로 묶는다
    shown = token + "sample.com]" if token.endswith(":") else token
    assert "mask_marker" in run(f"{shown} 확인 부탁 드립니다").codes


def test_brand_mirror_and_unknown_brand():
    assert "other_brand" in run("라홈 제품과 같습니다", brand="HAUD").codes
    assert run("하우드 제품 안내드립니다", brand="HAUD").ok
    assert "other_brand" in run("HAUD 매장 제품입니다").codes
    with pytest.raises(ValueError):
        check_draft("네", brand="OTHER")


def test_staff_reply_audit_counts_brand_mix_and_unknown_account_only():
    text = f"하우드 매장 안내드립니다. 계좌는 {OTHER_ACCOUNT} 입니다. 10% 할인해 드릴게요"
    result = audit_staff_reply(text, brand="LAHOM", allowed_accounts=[ACCOUNT])
    assert set(result.codes) == {"other_brand", "account_number"}  # 할인 · 숫자는 직원이 말할 수 있다
    assert audit_staff_reply(f"계좌는 {ACCOUNT} 입니다", brand="HAUD", allowed_accounts=[ACCOUNT]).ok
