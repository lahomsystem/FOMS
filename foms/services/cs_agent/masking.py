"""가림 — 상담 글이 모델(두뇌)에 닿기 전에 개인정보를 코드로 가리고, 가린 뒤에 남은 꼴을 센다.

플랜 ``docs/plans/2026-10-27-cs-ai-agent-plan.md`` C2-3 · 설계서 4절 4('코드 가림 → 가림 검사 0 이 아니면
멈춤 · 경보') · 9.2 '가림 구멍'. 순수 함수다: 네트워크 · DB · 채널톡이 없다. 규칙은 학습 폴더 PC 시범의 가림
(``build_corpus.mask``)과 대기열 검사(``queue_pii_check``)를 옮겼다. 낱말 목록은 :mod:`.masking_words`.

순서(바꾸지 않는다): :func:`mask` → :func:`leak_counts` 가 0 → 그때만 모델을 부른다(:func:`call_with_masked`), 아니면
:class:`MaskLeak` 로 멈춘다(예외 · 로그엔 칸별 숫자만 — C5-2). 가림 규칙은 좁고 정확하게, 검사는 넓게 — 검사가 멈추면
사람이 보고 규칙을 더한다. 둘 다 먼저 맞춘다(:func:`_normalize` — 보이지 않는 글자 지움 · 전각 숫자 → ASCII, R6-9).

10-28 PC 시범에서 실제로 샌 꼴과 막는 규칙:

- 이름 뒤 쉼표 · 줄바꿈("이름, ⏎경기도 …", "이름/ 주소/ 전화") → :data:`_RESERVATION_NAME`(+ 쉼표 없는 줄바꿈은
  :data:`_NAME_ONLY_LINE`) · 검사 '이름꼴'
- 한 글 전체가 이름("이름,") → :data:`_NAME_ONLY_LINE`(서버판은 여러 줄 글의 한 줄까지 넓힘) · 검사 '이름꼴'
- 단지 이름 꼬리("[단지명]○○○○") → :data:`_COMPLEX_ATTACHED` · :data:`_COMPLEX_BRAND_ONLY` 의 꼬리 칸 · 검사 '단지꼬리'
- 띄어 쓴 단지 이름("○○ 아파트") → :data:`_COMPLEX_SPACED` · 검사 '단지띄움'

R6 검수(10-28)로 더한 것: 구분 글자가 다른 휴대폰(ㅡ · – · _ · , · 폭 없는 공백 · 전각 · o1o) · 주민등록번호 · 계좌 · 카드
앞말 뒤 띄어 쓴 번호 · 붙여 쓴 02 집 전화 · '이름 [전화]' · '이름라고 합니다' · 받는 사람 · 마을 · 타운 같은 단지 끝말 ·
'○○동 123' · 주소 이름표 값은 줄 끝까지(두 번 가려도 같게). 치수 · 가격 줄은 남긴다(:mod:`.masking_contacts`).

구멍을 찾으면 규칙과 합성 예문(가려야 할 것 · 남아야 할 것)을 같이 고친다(``tests/domains/test_cs_mask.py``). 흔한 말이
이름꼴로 잡혀 멈추면 :data:`COMMON_WORDS` 에 넣고 '남아야 할 것'에 더한다. 지역 낱말(시 · 도 · 구 · 동)은 운임 규칙에 쓰니 남긴다.
"""

from __future__ import annotations

import re
from typing import Callable, Iterable, Mapping, Sequence, TypeVar

from foms.services.cs_agent.masking_words import (
    APT_ENDINGS, APT_GENERIC, COMMON3, COMMON_WORDS, COMPLEX_BRAND_ALT, COMPLEX_SUFFIX_ALT, COMPLEX_TAIL_PARTICLE_ALT,
    LABEL_ALT, LABEL_VALUE_KEEP, LOT_KEEP_WORDS, METRO_ALT, METRO_SET, NON_NAME_FINALS,
    NOT_NAME_PREFIXES, REGION_SUFFIXES, ROAD_KEEP_ALT, ROAD_KEEP_DAERO, SURNAMES, UNIT_ALT,
)
from foms.services.cs_agent.masking_contacts import MAIL, NUMBER, PHONE, contact_leaks, mask_contacts
from foms.services.cs_agent.masking_contacts import normalize as _normalize

__all__ = [
    "COMMON_WORDS", "MASK_TOKENS", "MaskLeak", "SURNAMES", "call_with_masked", "leak_counts", "mask", "require_masked",
]

T = TypeVar("T")

# ── 가림 표시 ──────────────────────────────────────────────────────────────
NAME, STAFF = "[이름]", "[직원이름]"  # 전화 · 번호 · 메일 표시는 :mod:`.masking_contacts`
UNIT, ADDRESS, ROAD, LOT, COMPLEX, HOLDER = "[동호수]", "[주소]", "[도로명주소]", "[지번주소]", "[단지명]", "[예금주]"
#: 보내기 전 검사(C2-2 '가림 표시')가 초안에서 찾을 표시. 링크는 ``[링크:도메인]`` 이라 앞머리만 둔다.
MASK_TOKENS = (NAME, STAFF, PHONE, NUMBER, MAIL, "[링크:", UNIT, ADDRESS, ROAD, LOT, COMPLEX, HOLDER)

_SUR = f"[{SURNAMES}]"
_NOT_NAME = "|".join(NOT_NAME_PREFIXES)


def _is_common_word(word: str) -> bool:
    """흔한 말인가 — 두 목록에 있거나 끝 글자가 이름에 안 오는 글자다."""
    return word in COMMON3 or word in COMMON_WORDS or word[-1:] in NON_NAME_FINALS


def _looks_like_name(word: str) -> bool:
    """세 글자 낱말이 사람 이름 꼴인가 — 성씨로 시작하고 흔한 말이 아니면 이름으로 본다(가림 · 검사가 같이 쓴다)."""
    return len(word) == 3 and word[0] in SURNAMES and not _is_common_word(word)


# ── 주소 ───────────────────────────────────────────────────────────────────
#: 'O동 O호'.
_DONG_HO = re.compile(r"\d{1,4}\s?동\s?\d{1,5}\s?호")
#: 호수만 쓴 꼴('403호'). 뒤에 조사가 붙어도 잡는다('1203호에요' — 서버판), 호선 · 호환 · 호텔은 뺀다.
_HOSU = re.compile(r"(?<!\d)\d{3,4}\s?호(?![선환텔])")
#: '주소: …' 뒤 값은 줄 끝(또는 빗금)까지 통째로 — 길이 상한이 있으면 꼬리가 남고 표시가 잘린다(R6-13). 앞머리 지역은 남긴다.
_ADDRESS_LABEL = re.compile(r"(주\s?소\s*[:：]\s*)([^\r\n/]{4,})")
_REGION_HEAD_RUN = re.compile(rf"(?:(?:[가-힣]{{1,6}}(?:특별시|광역시|시|도|군|구)|{METRO_ALT}|경기)\s+)+")
#: 도로명 + 건물 번호('○○로 12', '○○대로 3-1', '○○로12번길 3', 사이에 구분 글자 하나 '○○로ㅡ12' — R6 시험).
_ROAD = re.compile(r"(?<![가-힣])[가-힣]{2,}\d{0,3}(?:대로|로|길)[\s\-–—_ㅡ]?\d+(?:-\d+)?(?:번길\s?\d+)?")
_ROAD_KEEP_PREFIX = re.compile(f"(?:{ROAD_KEEP_ALT})로")
#: 번호 바로 뒤가 단위면 주소 번호가 아니다('아래로 10cm', '냉동 2칸' — 서버판). 층 · 호 · 동 · 번은 주소에 오므로 넣지 않는다.
#: 한글 단위는 숫자에 붙어야 한다 — '○○로 12 시공 · 원룸'처럼 띄어 쓴 말을 단위로 보면 주소가 샌다.
_UNIT_AFTER = re.compile(UNIT_ALT)
#: 지번 — '○○동 12-3' · '○○리 123번지' · '○○1가 12-3' · 시 · 군 · 구 · 읍 · 면 뒤 '○○리 123' · '○○동 123'(R6-12).
#: PC 시범의 '가' 가지는 조사('높이가 2400')를 집을 수 있어 '1가'만 남겼다. 흔한 말 · 단위는 :func:`_lot_kept`.
_LOT = re.compile(
    r"(?<![가-힣])([가-힣]{1,8}(?:동|리)|[가-힣]{1,8}\d{1,2}가)\s?(?:\d{1,5}-\d{1,5}(?:\s?번지?)?|\d{1,5}\s?번지?)"
    r"|(?<=[시군구읍면] )([가-힣]{1,8}리)\s?\d{1,5}(?![\d-])|(?<![가-힣])([가-힣]{1,7}동)\s?\d{1,5}(?![\d-])"
)

# ── 사람 이름 ──────────────────────────────────────────────────────────────
#: 이름 + 님 · 씨 · 고객 · 어머님 · 아버님 · 사모님(PC 시범의 두 규칙을 하나로). 흔한 말('지점장님')은 남긴다(서버판).
_NAME_BEFORE_TITLE = re.compile(rf"(?<![가-힣])(?!{_NOT_NAME})({_SUR}[가-힣]{{1,2}})(?=\s?(?:고객|씨|어머님|아버님|사모님|님))")
#: 세 글자 이름 + 사장님 · 대표님 · 여사님(서버판 — 업체 손님 호칭).
_NAME_BEFORE_HONORIFIC = re.compile(rf"(?<![가-힣])({_SUR}[가-힣]{{2}})(?=\s?(?:사장|대표|여사)님)")
#: 세 글자 이름 + 입니다 · 이에요 · 예요 · 이고요 · '(이)라고 합니다'(라고는 R6-11).
_NAME_BEFORE_COPULA = re.compile(
    rf"(?<![가-힣])({_SUR}[가-힣]{{2}})(?=\s?(?:입니다|이에요|예요|이고요|이구요|입니당|이?라고\s?(?:합니다|해요|하고요|하는)))"
)
#: 이름 + 띄어쓰기 + 전화 · 번호 · 메일 · 주소 표시나 0 · +82 로 시작하는 번호('김○○ [전화]' — 프로필 이름이 다를 때, R6-11).
_NAME_BEFORE_INFO = re.compile(
    rf"(?<![가-힣])({_SUR}[가-힣]{{2}})(?=[ \t]+(?:(\[(?:전화|번호|메일)\]|\+?82|0\d)|\[(?:주소|도로명주소|지번주소|동호수)\]))"
)
#: '성함 · 예약자 · 받는 사람 … : 이름'. 성씨 목록 밖 이름도 가린다. '…자명'의 명은 남김없이 먹는다(두 번 가려도 같게).
#: 조사(은 · 는 · 이 · 가)는 이름표에 붙어야 한다 — 띄어 쓴 '성함 이○○'의 '이'는 성씨다(R6-11 때 고침, PC 시범도 같은 구멍).
_NAME_AFTER_LABEL = re.compile(rf"((?:{LABEL_ALT})(?:명)?(?!명)(?:(?:은|는|이|가)요?)?\s*[:：]?\s*)([가-힣]{{2,4}})(?![가-힣])")
#: '…명 : 이름' · '고객 : 이름' — 쌍점이 있을 때만(서버판, 검사 '이름꼴'의 이름표 꼴과 같은 범위).
_NAME_AFTER_COLON_LABEL = re.compile(rf"((?:[가-힣]{{0,4}}명|고객)\s*[:：]\s*)({_SUR}[가-힣]{{2}})(?![가-힣])")
#: 예금주 이름. 글 끝 · 입니다 앞도 잡는다(서버판), 주식회사는 남긴다.
_ACCOUNT_HOLDER = re.compile(
    r"(예금주(?:명)?(?!명)(?:(?:은|는)요?)?\s*[:：]?\s*)([가-힣]{2,4})(?=$|[^가-힣]|입니다|이에요|예요|이고|이요|님|씨)"
)
#: 지역 낱말(예약 정보 꼴의 다음 칸 · 검사 문맥). 서울 · 부산처럼 시 없이 쓴 말도 넣었다(서버판).
_REGION_NEXT = rf"(?:[가-힣]{{2,}}(?:시|도|군|구|읍|동)(?![가-힣])|(?:{METRO_ALT})|경기(?:도|\s))"
#: 예약 정보 꼴 '이름/ 주소/ 전화' · '이름, ⏎경기도 …'(10-28 두 번 샘). 이름 뒤 빗금 · 쉼표 다음이 지역 · 가림 표시 · 0으로 시작하는 번호.
_RESERVATION_NAME = re.compile(rf"(?m)(^|[\s,/\]])({_SUR}[가-힣]{{1,3}})(?=\s?[/,]\s*(?:{_REGION_NEXT}|\[|0\d))")
#: 한 글 · 한 줄 전체가 이름('김○○,' · '김○○요' — 10-28 샘). 쉼표 없이 줄을 바꾼 예약 정보도 여기서 잡는다.
_NAME_ONLY_LINE = re.compile(rf"(?m)^([ \t]*)({_SUR}[가-힣]{{2}})(요?)([ \t]*[,./]?[ \t\r]*)$")
#: 직원 이름(성 뺀 이름) + 직함 — 직원 이름은 부르는 쪽이 넘긴다(저장소에 두지 않는다).
_STAFF_TITLES = r"(?=\s?(?:실장|팀장|과장|대리|주임|매니저|님|씨))"

# ── 단지 ───────────────────────────────────────────────────────────────────
#: 붙여 쓴 단지 이름 + 뒤 꼬리 여덟 글자까지('○○아파트', '○○자이○○' — 10-28 꼬리가 남음). '디자이너'는 뺀다.
_COMPLEX_ATTACHED = re.compile(
    rf"(?<![가-힣A-Za-z0-9])[가-힣A-Za-z0-9]{{1,12}}(?:{COMPLEX_SUFFIX_ALT})[가-힣A-Za-z0-9]{{0,8}}"
)
#: 띄어 쓴 단지 이름 '○○ 아파트'(10-28 샘). 앞말이 흔한 말 · 지역 · 숫자 · 조사로 끝나면 남긴다(_apt_keep).
_COMPLEX_SPACED = re.compile(r"(?<![가-힣A-Za-z0-9\]])([가-힣A-Za-z0-9]{1,12})\s(?:아파트|빌라|오피스텔)")
_APT_NUMERIC = re.compile(r"\d+(?:년|년차|평|평대|층|세대|억|개)?")
#: 앞말 없이 쓴 단지 브랜드('래미안○○').
_COMPLEX_BRAND_ONLY = re.compile(rf"(?<![가-힣A-Za-z0-9\]])(?:{COMPLEX_BRAND_ALT})[가-힣A-Za-z0-9]{{0,8}}")
#: 단지 뒤 '101-1203' 줄여 쓴 동 · 호(서버판).
_COMPLEX_UNIT_SHORT = re.compile(r"(\[단지명\]\s?)\d{1,4}\s?-\s?\d{1,5}(?!\d)")


def _apt_keep(word: str) -> bool:
    """'○○ 아파트'의 앞말이 단지 이름이 아닌가 — 흔한 말 · 지역(시 · 도 · 구 · 동 …) · 조사 끝 · 숫자(20평)."""
    regional = word.endswith(REGION_SUFFIXES)
    return word in APT_GENERIC or regional or word.endswith(APT_ENDINGS) or bool(_APT_NUMERIC.fullmatch(word))


def _road_kept(match: re.Match[str]) -> bool:
    """도로명 꼴인데 주소가 아닌가 — '통가로 2400' · '사이즈로 120' · '그대로 2개' · 번호 뒤 단위."""
    text = match.group(0)
    head = re.sub(r"[\d-]+$", "", text.split()[0])
    return (
        head.endswith(("으로", "가로", "세로"))
        or head.startswith(("가로", "세로"))
        or bool(_ROAD_KEEP_PREFIX.match(text))
        or head in ROAD_KEEP_DAERO
        or bool(_UNIT_AFTER.match(match.string, match.end()))
    )


def _lot_kept(match: re.Match[str]) -> bool:
    """지번 꼴인데 주소가 아닌가 — '다리 2-3개' · '냉동 2칸' 같은 흔한 말 · 번호 뒤 단위."""
    word = next(group for group in match.groups() if group)
    return word.endswith(LOT_KEEP_WORDS) or bool(_UNIT_AFTER.match(match.string, match.end()))


# ── 가림 ───────────────────────────────────────────────────────────────────
def _clean_names(names: Iterable[str]) -> list[str]:
    """두 글자 넘는 이름만(맞추고 앞뒤 공백 뺌). 한 글자는 다른 낱말을 너무 많이 가린다."""
    return [n for n in (_normalize(str(raw or "")).strip() for raw in names) if len(n) >= 2]


def _replace_known_names(text: str, customer_names: Sequence[str], staff_names: Sequence[str]) -> str:
    """상담 손님의 프로필 이름(+ 성 뺀 이름)은 [이름], 직원 이름은 [직원이름]으로 한 번에 바꾼다.

    성 뺀 이름은 세 글자 한글 이름의 뒤 두 글자다(PC 시범 draft_prep). 한 번에 바꿔야 앞서 넣은 표시 안을
    다음 이름이 다시 건드리지 않는다. 같은 글자가 둘 다에 있으면 손님 쪽이 이긴다.
    """
    table = {name: STAFF for name in _clean_names(staff_names)}
    for name in _clean_names(customer_names):
        table[name] = NAME
        if re.fullmatch(r"[가-힣]{3}", name):
            table[name[1:]] = NAME
    if not table:
        return text
    pattern = re.compile("|".join(re.escape(n) for n in sorted(table, key=len, reverse=True)))
    return pattern.sub(lambda m: table[m.group(0)], text)


def _address_label_value(match: re.Match[str]) -> str:
    """'주소: …' 값은 앞머리 지역(시 · 도 · 군 · 구)만 남기고 [주소]."""
    value = match.group(2)
    head = _REGION_HEAD_RUN.match(value)
    kept = head.group(0) if head else ""
    rest = value[len(kept):]
    return match.group(1) + kept + (ADDRESS if rest.strip() else "")


def _mask_addresses(text: str) -> str:
    """동 · 호수 · 주소 이름표 · 도로명 · 지번. 호수는 예약 정보 꼴('이름, 1203호')보다 먼저 가린다(서버판)."""
    text = _DONG_HO.sub(UNIT, text)
    text = _HOSU.sub(UNIT, text)
    text = _ADDRESS_LABEL.sub(_address_label_value, text)
    text = _ROAD.sub(lambda m: m.group(0) if _road_kept(m) else ROAD, text)
    return _LOT.sub(lambda m: m.group(0) if _lot_kept(m) else LOT, text)


def _name_if_like(match: re.Match[str]) -> str:
    """잡은 낱말이 흔한 말이면 그대로('사이즈입니다' · '하부장이에요' · '지점장님'), 아니면 [이름]."""
    return match.group(0) if _is_common_word(match.group(1)) else NAME


def _label_value(match: re.Match[str]) -> str:
    """이름표 뒤 값 — 흔한 말('알려' · '어떻게')이면 그대로."""
    return match.group(0) if match.group(2) in LABEL_VALUE_KEEP else match.group(1) + NAME


def _holder_value(match: re.Match[str]) -> str:
    """예금주 값 — 주식회사 · 흔한 말이면 그대로."""
    value = match.group(2)
    if value == "주식회사" or value in LABEL_VALUE_KEEP:
        return match.group(0)
    return match.group(1) + HOLDER


def _info_name_like(match: re.Match[str]) -> bool:
    """'이름 [전화]' 꼴의 앞말이 이름인가 — 주소 표시 앞이면 지역 낱말(○○구 · ○○동)은 이름이 아니다."""
    word = match.group(1)
    regional = match.group(2) is None and word.endswith(REGION_SUFFIXES)
    return _looks_like_name(word) and not regional


def _reservation_value(match: re.Match[str]) -> str:
    """예약 정보 꼴의 앞 칸 — 흔한 말 · 지역(서울 · ○○시)이면 그대로."""
    word = match.group(2)
    if _is_common_word(word) or word in METRO_SET:
        return match.group(0)
    return match.group(1) + NAME


def _name_only_line(match: re.Match[str]) -> str:
    """한 줄 전체가 이름 꼴이면 그 이름만 [이름]."""
    if not _looks_like_name(match.group(2)):
        return match.group(0)
    return match.group(1) + NAME + match.group(3) + match.group(4)


def _mask_people(text: str, staff_given: Sequence[str]) -> str:
    """사람 이름 — 호칭 앞 · 입니다 앞 · 예금주 · 직원 이름 · 이름표 · 연락처 앞 · 예약 정보 · 이름만 쓴 줄."""
    text = _NAME_BEFORE_TITLE.sub(_name_if_like, text)
    text = _NAME_BEFORE_HONORIFIC.sub(_name_if_like, text)
    text = _NAME_BEFORE_COPULA.sub(_name_if_like, text)
    text = _ACCOUNT_HOLDER.sub(_holder_value, text)
    if staff_given:
        given = "|".join(re.escape(n) for n in staff_given)
        text = re.sub(f"(?:{given}){_STAFF_TITLES}", STAFF, text)
    text = _NAME_AFTER_LABEL.sub(_label_value, text)
    text = _NAME_AFTER_COLON_LABEL.sub(
        lambda m: m.group(1) + NAME if _looks_like_name(m.group(2)) else m.group(0), text
    )
    text = _NAME_BEFORE_INFO.sub(lambda m: NAME if _info_name_like(m) else m.group(0), text)
    text = _RESERVATION_NAME.sub(_reservation_value, text)
    return _NAME_ONLY_LINE.sub(_name_only_line, text)


def _mask_complexes(text: str) -> str:
    """단지 이름(붙여 쓴 꼴 · 띄어 쓴 꼴 · 브랜드만) · 단지 뒤 줄여 쓴 동 · 호."""
    text = _COMPLEX_ATTACHED.sub(COMPLEX, text)
    text = _COMPLEX_SPACED.sub(lambda m: m.group(0) if _apt_keep(m.group(1)) else COMPLEX, text)
    text = _COMPLEX_BRAND_ONLY.sub(COMPLEX, text)
    return _COMPLEX_UNIT_SHORT.sub(lambda m: m.group(1) + UNIT, text)


def mask(text: str, *, customer_names: Iterable[str] = (), staff_names: Iterable[str] = ()) -> str:
    """상담 글 하나를 가린다(글마다 따로 — 여러 글을 이어 붙이면 '이름만 쓴 글' 규칙이 빗나간다).

    Args:
        text: 상담 글 하나(손님 · 직원 공개 글).
        customer_names: 그 상담 손님의 프로필 이름들 — 글 속 같은 글자를 모두 [이름]으로(성 뺀 이름 포함).
        staff_names: 직원 이름들 — 글 속 같은 글자는 [직원이름], 성 뺀 이름은 직함 앞에서만. 저장소에 두지 않고
            부르는 쪽이 넘긴다.

    Returns:
        가린 글(보이지 않는 서식 글자는 지우고 ASCII 아닌 숫자는 ASCII 로). 같은 글을 두 번 가려도 결과가 같다.
    """
    if not text:
        return ""
    customers = tuple(customer_names or ())
    staff = _clean_names(staff_names or ())
    staff_given = sorted({n[1:] for n in staff if re.fullmatch(r"[가-힣]{3}", n)}, key=len, reverse=True)
    text = _replace_known_names(_normalize(text), customers, staff)
    text = mask_contacts(text)
    text = _mask_addresses(text)
    text = _mask_people(text, staff_given)
    return _mask_complexes(text)


# ── 가림 검사 ──────────────────────────────────────────────────────────────
#: '이름꼴' — 세 글자 이름 꼴 + 빗금 · 쉼표, 그 뒤가 줄 끝 · 글 끝 · 숫자 · 가림 표시 · 지역(예약 정보가 늘 이 자리에 있었다).
#: PC 시범의 '말뭉치에 20번 안 된 낱말'을 이 문맥 + :func:`_looks_like_name`(고정 흔한 말 목록 · 끝 글자)으로 바꿨다.
_LEAK_NAME_BEFORE_SEPARATOR = re.compile(
    rf"(?<![가-힣])({_SUR}[가-힣]{{2}})\s?[/,](?=[ \t]*(?:\r|\n|$|[\[\d+]|{_REGION_NEXT}))"
)
#: '이름꼴' — 이름표 + 쌍점 + 이름(PC 시범이 학습 기록에 쓰던 꼴).
_LEAK_NAME_AFTER_LABEL = re.compile(
    rf"(?:명|성함|고객|계약자|예약자|이름|입금자|예금주|주문자|수령인)\s*[:：]\s*({_SUR}[가-힣]{{2}})(?![가-힣])"
)
#: '이름꼴' — 세 글자 이름 + 님 · 씨 · 고객님(서버판). '○○님' 가림의 호칭 목록 예외(이사 · 원장 …)에 걸린 이름도 센다.
_LEAK_NAME_BEFORE_TITLE = re.compile(rf"(?<![가-힣])({_SUR}[가-힣]{{2}})(?=\s?(?:님|씨|고객님))")
_LEAK_NAME_SHAPES = (
    _LEAK_NAME_BEFORE_SEPARATOR, _LEAK_NAME_AFTER_LABEL, _LEAK_NAME_BEFORE_TITLE,
    _NAME_BEFORE_HONORIFIC, _NAME_BEFORE_COPULA,
)
#: '단지꼬리' — [단지명] 바로 뒤에 붙은 글자. 조사 · 맺음뿐이면 꼬리가 아니다(서버판 — '[단지명]에서').
_LEAK_COMPLEX_TAIL = re.compile(r"\[단지명\]([가-힣A-Za-z]{2,})")
_COMPLEX_TAIL_PARTICLES = re.compile(f"(?:{COMPLEX_TAIL_PARTICLE_ALT})+")
#: '단지붙음' — 가리지 않은 붙여 쓴 단지 이름 · 브랜드(서버판 — 가림을 건너뛴 글을 막는다).
_LEAK_COMPLEX = re.compile(f"(?:{_COMPLEX_ATTACHED.pattern})|(?:{_COMPLEX_BRAND_ONLY.pattern})")


def _complex_tail_leaks(body: str) -> int:
    """[단지명] 뒤 꼬리 — 열 글자 안의 조사 · 맺음뿐이면 세지 않는다(긴 덩어리는 늘 센다)."""
    tails = (m.group(1) for m in _LEAK_COMPLEX_TAIL.finditer(body))
    return sum(1 for t in tails if not (len(t) <= 10 and _COMPLEX_TAIL_PARTICLES.fullmatch(t)))


def _name_leaks(body: str) -> int:
    """이름 꼴 — 예약 정보 문맥 · 이름만 쓴 줄 · 이름표 뒤 · 호칭 · 입니다 · 라고 앞 · 연락처 앞. 같은 자리는 한 번만 센다."""
    hits = {m.start(2) for m in _NAME_ONLY_LINE.finditer(body) if _looks_like_name(m.group(2))}
    hits |= {m.start(2) for m in _NAME_AFTER_LABEL.finditer(body) if m.group(2) not in LABEL_VALUE_KEEP
             and _looks_like_name(m.group(2))}
    hits |= {m.start(1) for m in _NAME_BEFORE_INFO.finditer(body) if _info_name_like(m)}
    for rx in _LEAK_NAME_SHAPES:
        hits |= {m.start(1) for m in rx.finditer(body) if _looks_like_name(m.group(1))}
    return len(hits)


def leak_counts(text: str) -> dict[str, int]:
    """가린 글에 남은 개인정보 꼴을 칸별로 센다(글은 돌려주지 않는다 — 숫자만 보고 · 경보에 싣는다).

    PC 시범 queue_pii_check 의 칸(호수 · 전화 · 도로 · 단지꼬리 · 단지띄움 · 이름꼴)에 서버판 칸(번호 · 메일 · 링크 ·
    지번 · 단지붙음)을 더했다 — 가림을 건너뛴 글도 막는다. 가림이 남기기로 한 말(치수 · 지역 · 흔한 말)은 같은 판정으로 뺀다.
    전화 · 번호 · 메일 · 링크 칸은 :func:`.masking_contacts.contact_leaks` (가림 규칙이 바꿀 자리 수).

    Returns:
        칸 이름 → 개수. 모두 0 이어야 모델에 보낸다(:func:`require_masked`).
    """
    body = _normalize(text or "")
    return {
        "호수": len(_HOSU.findall(body)),
        **contact_leaks(body),
        "도로": sum(1 for m in _ROAD.finditer(body) if not _road_kept(m)),
        "지번": sum(1 for m in _LOT.finditer(body) if not _lot_kept(m)),
        "단지붙음": len(_LEAK_COMPLEX.findall(body)),
        "단지꼬리": _complex_tail_leaks(body),
        "단지띄움": sum(1 for m in _COMPLEX_SPACED.finditer(body) if not _apt_keep(m.group(1))),
        "이름꼴": _name_leaks(body),
    }


class MaskLeak(ValueError):
    """가린 글에 개인정보 꼴이 남아 모델을 부르지 않는다. 메시지 · :attr:`counts` 엔 칸별 숫자만(글 · 이름 없음)."""

    def __init__(self, counts: Mapping[str, int]) -> None:
        self.counts = {key: int(value) for key, value in counts.items() if value}
        summary = " · ".join(f"{key} {value}" for key, value in self.counts.items())
        super().__init__(f"가림 검사 0 아님 — {summary}")


def require_masked(text: str) -> str:
    """가림 검사가 0 이면 글을 그대로 돌려주고, 한 칸이라도 0 이 아니면 :class:`MaskLeak`(모델에 보낼 글은 반드시 거친다)."""
    counts = leak_counts(text)
    if any(counts.values()):
        raise MaskLeak(counts)
    return text


def call_with_masked(
    messages: Sequence[str],
    call: Callable[[list[str]], T],
    *,
    customer_names: Iterable[str] = (),
    staff_names: Iterable[str] = (),
) -> T:
    """정한 순서: 글마다 가림 → 가림 검사 0 → 그때만 ``call(가린 글 목록)``. 검사가 0 이 아니면 부르지 않는다.

    Args:
        messages: 상담 글 목록(글마다 따로 가린다). 글 하나(str)는 거절 — 글자마다 가리게 된다.
        call: 가린 글 목록을 받는 모델 호출(두뇌). customer_names · staff_names 는 :func:`mask` 와 같다.

    Returns:
        ``call`` 의 반환값.

    Raises:
        TypeError: ``messages`` 가 글 하나. MaskLeak: 가린 뒤에도 꼴이 남음(칸별 숫자를 더해 한 번에).
    """
    if isinstance(messages, (str, bytes)):
        raise TypeError("messages 는 글 목록이다 — 글 하나를 넘기면 글자마다 따로 가린다")
    names, staff = tuple(customer_names or ()), tuple(staff_names or ())
    masked = [mask(item, customer_names=names, staff_names=staff) for item in messages]
    total: dict[str, int] = {}
    for item in masked:
        for key, value in leak_counts(item).items():
            total[key] = total.get(key, 0) + value
    if any(total.values()):
        raise MaskLeak(total)
    return call(masked)
