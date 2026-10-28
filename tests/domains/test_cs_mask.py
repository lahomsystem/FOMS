"""CS 가림(플랜 C2-3) — 손으로 꾸민 합성 글만 쓴다(실제 손님 · 직원 이름 · 주소 · 단지 없음).

전화 꼴 숫자는 저장소에 그대로 두지 않는다(2026-10-18 점검) — 실행 중에 조각을 이어 만든다(:func:`_digits`).
이름은 '가나다라마바사' 같은 꾸민 글자, 지역은 시 · 도 이름 말고는 꾸민 이름(가나시 · 다라구 · 마바동)이다.

- 가려야 할 것(BAD): 가린 결과가 정확히 기대한 글이고, 원래 개인정보 조각이 하나도 안 남고, 가림 검사가 0.
- 남아야 할 것(NEAR): 가림이 글을 바꾸지 않고, 가림 검사도 0(흔한 말로 멈추지 않는다).
- 10-28 PC 시범에서 실제로 샌 꼴 넷은 :data:`INCIDENTS_1028` 로 따로 묶는다.
- 구멍을 찾으면 규칙과 여기 예문(가려야 할 것 · 남아야 할 것)을 같이 더한다.
- R6 검수(10-28)로 더한 꼴은 ``r6-…`` 예문 — 치수 · 가격 줄은 :data:`KEEP_NUMBERS` 로 남는지 함께 본다.
"""

from __future__ import annotations

import random
import re
from pathlib import Path

import pytest

from foms.services.cs_agent import masking
from foms.services.cs_agent.masking import (
    MASK_TOKENS,
    MaskLeak,
    call_with_masked,
    leak_counts,
    mask,
    require_masked,
)

_MOBILE_HEAD = "0" + "1" + "0"  # 휴대폰 앞자리 — 전화 꼴 숫자를 글자 그대로 두지 않으려고 이어 만든다


def _digits(*groups: str, sep: str = "-") -> str:
    """숫자 조각을 이어 번호 꼴을 만든다(저장소에 번호 꼴 글자가 남지 않게)."""
    return sep.join(groups)


def _phone(sep: str = "-") -> str:
    return _digits(_MOBILE_HEAD, "0000", "0000", sep=sep)


PHONE = _phone()

# (id, 글, mask 인자, 기대 결과, 남으면 안 되는 조각)
BAD = [
    # 사람 이름
    ("copula", "안녕하세요 김가나입니다", {}, "안녕하세요 [이름]입니다", ("김가나",)),
    ("title-nim", "김가나님 확인 부탁드려요", {}, "[이름]님 확인 부탁드려요", ("김가나",)),
    ("title-gogaek", "김가나 고객님 안녕하세요", {}, "[이름] 고객님 안녕하세요", ("김가나",)),
    ("title-ssi", "이다라씨 맞으시죠", {}, "[이름]씨 맞으시죠", ("이다라",)),
    ("title-mother", "박마바 어머님이 받으세요", {}, "[이름] 어머님이 받으세요", ("박마바",)),
    ("honorific-boss", "최사아 사장님 견적 드립니다", {}, "[이름] 사장님 견적 드립니다", ("최사아",)),
    ("label-colon", "성함: 김가나", {}, "성함: [이름]", ("김가나",)),
    ("label-particle", "성함은 김가나 입니다", {}, "성함은 [이름] 입니다", ("김가나",)),
    ("label-eunyo", "성함은요 김가나", {}, "성함은요 [이름]", ("김가나",)),
    ("label-myeong", "예약자명: 김가나", {}, "예약자명: [이름]", ("김가나",)),
    ("label-seongmyeong", "성명 : 이다라", {}, "성명 : [이름]", ("이다라",)),
    ("label-receiver", "받는 분 박마바", {}, "받는 분 [이름]", ("박마바",)),
    ("label-any-myeong", "업체명: 박마바", {}, "업체명: [이름]", ("박마바",)),
    ("label-gogaek-colon", "고객: 김가나", {}, "고객: [이름]", ("김가나",)),
    ("holder", "예금주 김가나", {}, "예금주 [예금주]", ("김가나",)),
    ("holder-end", "환불 계좌 예금주: 이다라", {}, "환불 계좌 예금주: [예금주]", ("이다라",)),
    ("reservation-slash", f"김가나/ 서울시 가나구 다라로 12/ {PHONE}", {},
     "[이름]/ 서울시 가나구 [도로명주소]/ [전화]", ("김가나", "다라로 12", PHONE)),
    ("reservation-crlf", "김가나,\r\n경기도 가나시", {}, "[이름],\r\n경기도 가나시", ("김가나",)),
    ("reservation-metro", "김가나, 서울 가나구 다라로 12", {}, "[이름], 서울 가나구 [도로명주소]", ("김가나", "다라로 12")),
    ("reservation-list", f"주소/이름/전화: 가나시 다라동 12-3/김가나/{PHONE}", {},
     "주소/이름/전화: 가나시 [지번주소]/[이름]/[전화]", ("김가나", "12-3", PHONE)),
    ("reservation-hosu", "김가나, 1203호", {}, "[이름], [동호수]", ("김가나", "1203")),
    ("name-only-bare", "김가나", {}, "[이름]", ("김가나",)),
    ("name-only-yo", "김가나요", {}, "[이름]요", ("김가나",)),
    ("name-only-line", f"김가나\n경기도 가나시 다라동 12-3\n{PHONE}", {},
     "[이름]\n경기도 가나시 [지번주소]\n[전화]", ("김가나", "12-3", PHONE)),
    # 연락처 · 번호
    ("phone-dash", PHONE, {}, "[전화]", (PHONE,)),
    ("phone-space", _phone(" "), {}, "[전화]", (_phone(" "),)),
    ("phone-dot", _phone("."), {}, "[전화]", (_phone("."),)),
    ("phone-plus82", "+82 " + _digits("1" + "0", "0000", "0000"), {}, "[전화]", ("0000",)),
    ("phone-spaced-digits", " ".join(_MOBILE_HEAD + "0000" + "1234"), {}, "[전화]", ("1 2 3 4",)),
    ("phone-tilde", f"전화 {_phone('~')} 으로", {}, "전화 [전화] 으로", (_phone("~"),)),
    ("phone-attached", "번호" + _phone(""), {}, "번호[전화]", (_phone(""),)),
    ("landline", "집 " + _digits("0" + "2", "000", "0000"), {}, "집 [전화]", ("000-0000",)),
    ("landline-attached", "전화" + _digits("0" + "2", "0000", "0000") + " 입니다", {}, "전화[전화] 입니다", ("0000",)),
    ("account-dashed", "계좌 " + _digits("123", "0000", "0000", "00"), {}, "계좌 [번호]", ("0000",)),
    ("account-long", "계좌번호" + "0" * 11, {}, "계좌번호[번호]", ("0" * 11,)),
    ("mail", "메일 gana@example.com", {}, "메일 [메일]", ("gana@",)),
    ("link-path", "링크 https://example.com/path?name=gana", {}, "링크 [링크:example.com]", ("path", "gana")),
    ("link-userinfo", "http://user:pw@example.com:8080/a", {}, "[링크:example.com]", ("user", "pw", "8080")),
    # 주소
    ("dong-ho", "101동 1203호", {}, "[동호수]", ("101", "1203")),
    ("dong-ho-spaced", "101 동 1203 호", {}, "[동호수]", ("101", "1203")),
    ("hosu", "1203호", {}, "[동호수]", ("1203",)),
    ("hosu-particle", "1203호에요", {}, "[동호수]에요", ("1203",)),
    ("hosu-attached", "가나동1203호", {}, "가나동[동호수]", ("1203",)),
    ("address-label", "주소: 경기도 가나시 다라구 마바로 12", {}, "주소: 경기도 가나시 다라구 [주소]", ("마바로",)),
    ("address-label-metro", "주소 : 서울 가나구 다라동 12-3", {}, "주소 : 서울 가나구 [주소]", ("다라동", "12-3")),
    ("road", "가나로 12", {}, "[도로명주소]", ("가나로",)),
    ("road-daero", "가나대로 123-4", {}, "[도로명주소]", ("가나대로",)),
    ("road-bungil", "가나로12번길 3", {}, "[도로명주소]", ("가나로",)),
    ("road-then-word", "다라로 12 시공 부탁드려요", {}, "[도로명주소] 시공 부탁드려요", ("다라로",)),
    ("lot-then-word", "가나시 다라동 12 원룸이에요", {}, "가나시 [지번주소] 원룸이에요", ("다라동",)),
    ("lot-dash", "가나동 12-3", {}, "[지번주소]", ("12-3",)),
    ("lot-beonji", "가나리 123번지", {}, "[지번주소]", ("123",)),
    ("lot-ga", "가나1가 12-3", {}, "[지번주소]", ("12-3",)),
    ("lot-after-region", "배송지 : 가나구 다라동 45", {}, "배송지 : 가나구 [지번주소]", ("다라동", "45")),
    # 단지
    ("complex-attached", "가나마아파트", {}, "[단지명]", ("가나마",)),
    ("complex-particle", "가나마아파트에서 배송", {}, "[단지명] 배송", ("가나마",)),
    ("complex-brand-tail", "래미안가나마바", {}, "[단지명]", ("가나마바",)),
    ("complex-jai-tail", "가나자이마바사", {}, "[단지명]", ("가나", "마바사")),
    ("complex-villa-spaced", "가나 빌라 3층", {}, "[단지명] 3층", ("가나 빌라",)),
    ("complex-danji", "가나3단지", {}, "[단지명]", ("가나3",)),
    ("complex-unit-short", "가나마아파트 101-1203", {}, "[단지명] [동호수]", ("가나마", "1203")),
    ("brand-only", "힐스테이트가나마", {}, "[단지명]", ("가나마",)),
    # 알고 있는 이름(프로필 · 직원)
    ("customer-given", "가나님 안녕하세요", {"customer_names": ["김가나"]}, "[이름]님 안녕하세요", ("가나",)),
    ("customer-full", "김가나 고객님 도면 확인 부탁드려요", {"customer_names": ["김가나"]},
     "[이름] 고객님 도면 확인 부탁드려요", ("김가나",)),
    ("staff-full", "김가나 실장입니다", {"staff_names": ["김가나"]}, "[직원이름] 실장입니다", ("김가나",)),
    ("staff-given-title", "가나 실장님이 연락드릴게요", {"staff_names": ["김가나"]},
     "[직원이름] 실장님이 연락드릴게요", ("가나",)),
    # R6-10 주민등록번호 · 카드 · 계좌(앞말 앞 · 뒤 · 없음) · 붙여 쓴 02 집 전화
    ("r6-10-resident", "현금영수증 " + _digits("900" + "101", "123" + "4567"), {}, "현금영수증 [번호]", ("4567",)),
    ("r6-10-resident-space", _digits("900" + "101", "223" + "4567", sep=" "), {}, "[번호]", ("4567",)),
    ("r6-10-card-context", "카드번호 " + _digits("1234", "5678", "9012", "3456", sep=" "), {}, "카드번호 [번호]", ("3456",)),
    ("r6-10-card-bare", _digits("1234", "5678", "9012", "3456", sep=" "), {}, "[번호]", ("3456",)),
    ("r6-10-account-before", "농협 " + _digits("302", "1234", "5678", "11", sep=" "), {}, "농협 [번호]", ("5678",)),
    ("r6-10-account-after", _digits("302", "1234", "5678", "11", sep=" ") + " 신한이요", {}, "[번호] 신한이요", ("5678",)),
    ("r6-10-account-bare", _digits("110", "123", "456" + "789", sep=" "), {}, "[번호]", ("789",)),
    ("r6-10-seoul-9", "집 " + "0" + "2" + "1234" + "567", {}, "집 [전화]", ("567",)),
    # R6-11 이름 + 띄어쓰기 + 연락처 · '라고 합니다' · 받는 사람
    ("r6-11-name-phone", f"김가나 {PHONE}", {"customer_names": ["이다라"]}, "[이름] [전화]", ("김가나",)),
    ("r6-11-name-token", "김가나 [전화]", {}, "[이름] [전화]", ("김가나",)),
    ("r6-11-name-address", "최사아 [도로명주소]", {}, "[이름] [도로명주소]", ("최사아",)),
    ("r6-11-rago", "저는 김가나라고 합니다", {}, "저는 [이름]라고 합니다", ("김가나",)),
    ("r6-11-irago", "최사안이라고 해요", {}, "[이름]이라고 해요", ("최사안",)),
    ("r6-11-receiver", "받는 사람 김가나", {}, "받는 사람 [이름]", ("김가나",)),
    ("r6-11-receiver-polite", "받으실 분 이다라", {}, "받으실 분 [이름]", ("이다라",)),
    ("r6-11-receiver-colon", "받으시는 사람: 박마바", {}, "받으시는 사람: [이름]", ("박마바",)),
    # R6-12 단지 끝말(붙여 쓴 꼴만) · 구 없는 '○○동 123'
    ("r6-12-maeul", "가나마을 3단지", {}, "[단지명] 3단지", ("가나마을",)),
    ("r6-12-town", "가나타운 2층", {}, "[단지명] 2층", ("가나타운",)),
    ("r6-12-palace", "가나팰리스", {}, "[단지명]", ("팰리스",)),
    ("r6-12-tower", "가나타워", {}, "[단지명]", ("타워",)),
    ("r6-12-castle", "가나캐슬 101동", {}, "[단지명] 101동", ("캐슬",)),
    ("r6-12-park", "가나파크에서 배송", {}, "[단지명] 배송", ("파크",)),
    ("r6-12-lot-bare", "가나동 123", {}, "[지번주소]", ("123",)),
    # R6-13 주소 이름표 값은 줄 끝까지(60자 넘어도 · 줄바꿈 글자는 남김)
    ("r6-13-long-label", "주소: 경기도 가나시 다라구 " + "마바사아자차카타파하 " * 6 + "파란 대문집", {},
     "주소: 경기도 가나시 다라구 [주소]", ("대문집", "마바사")),
    ("r6-13-label-crlf", "주소: 경기도 가나시 다라로 3\r\n다음 줄", {}, "주소: 경기도 가나시 [주소]\r\n다음 줄", ("다라로",)),
]

#: 10-28 PC 시범 대기열에서 실제로 샌 꼴(설계서 2.7 · 원장 §2)의 합성판.
INCIDENTS_1028 = {
    "name-comma-linebreak": ("김가나, \n경기도 가나시 다라구 마바로 3", "[이름], \n경기도 가나시 다라구 [도로명주소]"),
    "whole-message-name": ("김가나,", "[이름],"),
    "complex-name-tail": ("가나마아파트마바사아자", "[단지명]"),
    "spaced-complex-name": ("라마바 아파트에서 배송돼요?", "[단지명]에서 배송돼요?"),
}

NEAR = [
    "가로 2400 세로 2300 높이 2400", "통가로 2400", "가로로 2400", "사이즈로 120", "아래로 10cm 내려주세요",
    "그대로 2개 주세요", "세트로 2개", "오후로 3시에 가능해요", "높이가 2400이고 길이가 1800", "W1200 x D600 x H750",
    "신축 아파트의 경우 배송이 빨라요", "20평 아파트", "가나동 아파트 배송돼요", "부산 아파트 배송", "디자이너가 확인했어요",
    "고객님 안녕하세요", "기사님이 연락드릴 거예요", "사장님 감사합니다", "선생님 안녕하세요", "어머님께 전해 주세요",
    "부모님 댁으로 보내요", "이번 고객님", "지점장님께 전달드렸습니다","경기도 가나시 다라구 쪽 배송 되나요", "서울시 가나구 배송비 얼마예요",
    "서울, 경기 지역 배송 되나요", "배송비, 서울은 얼마예요", "사진은, 내일 보내드릴게요", "사이즈, 1800 x 600",
    "손잡이, 2개 추가요", "하부장, 상부장 견적", "하부장\n상부장\n서랍장", "주세요", "정말요", "이렇게,", "오늘은,",
    "추가 3개", "다리 4개", "유리 2장", "이동 2번", "냉동 2칸", "혹시 다리 4개 추가돼요?", "2026-10-28 시공",
    f"1{_MOBILE_HEAD} 1200 1800", "2호선 역 근처", "3층 엘리베이터 있어요", "가구 3개 배송", "1,200,000원",
    "성함이 어떻게 되세요", "성함 알려주세요", "예금주 확인 부탁드려요", "예금주: 주식회사", "제품명: 서랍장",
    "사이즈입니다", "하부장이에요", "배송팀입니다",
    "안녕하세요 고객님\n라홈입니다\n서랍장, 2개 견적 안내드립니다\n배송비, 3만원\n설치비, 별도",
    "도어색,\n화이트\n손잡이,\n골드",
    "타워형 구조예요", "판상형, 타워형 둘 다 있어요", "마을버스 타고 가요", "아동 2명", "가나동 32평", "ㅋㅋㅋ ㅎㅎ 감사합니다",
    "연락처 [전화]", "전화 [전화]", "사업자 [번호]", "신다구 [주소]", "주소는 [도로명주소]",
]


def _nonzero(counts: dict[str, int]) -> dict[str, int]:
    return {key: value for key, value in counts.items() if value}


@pytest.mark.parametrize("case_id, text, kwargs, expected, pii", BAD, ids=[c[0] for c in BAD])
def test_bad_is_masked_exactly(case_id, text, kwargs, expected, pii):
    masked = mask(text, **kwargs)
    assert masked == expected
    assert not [p for p in pii if p in masked], case_id
    assert _nonzero(leak_counts(masked)) == {}, case_id


def test_regression_bad_count_is_zero():
    """회귀 목록 전체 — 가린 뒤 개인정보 조각이 남거나 가림 검사가 0 이 아닌 예문 수(BAD)가 0."""
    cases = [(c[0], c[1], c[2], c[4]) for c in BAD]
    cases += [(name, text, {}, ()) for name, (text, _) in INCIDENTS_1028.items()]
    bad = []
    for case_id, text, kwargs, pii in cases:
        masked = mask(text, **kwargs)
        if any(p in masked for p in pii) or any(leak_counts(masked).values()):
            bad.append(case_id)
    assert bad == []


@pytest.mark.parametrize("shape", sorted(INCIDENTS_1028))
def test_incident_1028_shapes_are_masked(shape):
    text, expected = INCIDENTS_1028[shape]
    assert any(leak_counts(text).values()), "가리기 전 글은 검사에 걸려야 한다"
    assert mask(text) == expected
    assert _nonzero(leak_counts(expected)) == {}


@pytest.mark.parametrize("text", NEAR)
def test_near_miss_is_not_masked_and_does_not_trip_check(text):
    assert mask(text) == text
    assert _nonzero(leak_counts(text)) == {}


@pytest.mark.parametrize("text", [c[1] for c in BAD] + NEAR + [t for t, _ in INCIDENTS_1028.values()])
def test_mask_is_idempotent(text):
    once = mask(text)
    assert mask(once) == once


def test_placeholders_are_the_published_tokens():
    """보내기 전 검사(C2-2)가 :data:`MASK_TOKENS` 로 가림 표시를 찾는다 — 가림이 내는 표시는 모두 그 목록에 있다."""
    seen = {tok for c in BAD for tok in re.findall(r"\[[^\]]*\]", mask(c[1], **c[2]))}
    assert seen
    assert [tok for tok in seen if not tok.startswith(MASK_TOKENS)] == []


@pytest.mark.parametrize(
    "category, text",
    [
        ("호수", "1203호"),
        ("전화", PHONE),
        ("번호", "0" * 11),
        ("메일", "gana@example.com"),
        ("링크", "https://example.com/a"),
        ("도로", "가나로 12"),
        ("지번", "가나동 12-3"),
        ("단지붙음", "가나마아파트"),
        ("단지붙음", "래미안가나마"),
        ("단지꼬리", "[단지명]가나마바"),
        ("단지띄움", "라마바 아파트"),
        ("이름꼴", "김가나, 서울시 가나구"),
        ("이름꼴", "김가나"),
        ("이름꼴", "성함: 김가나"),
        ("이름꼴", "김가나님 안녕하세요"),
        ("이름꼴", "김가나입니다"),
        ("이름꼴", "최사아 대표님"),
    ],
)
def test_leak_counts_flags_unmasked_shapes(category, text):
    assert leak_counts(text)[category] >= 1


def test_leak_counts_keys_are_stable():
    keys = ["호수", "전화", "번호", "메일", "링크", "도로", "지번", "단지붙음", "단지꼬리", "단지띄움", "이름꼴"]
    assert list(leak_counts("")) == keys


def test_complex_tail_particles_are_not_a_tail():
    """'[단지명]에서 · 이에요'는 꼬리가 아니다. 조사뿐이어도 긴 덩어리는 꼬리로 센다(멈춤 쪽)."""
    assert leak_counts("[단지명]에서 배송")["단지꼬리"] == 0
    assert leak_counts("[단지명]이에요")["단지꼬리"] == 0
    assert leak_counts("[단지명]" + "이에요" * 4)["단지꼬리"] == 1


@pytest.mark.parametrize("name", ["김가나", "이다라", "박마바", "최사아", "정자차"])
def test_name_shape_counts_rare_words(name):
    """말뭉치 빈도 대신 고정 규칙 — 성씨로 시작하는 흔하지 않은 세 글자 + 쉼표 + 줄 끝이면 이름꼴이다."""
    assert leak_counts(f"{name},\n")["이름꼴"] == 1


@pytest.mark.parametrize(
    "word", ["사이즈", "손잡이", "서랍장", "하부장", "오늘은", "사진은", "배송비", "이렇게", "주말에", "연락처", "경기도", "설치는", "고객님"]
)
def test_name_shape_skips_common_words(word):
    """흔한 말 목록 · 이름에 안 오는 끝 글자(조사 · 장 · 님 …)는 이름꼴로 세지 않는다."""
    assert leak_counts(f"{word},\n")["이름꼴"] == 0


def test_check_is_wider_than_mask_and_stops_unknown_shapes():
    """가림 규칙이 모르는 꼴('이름, 32평')은 가리지 않지만 검사가 잡아 멈춘다 — 두 겹의 뜻."""
    text = "김가나, 32평 견적 부탁드려요"
    assert mask(text) == text
    assert leak_counts(mask(text))["이름꼴"] == 1
    with pytest.raises(MaskLeak):
        require_masked(mask(text))


def test_check_catches_names_hidden_by_title_exceptions():
    """'○○님' 가림은 앞 두 글자가 호칭 목록(이사 · 원장 …)이면 넘긴다(PC 시범 그대로) — 그 틈에 든 이름은 검사가 멈춘다."""
    text = "이사랑님 안녕하세요"
    assert mask(text) == text
    with pytest.raises(MaskLeak):
        require_masked(mask(text))


def test_require_masked_returns_clean_text():
    assert require_masked("[이름]님 견적 보내드립니다") == "[이름]님 견적 보내드립니다"


def test_mask_leak_message_has_counts_only():
    with pytest.raises(MaskLeak) as caught:
        require_masked(f"김가나/ 서울시 가나구 다라로 12/ {PHONE}")
    message = str(caught.value)
    assert caught.value.counts == {"전화": 1, "번호": 1, "도로": 1, "이름꼴": 1}
    for fragment in ("김가나", "다라로", "0000", "서울시"):
        assert fragment not in message


class _FakeBrain:
    """두뇌 대신 — 불린 횟수와 받은 글만 적는다."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, masked: list[str]) -> str:
        self.calls.append(list(masked))
        return "초안"


def test_model_is_not_called_when_a_leak_remains():
    brain = _FakeBrain()
    with pytest.raises(MaskLeak):
        call_with_masked(["안녕하세요", "김가나, 32평 견적 부탁드려요"], brain)
    assert brain.calls == []


def test_model_is_not_called_when_mask_is_broken(monkeypatch):
    """가림이 고장 나도(아무것도 안 가림) 검사가 모델 호출을 막는다."""
    monkeypatch.setattr(masking, "mask", lambda text, **_: text)
    brain = _FakeBrain()
    with pytest.raises(MaskLeak):
        call_with_masked([f"전화 {PHONE} 입니다", "1203호예요"], brain)
    assert brain.calls == []


def test_model_gets_only_masked_messages():
    brain = _FakeBrain()
    result = call_with_masked(["김가나입니다", PHONE, "가나님 견적요"], brain, customer_names=["김가나"])
    assert result == "초안"
    assert brain.calls == [["[이름]입니다", "[전화]", "[이름]님 견적요"]]


def test_single_string_is_rejected_before_calling():
    brain = _FakeBrain()
    with pytest.raises(TypeError):
        call_with_masked(PHONE, brain)
    assert brain.calls == []


def test_short_or_blank_names_are_ignored():
    assert mask("김치냉장고 자리 확인", customer_names=["김", " ", ""]) == "김치냉장고 자리 확인"
    assert mask("") == ""


def test_known_names_are_replaced_in_one_pass():
    """프로필 · 직원 이름은 한 번에 바꾼다 — 앞서 넣은 [이름] 표시 안을 다른 이름이 다시 건드리지 않는다."""
    assert mask("직원 이름", customer_names=["직원"], staff_names=["이름"]) == "[이름] [직원이름]"


_FULLWIDTH = {ord(str(i)): chr(0xFF10 + i) for i in range(10)}
#: R6-9 — 구분 글자가 다른 휴대폰(자모 'ㅡ' · 붙임표 꼴 · 밑줄 · 쉼표 · 폭 없는 공백 · 전각 · 'o1o' · +82).
R69_PHONES = {
    "jamo": _phone("ㅡ"), "jamo-spaced": _phone(" ㅡ "), "en-dash": _phone(chr(0x2013)), "em-dash": _phone(chr(0x2014)),
    "underscore": _phone("_"), "comma": _phone(","), "zero-width": _phone(chr(0x200B)),
    "fullwidth-spaced": _phone(" ").translate(_FULLWIDTH), "fullwidth-dot": _phone(".").translate(_FULLWIDTH),
    "o-for-zero": "o1o" + _phone()[3:], "plus82": "+82 " + _phone()[1:], "plus82-paren": "+82 (0)" + _phone()[1:],
}


@pytest.mark.parametrize("shape", sorted(R69_PHONES))
def test_r6_9_phone_with_any_separator_is_masked_and_counted(shape):
    raw = f"연락처 {R69_PHONES[shape]} 입니다"
    assert leak_counts(raw)["전화"] >= 1, "가리기 전 글은 검사가 잡아야 한다"
    assert mask(raw) == "연락처 [전화] 입니다"
    assert _nonzero(leak_counts(mask(raw))) == {}


def test_r6_9_normalization_is_not_nfkc():
    """맞추기는 보이지 않는 글자 지우기 · 숫자 ASCII 만 — NFKC 처럼 자모 'ㅋ'(U+314B)을 바꾸지 않는다."""
    jamo = chr(0x314B) * 3 + " 감사합니다"
    assert mask(jamo) == jamo
    assert mask("가로" + chr(0x200B) + " 2400") == "가로 2400"


@pytest.mark.parametrize("word", ["계좌", "은행", "뱅크", "농협", "국민", "신한", "하나", "기업", "새마을", "우체국", "신협", "수협",
                                  "카뱅", "토스", "예금", "카드", "card", "결제"])
def test_r6_10_spaced_number_after_money_word_is_masked(word):
    run = _digits("302", "1234", "5678", "11", sep=" ")  # 앞말이 없으면 가리지 않는 꼴(다섯 자리 넘는 묶음 없음)
    assert mask(f"{word} {run}") == f"{word} [번호]"
    assert leak_counts(f"{word} {run}")["번호"] == 1


#: R6-10 제약 — 치수 · 가격 · 날짜 줄은 가리지 않고 검사도 0. 숫자 묶음 셋 넘는 줄은 실행 중에 잇는다.
KEEP_NUMBERS = [
    "가로 2400 세로 2300 높이 600", _digits("2400", "1800", "600", "1200", sep=" "), "3600 2400", "1,138,800원",
    "W1200 D600 H750", "1200*600*750", "2400x2300", "가로2400 세로2300", "폭 600 깊이 400 높이 2100", "1800 x 2400 x 600",
    "총 3,450,000원", "1,200,000원 + 배송비 50,000원", "10% 할인 1,080,000원", "2400 / 1800 / 600", "가로 2,400 세로 1,800",
    _digits("3600", "2400", "600", "1200", "450", sep=" "), "도어 4짝 1200 x 2400", "3,600 x 2,400",
    "서랍장 하나 1200 450 800 사이즈로 주문하려고요", "카드 결제 1,138,800원", "계좌로 1,138,800원 입금했어요",
    "결제 금액 2,400,000원", "결제일 2026-10-28", "결제 후 " + _digits("2400", "1800", "600", "1200", sep=" ") + " 로 제작",
    _digits("2400", "1800", "2400", "1800", sep=" "), "카드 2개 1200 600", "하나은행 계좌로 입금 예정이에요",
    "기업 납품 " + _digits("2400", "1800", "600", "1200", sep=" "), "토스트 1200 450", "신축 30평 거실장 2400 450 500",
    "2026.10.28 10:30~12:00 방문", "01.05 9:30~10:00 방문 예정", "02.05 9:30~10:00 실측", "06.01 9:00 10:00 설치",
    _digits(*["1200"] * 5, sep=" "), "가로 1183 세로 2290", "결제는 10:30부터 18:00까지",
    "우리 집 " + _digits("302", "1234", "5678", "11", sep=" "),  # '우리'는 계좌 앞말이 아니다('우리 집')
]


@pytest.mark.parametrize("text", KEEP_NUMBERS)
def test_r6_10_sizes_and_prices_stay_and_do_not_trip_the_check(text):
    assert mask(text) == text
    assert _nonzero(leak_counts(text)) == {}


@pytest.mark.parametrize(
    "text",
    ["김가나 [전화]", "김가나 [번호]", "김가나 [주소]", "김가나 0" + "2", "저는 김가나라고 합니다", "받는 사람 김가나",
     "받으실 분 이다라"],
)
def test_r6_11_name_shapes_are_counted_before_masking(text):
    assert leak_counts(text)["이름꼴"] == 1


@pytest.mark.parametrize("text, category", [("가나마을", "단지붙음"), ("가나타운", "단지붙음"), ("가나팰리스", "단지붙음"),
                                            ("가나타워", "단지붙음"), ("가나캐슬", "단지붙음"), ("가나파크", "단지붙음"),
                                            ("가나동 123", "지번")])
def test_r6_12_new_shapes_are_counted_before_masking(text, category):
    assert leak_counts(text)[category] == 1


@pytest.mark.parametrize("text", [f"전화 {R69_PHONES['jamo']}", _digits("900" + "101", "123" + "4567"),
                                  _digits("1234", "5678", "9012", "3456", sep=" "), "김가나 [전화]", "가나타워 101동"],
                         ids=["jamo-phone", "resident", "card", "name-token", "complex-tower"])
def test_r6_model_is_not_called_for_new_shapes_when_mask_is_broken(monkeypatch, text):
    monkeypatch.setattr(masking, "mask", lambda value, **_: value)
    brain = _FakeBrain()
    with pytest.raises(MaskLeak):
        call_with_masked([text], brain)
    assert brain.calls == []


_FRAGMENTS = (
    "김가나님", "박다라 고객님", PHONE, R69_PHONES["jamo"], "가나아파트 101동 1203호", "가나로 12", "주소: 경기도 가나시 다라로 3",
    "예금주 김가나", "https://a.example/x?q=1", "kim@example.com", "\n", ", ", "/", " ", "김가나,\n", "이름: 박다라",
    "가나동 12-3", "가나동 45", "[단지명]", "[링크:a.com]", "[전화]", _digits("900" + "101", "123" + "4567"),
    "계좌 " + _digits("302", "1234", "5678", "11", sep=" "), _digits("1234", "5678", "9012", "3456", sep=" "),
    "가로 2400 세로 2300", "1,138,800원", "받는 사람 이다라", "저는 최사아라고 합니다", "가나마을", "라마바 아파트에서",
    "집 0" + "2" + "1234" + "567", chr(0x200B), "ㅋㅋ", "성함 이다라", "가나타워", "1203호에요",
)


def test_r6_13_mask_is_idempotent_on_random_combinations():
    """R6-13 — 조각을 무작위로 이어 붙여도 두 번 가린 결과가 한 번 가린 결과와 같다(씨앗 고정 · 400 조합)."""
    rng = random.Random(20261028)
    kwargs = {"customer_names": ["김가나"], "staff_names": ["박다라"]}
    unstable = []
    for case in range(400):
        text = "".join(rng.choice(_FRAGMENTS) for _ in range(rng.randint(1, 8)))
        once = mask(text, **kwargs)
        if mask(once, **kwargs) != once:
            unstable.append(case)
    assert unstable == []


def test_cs_agent_sources_have_no_phone_shaped_digits():
    """R6-19 공개 저장소 — 상담 에이전트 패키지 전체와 그 시험(test_cs_* 가운데 cs_agent 를 쓰는 것)에 전화 꼴 숫자가 없다.

    전화 · 계좌 꼴(두 · 세 자리 + 세 · 네 자리 + 네 자리, 사이 구분 글자 하나) · 열 자리 넘는 숫자. 치수 줄도 이 꼴이면
    실행 중에 잇는다. cs_agent 를 쓰지 않는 옛 test_cs_*(주문 CS 단계)는 이 묶음 밖이다.
    """
    shaped = re.compile(r"[0-9]{2,3}[-–—_.,ㅡ ]?[0-9]{3,4}[-–—_.,ㅡ ]?[0-9]{4}|[0-9]{10,}")
    root = Path(__file__).resolve().parents[2]
    package = sorted((root / "foms" / "services" / "cs_agent").glob("*.py"))
    suite = [p for p in sorted((root / "tests" / "domains").glob("test_cs_*.py"))
             if "foms.services.cs_agent" in p.read_text(encoding="utf-8")]
    assert len(package) >= 5 and Path(__file__).resolve() in suite
    found = {p.relative_to(root).as_posix(): shaped.findall(p.read_text(encoding="utf-8")) for p in package + suite}
    assert {path: len(hits) for path, hits in found.items() if hits} == {}
