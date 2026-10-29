"""보내기 전 검사의 '읽기' 쪽 — 글 맞추기 · 링크 집 · 숫자 · 금액 · 날짜 · 전화/계좌 꼴을 읽는다(판정은 :mod:`.checks`).

플랜 ``docs/plans/2026-10-27-cs-ai-agent-plan.md`` C2-2 허용 목록(원장 R1-11): 초안 속 숫자 · 금액 · 날짜는 계산기 ·
확정 값과 같을 때만 통과한다. 그러려면 '십오만 원' · '15 만원' · '15.0만' · '150,000원' · '₩150000' 이 모두 150000 으로
읽혀야 한다 — 그 규칙이 여기 있다. 허용 목록 글(계산기 결과 · 승인 지식)도 같은 함수로 읽으므로 같은 꼴은 늘 같은 값이다.
숫자마다 종류(금액 · 비율 · 수)와 단위(개 · 시 · 일 · cm …)도 읽는다 — '서랍 3개' 가 '3시' 를 통과시키지 않게(R6-5).

순수 함수다(네트워크 · DB 없음). 글은 :func:`normalize` 를 거친 뒤 읽는다.
"""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal
from typing import Iterable, NamedTuple, Optional

__all__ = [
    "NON_DIGIT", "NOT_FRACTION", "TIME_UNITS", "Found", "blank", "clean_host", "host_allowed", "id_code", "normalize",
    "read_numbers", "sentence_after", "split_links", "squash",
]

# ── 글 맞추기 ────────────────────────────────────────────────────────────
#: 동그라미 숫자(①, ② …) — 목록 표시라 숫자로 읽지 않는다(NFKC 가 1 로 바꾸기 전에 뺀다).
_CIRCLED = re.compile(f"[{chr(0x2460)}-{chr(0x2473)}{chr(0x2776)}-{chr(0x2793)}]")
#: 한자로 쓴 숫자 단위(꼴마다 두 가지 — 만 · 천 · 백 · 억)를 한글 단위로 바꿔 같은 값으로 읽는다.
_HANJA_UNITS = str.maketrans(
    {chr(0x842C): "만", chr(0x4E07): "만", chr(0x5343): "천", chr(0x767E): "백", chr(0x5104): "억", chr(0x4EBF): "억"}
)
#: 견주기용 글자(한글 · 영문 · 숫자) 밖의 것 — 비공개 메모 · 예시 낱말을 견줄 때 지운다.
_NOT_WORD_CHAR = re.compile(r"[^0-9a-z가-힣]")
#: 숫자 아닌 글자 — 전화 · 계좌 꼴 묶음은 숫자만으로 견준다.
NON_DIGIT = re.compile(r"\D")
#: 문장 끝 — 약속 꼴 뒤를 볼 때 여기서 자른다.
_SENTENCE_END = re.compile(r"[.!?\n]")


def normalize(text: Optional[str]) -> str:
    """검사용 글: 동그라미 숫자 빼기 → NFKC → 서식 글자(Cf · 폭 없는 공백 등) 빼기 → 다른 글자의 숫자를 0-9 로 → 한자 단위를 한글로.

    Args:
        text: 초안 · 허용 목록 글 · 비공개 메모. None 은 빈 글.

    Returns:
        같은 뜻의 글(줄바꿈은 그대로).
    """
    body = unicodedata.normalize("NFKC", _CIRCLED.sub(" ", text or ""))
    chars = (
        str(unicodedata.decimal(ch)) if ch.isdecimal() and not ch.isascii() else ch
        for ch in body
        if unicodedata.category(ch) != "Cf"
    )
    return "".join(chars).translate(_HANJA_UNITS)


def squash(text: str) -> str:
    """한글 · 영문 · 숫자만 남긴 소문자 글 — 띄어쓰기 · 문장부호가 달라도 같은 말로 견준다."""
    return _NOT_WORD_CHAR.sub("", text.lower())


def is_hangul(ch: str) -> bool:
    """한글 음절 한 글자인가."""
    return bool(ch) and "가" <= ch <= "힣"


def blank(body: str, m: re.Match[str]) -> str:
    """맞은 자리를 같은 길이 빈칸으로 바꾼다 — 다른 규칙이 두 번 읽지 않게, 다른 자리는 그대로."""
    return _blank_spans(body, [m.span()])


def _blank_spans(body: str, spans: list[tuple[int, int]]) -> str:
    """여러 자리(앞에서부터 겹치지 않는)를 한 번에 빈칸으로 — 긴 글에서 자리마다 글을 새로 만들지 않게."""
    if not spans:
        return body
    parts: list[str] = []
    last = 0
    for start, end in spans:
        parts += [body[last:start], " " * (end - start)]
        last = end
    return "".join(parts) + body[last:]


def sentence_after(body: str, end: int, size: int) -> str:
    """``end`` 뒤 ``size`` 자 — 문장 끝(. ! ? 줄바꿈)에서 자른다."""
    window = body[end:end + size]
    cut = _SENTENCE_END.search(window)
    return window[: cut.start()] if cut else window


# ── 링크 ─────────────────────────────────────────────────────────────────
#: 링크 이름에 쓰는 글자 — 영문과, 닮은꼴로 쓰이는 라틴 확장 · 그리스 · 키릴 글자(한글은 아님, R6-7).
_LETTERS = f"a-z{chr(0xC0)}-{chr(0x24F)}{chr(0x370)}-{chr(0x3FF)}{chr(0x400)}-{chr(0x52F)}"
#: 링크 이름 마디 한 글자(글자 · 숫자 · 붙임표).
_LABEL = rf"[{_LETTERS}0-9\-]"
#: 점 · 돌려 쓴 점(' . ' · '[.]' · '(.)' · '(dot)' · '。' · '점' · '닷').
_DOT = r"\s?(?:\.|\[\.\]|\(\.\)|\(dot\)|\[dot\]|。|점|닷)\s?"
#: 돌려 쓴 점을 '.' 으로 바꿀 때 쓴다.
_DOT_RE = re.compile(_DOT)
#: 돌려 쓴 점 뒤에서 링크로 보는 알려진 끝 이름('컴' 은 '닷컴 · 점컴' 꼴). 붙여 쓴 점 뒤는 글자 끝 이름이면 모두 링크다.
_TLD_KNOWN = r"(?:com|net|org|kr|co|me|ly|io|gl|to|app|page|link|site|shop|store|xyz|info|biz|tv|gg|ai|so|cc|dev|online|컴)"
#: 역슬래시 — 브라우저는 앞말 링크의 역슬래시를 '/' 로 본다(집 이름이 거기서 끝난다, R6-7).
_BS = re.escape(chr(92))
#: 'http(s)://' · 'hxxp://' 로 시작하는 링크 — 집은 첫 '/ ? #' · 역슬래시 앞, 그 안에서 '@' 뒤 · ':' 앞.
_SCHEME_LINK = re.compile(rf"h(?:tt|xx)ps?\s?:\s?//\s?(?P<auth>[^\s/{_BS}?#]+)\S*", re.I)
#: 앞말 없는 링크(붙여 쓴 점) — 끝 이름이 글자 2개 이상이면 링크다('.dev · .online' · 키릴 닮은꼴도). 마디 수 · 길이에 상한.
_TIGHT_LINK = re.compile(
    rf"(?<!{_LABEL})(?P<host>(?:{_LABEL}{{1,63}}[.。]){{1,8}}[{_LETTERS}]{{2,63}})(?!{_LABEL})(?:/\S*)?", re.I
)
#: 돌려 쓴 점('naver . me' · 'kakao 점 com' · 'kakao닷컴') — 알려진 끝 이름만(띄어 쓴 문장 끝 '.' 뒤 영어 낱말은 아님).
_LOOSE_LINK = re.compile(rf"(?<!{_LABEL})(?P<host>(?:{_LABEL}{{1,63}}{_DOT}){{1,8}}{_TLD_KNOWN})(?!{_LABEL})(?:/\S*)?", re.I)
#: 한글 이름 + 닷컴 · '.com'(한글 도메인) — 집에 한글이 있으니 허용 집이 아니다.
_HANGUL_LINK = re.compile(r"(?P<host>[가-힣]{2,20}(?:닷컴|닷넷|\.(?:com|net|org|kr)))(?![a-z0-9])", re.I)
#: 앞말 링크의 길 시작(/ ? # · 역슬래시) — 집 이름은 그 앞에서 끝난다.
_PATH_START = re.compile(rf"[/{_BS}?#]")


def clean_host(raw: str) -> str:
    """링크 집 이름 맞추기 — 소문자 · 앞말(://) · 길(/ ? # · 역슬래시) · 돌려 쓴 점 → '.' · '컴' → com · 사용자(@ 앞) · 포트 · 'www.'."""
    rest = raw.strip().lower().split("://")[-1]
    host = _DOT_RE.sub(".", _PATH_START.split(rest, 1)[0]).replace("컴", "com")
    host = host.rsplit("@", 1)[-1].split(":", 1)[0].strip(".")
    return host[4:] if host.startswith("www.") else host


def host_allowed(host: str, allowed: Iterable[str]) -> bool:
    """집이 허용 집과 같거나 그 아래 집인가('m.smartstore.naver.com' 은 'smartstore.naver.com' 아래)."""
    return any(host == a or host.endswith("." + a) for a in allowed)


def split_links(body: str) -> tuple[list[str], str]:
    """링크 집 목록과, 링크 자리를 빈칸으로 바꾼 글(링크 속 숫자를 금액으로 읽지 않게)."""
    hosts: list[str] = []
    for pattern in (_SCHEME_LINK, _TIGHT_LINK, _LOOSE_LINK, _HANGUL_LINK):
        spans = []
        for m in pattern.finditer(body):
            hosts.append(clean_host(m.group(1)))
            spans.append(m.span())
        body = _blank_spans(body, spans)
    return hosts, body


# ── 숫자 · 금액 · 날짜 · 전화/계좌 꼴 ─────────────────────────────────────
_KO_DIGIT = {"일": 1, "이": 2, "삼": 3, "사": 4, "오": 5, "육": 6, "칠": 7, "팔": 8, "구": 9}
_SMALL = {"십": 10, "백": 100, "천": 1000}
_BIG = {"만": 10**4, "억": 10**8, "조": 10**12}
#: 한글 숫자 말이 시작될 수 있는 글자(앞 글자가 한글이 아닐 때만 — '사진만' · '실측일' 은 아님).
_KO_START = frozenset("일이삼사오육칠팔구십백천만억")
#: 한글 숫자만으로 된 말이 '원' 없이도 금액인 첫 글자('십오만 정도'). '만 · 백 · 천' 으로 시작하면 낱말이 많다('만약' · '천만에요').
_KO_LEAD = frozenset("일이삼사오육칠팔구십")
#: '원' 없이는 숫자로 보지 않는 한글 말('이만 마치겠습니다' · '일만 하시면').
_KO_WORDS = frozenset({"이만", "일만"})
_KD = "[일이삼사오육칠팔구]"
#: 숫자 덩어리 — '15' · '150,000' · '15.5' 뒤에 '천 · 백 · 십'(낱말 첫 글자가 아닐 때 — '2400 천장' 은 아님)과 '만 · 억 · 조'.
_DIGIT_CHUNK = re.compile(
    r"(?P<d>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?:\s?(?P<s>[천백십])(?=[만억조원이은는을를에도정쯤가대짜]|[^가-힣]|$))?(?:\s?(?P<b>[만억조]))?"
)
#: 한글 숫자 덩어리 — '십오' · '오천' · '삼백오십' 뒤에 '만 · 억 · 조'('만' 하나만도 된다 — '만 원').
_KO_CHUNK = re.compile(rf"(?P<k>(?:{_KD}?천)?(?:{_KD}?백)?(?:{_KD}?십)?{_KD}?)(?P<b>[만억조])?")
#: 금액 끝말 '원'.
_WON = re.compile(r"\s?원")
#: 비율 끝말 — 배 · % · 퍼센트 · 프로(사람만 말하는 항목의 배수도 막을 수 있게 따로 센다, D17).
_RATIO = re.compile(r"\s?(?:배|%|퍼센트|프로)")
#: 숫자 뒤 단위 낱말 — 허용 목록은 값 · 종류와 함께 이것도 견준다(R6-5).
_UNIT_WORD = re.compile(
    r"\s?(시간|개월|주일|시|분|초|일|주|월|년|개|장|층|명|세트|칸|단|짝|평|인치|mm|cm|m|미리|밀리|센치|센티|kg|키로)(?![a-z])", re.I
)
#: 같은 단위의 다른 이름.
_UNIT_ALIAS = {"미리": "mm", "밀리": "mm", "센치": "cm", "센티": "cm", "키로": "kg"}
#: 때 단위 — 허용 목록에서 같은 단위끼리만 맞는다('서랍 3개' 는 '3시' 를 허용하지 않는다, R6-5).
TIME_UNITS = frozenset({"시", "시간", "분", "초", "일", "주", "주일", "월", "개월", "년"})
#: 돈 표시 앞말 — 뒤 숫자는 금액이다.
_CURRENCY = re.compile(r"(?:₩|KRW)\s?", re.I)
#: 범위 사이 — '15~20만 원' 의 앞 숫자에 뒤 단위를 나눠 준다.
_RANGE_SEP = re.compile(r"\s?[~\-–]\s?")
#: 목록 표시 — 줄 첫머리 '1.' · '2)' 는 숫자로 읽지 않는다.
_LIST_MARK = re.compile(r"(?m)^[ \t]*\d{1,2}[.)](?=\s)")
#: 'a/b' 뒤에 이 말이 오면 날짜가 아니라 분수다('1/2 가격' — R6-20).
NOT_FRACTION = r"(?!\s?(?:가격|값|크기|사이즈|정도|분량|수준|만큼))"
#: 날짜 꼴 — '2026년 11월 3일' · '11월 3일' · '2026-11-03' · '2026.11.03' · '11/3'. 달 1~12 · 날 1~31 만 날짜다.
_DATE = re.compile(
    r"(?<!\d)(?:(?P<y>\d{4})\s?년\s?)?(?P<m>\d{1,2})\s?월\s?(?P<d>\d{1,2})\s?일"
    r"|(?<![\d.])(?P<y2>\d{4})\s?[-./]\s?(?P<m2>\d{1,2})\s?[-./]\s?(?P<d2>\d{1,2})(?!\d)"
    rf"|(?<![\d/.])(?P<m3>\d{{1,2}})/(?P<d3>\d{{1,2}})(?![\d/]){NOT_FRACTION}"
)
#: 분수 — 날짜로 읽히지 않은 'a/b'. 값은 a/b, 종류는 비율(R6-20).
_FRACTION = re.compile(r"(?<![\d/.])(\d{1,3})\s?/\s?(\d{1,3})(?![\d/])")
#: 전화 · 계좌 꼴 숫자 묶음 — 붙임표로 이은 묶음 · '0NN NNNN NNNN' 꼴 · 10자리 넘는 숫자(숫자 8개 이상만). 단위가 붙으면 범위다.
_DIGIT_ID = re.compile(
    r"(?<![\d.,])(?:\d{2,6}(?:\s?-\s?\d{2,8}){1,4}|0\d{1,2}[ .]\d{3,4}[ .]\d{4}|\d{10,16})(?![\d,])"
    r"(?!\s?(?:mm|cm|미리|센치|원|만|천|개|일|년|월|시|분|배|%))"
)
#: 계좌 앞말 — 이 말 뒤 12자 안의 숫자 묶음은 계좌 번호다.
_ACCOUNT_CONTEXT = re.compile(r"(?:계좌|입금|송금|이체|예금주|은행|뱅크)[^.!?\n]{0,12}$")
#: 전화 꼴(숫자만) — 0 으로 시작하는 9~11자리 · 15xx/16xx/18xx 대표 번호.
_PHONE_SHAPE = re.compile(r"0\d{8,10}|1[5-9]\d{6}")


class _Num(NamedTuple):
    """읽은 숫자 말 하나 — 값 · 종류 · 단위와, 범위 나눠 주기에 쓰는 자리 · 첫 곱수."""

    value: Decimal
    kind: str  # 'amount' | 'ratio' | 'number'
    unit: str  # '원' · '%' · '배' · '분수' · '개' · '시' … · '' (없음)
    start: int
    end: int
    mult: int  # 첫 덩어리 곱수 — 범위 앞 숫자에 나눠 줄 값


class Found(NamedTuple):
    """글 하나에서 읽은 것 — ``ids`` (숫자만, 계좌 앞말 있음) · ``dates`` (해 또는 None, 달, 날) · ``values`` (값, 종류, 단위)."""

    ids: list[tuple[str, bool]]
    dates: list[tuple[Optional[int], int, int]]
    values: list[tuple[Decimal, str, str]]


def _ko_value(text: str) -> int:
    """만 아래 한글 숫자 값 — '십오' 15 · '오천' 5000 · '' 0."""
    total, digit = 0, 0
    for ch in text:
        if ch in _KO_DIGIT:
            digit = _KO_DIGIT[ch]
        else:
            total, digit = total + (digit or 1) * _SMALL[ch], 0
    return total + digit


def _chunk_value(m: re.Match[str]) -> tuple[Decimal, int]:
    """덩어리 하나의 (밑값, 곱수). 한글 '만' 하나는 1 × 만."""
    if m.re is _DIGIT_CHUNK:
        base, unit = Decimal(m.group("d").replace(",", "")), _SMALL.get(m.group("s") or "", 1)
    else:
        base, unit = Decimal(_ko_value(m.group("k")) or 1), 1
    return base, unit * _BIG.get(m.group("b") or "", 1)


def _joins(body: str, prev_end: int, m: re.Match[str]) -> bool:
    """'만 · 억' 뒤 덩어리를 이을지 — 붙어 있거나, 제 곱수가 있거나, 뒤에 '원' 이 오면 잇는다('1만 5천 원' · '1만 5000원').

    '이 · 일' 한 글자 뒤에 한글이 오면 잇지 않는다('15만이에요' · '만일에').
    """
    text = m.group(0)
    if text in ("이", "일") and is_hangul(body[m.end():m.end() + 1]):
        return False
    if m.start() == prev_end or m.group("b") or any(ch in _SMALL for ch in text):
        return True
    return bool(_WON.match(body, m.end()))


def _kind_unit(body: str, end: int, money: bool) -> tuple[str, str]:
    """숫자 말의 종류 · 단위 — 금액(원 · 만 · 한글 금액) · 비율(% · 배) · 그 밖은 수(뒤 단위 낱말, 없으면 '')."""
    if money:
        return "amount", "원"
    ratio = _RATIO.match(body, end)
    if ratio:
        return "ratio", "배" if "배" in ratio.group(0) else "%"
    unit = _UNIT_WORD.match(body, end)
    if unit is None:
        return "number", ""
    word = unit.group(1).lower()
    return "number", _UNIT_ALIAS.get(word, word)


def _read_phrase(body: str, pos: int) -> Optional[tuple[Decimal, str, str, int, int]]:
    """``pos`` 의 숫자 말 하나 → (값, 종류, 단위, 끝, 첫 곱수). 덩어리는 '만 · 억' 뒤에서만 잇는다.

    한글 숫자만으로 된 말은 '원' 이 붙거나, '만 · 억' 을 품고 숫자 글자로 시작할 때만 숫자다
    ('사진만' · '천장' · '만약' · '이만 마치겠습니다' 는 숫자가 아니다).
    """
    total, at, end, first, digit_chunks, ko = Decimal(0), pos, pos, 0, [], ""
    while True:
        m = _DIGIT_CHUNK.match(body, at) or _KO_CHUNK.match(body, at)
        if m is None or m.end() == at or (first and not _joins(body, end, m)):
            break
        base, unit = _chunk_value(m)
        total, first, end = total + base * unit, first or unit, m.end()
        if m.re is _DIGIT_CHUNK:
            digit_chunks.append(m.group(0))
        else:
            ko += m.group(0)
        if not m.group("b"):
            break
        at = end + 1 if body[end:end + 1] == " " else end
    if not first:
        return None
    won = _WON.match(body, end)
    if not digit_chunks and not won and not (ko[:1] in _KO_LEAD and ko not in _KO_WORDS and any(b in ko for b in _BIG)):
        return None
    if won and first == 1 and len(digit_chunks) == 1 and "." in digit_chunks[0]:
        total = Decimal(NON_DIGIT.sub("", digit_chunks[0]))  # '150.000원' — 원에는 소수가 없으니 점은 자릿점이다
    kind, unit = _kind_unit(body, end, bool(won) or first > 1 or not digit_chunks)
    return total, kind, unit, (won.end() if won else end), first


def _scan_numbers(body: str) -> list[_Num]:
    """숫자 말을 앞에서부터 읽는다('₩ · KRW' 뒤는 금액). 한글 숫자는 앞 글자가 한글이 아닐 때만 시작한다."""
    found: list[_Num] = []
    i = 0
    while i < len(body):
        cur = _CURRENCY.match(body, i)
        at = cur.end() if cur else i
        ch = body[at:at + 1]
        got = None
        if ch.isdigit() or (ch in _KO_START and not is_hangul(body[max(at - 1, 0):at])):
            got = _read_phrase(body, at)
        if got is None:
            i += 1
            continue
        value, kind, unit, end, mult = got
        found.append(_Num(value, "amount" if cur else kind, "원" if cur else unit, at, end, mult))
        i = end
    return _spread_ranges(body, found)


def _spread_ranges(body: str, nums: list[_Num]) -> list[_Num]:
    """범위 '15~20만 원' · '5~7일' — 곱수 · 단위 없는 앞 숫자에 뒤 숫자의 곱수 · 종류 · 단위를 나눠 준다(15 → 15만, 5 → 5일)."""
    out = list(nums)
    for k in range(len(out) - 2, -1, -1):
        a, b = out[k], out[k + 1]
        if a.kind != "number" or a.mult != 1 or a.unit or not _RANGE_SEP.fullmatch(body[a.end:b.start]):
            continue
        if b.mult > 1 or b.unit:
            out[k] = a._replace(value=a.value * b.mult, kind=b.kind, unit=b.unit, mult=b.mult)
    return out


def read_numbers(body: str) -> Found:
    """링크를 뺀 맞춘 글에서 날짜 → 분수 → 전화 · 계좌 꼴 → 숫자 말 순으로 읽는다(읽은 자리는 빈칸 — 두 번 읽지 않게).

    Args:
        body: :func:`normalize` 를 거치고 :func:`split_links` 로 링크를 뺀 글.

    Returns:
        :class:`Found` — 날짜 · 숫자 묶음 · 숫자 값(한글 숫자 · '15 만원' · '₩150,000' 도 값 하나, 종류 · 단위와 함께).
    """
    body = _LIST_MARK.sub(lambda m: " " * len(m.group(0)), body)
    dates: list[tuple[Optional[int], int, int]] = []
    ids: list[tuple[str, bool]] = []
    values: list[tuple[Decimal, str, str]] = []
    spans: list[tuple[int, int]] = []
    for m in _DATE.finditer(body):
        month = int(m.group("m") or m.group("m2") or m.group("m3"))
        day = int(m.group("d") or m.group("d2") or m.group("d3"))
        if 1 <= month <= 12 and 1 <= day <= 31:
            year = m.group("y") or m.group("y2")
            dates.append((int(year) if year else None, month, day))
            spans.append(m.span())
    body, spans = _blank_spans(body, spans), []
    for m in _FRACTION.finditer(body):
        if int(m.group(2)):
            values.append((Decimal(int(m.group(1))) / Decimal(int(m.group(2))), "ratio", "분수"))
            spans.append(m.span())
    body, spans = _blank_spans(body, spans), []
    for m in _DIGIT_ID.finditer(body):
        digits = NON_DIGIT.sub("", m.group(0))
        if len(digits) >= 8:
            ids.append((digits, bool(_ACCOUNT_CONTEXT.search(body[max(0, m.start() - 16):m.start()]))))
            spans.append(m.span())
    body = _blank_spans(body, spans)
    return Found(ids, dates, values + [(n.value, n.kind, n.unit) for n in _scan_numbers(body)])


def id_code(digits: str, account_context: bool) -> str:
    """허용 안 된 숫자 묶음의 문제 코드 — 계좌 앞말이 있거나 전화 꼴이 아닌 10자리 넘는 묶음은 계좌, 전화 꼴은 전화."""
    phone = bool(_PHONE_SHAPE.fullmatch(digits))
    if account_context or (len(digits) >= 10 and not phone):
        return "account_number"
    return "phone_number" if phone else "number_not_allowed"
