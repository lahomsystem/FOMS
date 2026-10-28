"""가림 — 연락처 · 번호 쪽(링크 · 전자 우편 · 전화 · 주민등록번호 · 계좌 · 카드)과 맞추기.

:mod:`foms.services.cs_agent.masking` 이 부른다(R6 검수 때 파일을 나눴다 — 500줄 상한). 규칙마다 가림과 검사가 같은 판정을
쓴다: :func:`mask_contacts` 가 바꾸는 자리를 :func:`contact_leaks` 가 센다. 치수 · 가격 · 날짜 줄은 남긴다(:func:`looks_like_sizes`).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Callable, Optional

from foms.services.cs_agent.masking_words import MONEY_CONTEXT_ALT

PHONE, NUMBER, MAIL = "[전화]", "[번호]", "[메일]"

# ── 맞추기(R6-9) ───────────────────────────────────────────────────────────
#: 보이지 않는 서식 글자(폭 없는 공백 · 결합 · 방향 표시 · 소프트 하이픈)의 번호표 — 번호 사이에 끼면 꼴이 깨진다. 지운다.
_INVISIBLE = dict.fromkeys([0x00AD, *range(0x200B, 0x2010), *range(0x202A, 0x202F), *range(0x2060, 0x2065),
                            *range(0x2066, 0x206A), 0xFEFF])
#: ASCII 아닌 숫자(전각 '０' 등)는 ASCII 로. 글 전체 NFKC 는 쓰지 않는다 — 자모 'ㅋ'까지 바뀌어 뜻이 달라진다.
_NON_ASCII_DIGIT = re.compile(r"(?![0-9])\d")


def normalize(text: str) -> str:
    """가림 · 검사 앞 맞추기 — 보이지 않는 서식 글자를 지우고 ASCII 아닌 숫자를 ASCII 로 바꾼다."""
    text = text.translate(_INVISIBLE)
    return _NON_ASCII_DIGIT.sub(lambda m: str(unicodedata.decimal(m.group(0))), text)


# ── 꼴 ─────────────────────────────────────────────────────────────────────
#: 숫자 사이 구분 글자 — 낱말 글자가 아닌 것 + 밑줄 · 자모 'ㅡ' · 한자 '一' · 장음 'ー'(R6-9).
SEP = r"(?:\W|[_ㅡ一ー])"
#: 링크는 도메인만 남긴다(경로 · 물음표 뒤에 손님 정보가 실릴 수 있다).
_LINK = re.compile(r"https?://[^\s)>\]]+")
_LINK_HOST = re.compile(r"[A-Za-z0-9.-]+")
#: 전자 우편 주소. 앞 칸은 64자까지 ASCII 만 — 앞 경계 없이도 길이에 비례하고, 앞뒤 한글을 먹지 않는다(R6-13 멱등).
_MAIL = re.compile(r"[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
#: 휴대폰(+82 꼴 포함). 앞 숫자 경계는 서버판에서 더함 — 숫자 뒤에 이어 쓴 치수 줄 속 '01…'을 전화로 가리지 않는다.
_PHONE_MOBILE = re.compile(r"(?<!\d)(?:\+?82[-. ]?)?0?1[016789][-. ]?\d{3,4}[-. ]?\d{4}")
#: 휴대폰 넓은 꼴 — 010 · o1o · +82 10 으로 시작해 숫자 10~11개, 숫자 사이 구분 글자 0~3개(R6-9 · 옛 띄어 쓴 꼴을 넓힘).
#: 앞 세 자리는 붙여(또는 한 칸씩 띄어) 써야 한다 — '01.05 9:30~10:00' 같은 날짜 · 시각 줄을 전화로 보지 않는다.
_PHONE_WIDE = re.compile(
    rf"(?:(?<!\d)\+?\s?82{SEP}{{0,3}}(?:\(?0\)?{SEP}{{0,2}})?1|(?<!\d)0\s?1|(?<![\dA-Za-z])[oO]\s?1)\s?[016789oO]"
    rf"(?:{SEP}{{0,3}}\d){{7,8}}(?!\d)"
)
#: 집 · 회사 전화. 한글에 붙은 번호('전화02-…')도 잡게 숫자 경계를 쓰고, 구분 글자는 넓은 꼴(R6-9).
_PHONE_LANDLINE = re.compile(rf"(?<!\d)0\d{{1,2}}{SEP}{{1,3}}\d{{3,4}}{SEP}{{1,3}}\d{{4}}(?!\d)")
#: 붙여 쓴 서울 집 전화 9자리('02' + 7자리, R6-10). 열 자리 넘는 번호는 :data:`_LONG_NUMBER`.
_PHONE_SEOUL9 = re.compile(r"(?<!\d)02\d{7}(?!\d)")
#: PC 시범 검사의 휴대폰 꼴(줄바꿈 · 탭으로 끊은 꼴) — 검사에서만 센다.
_LEAK_MOBILE = re.compile(r"(?<!\d)01[016789][\s\-.]?\d{3,4}[\s\-.]?\d{4}")
#: 주민 · 외국인등록번호 꼴 '6자리-7자리'(뒤 첫 자리 1~8, R6-10).
_RESIDENT_NUMBER = re.compile(rf"(?<!\d)\d{{6}}{SEP}{{1,3}}[1-8]\d{{6}}(?!\d)")
#: 줄표로 이은 번호(계좌 · 안심번호). 날짜('2026-10-28')는 뺀다. 줄표로 이은 치수도 가린다 — 계좌가 새는 쪽보다 낫다.
_DASHED_NUMBER = re.compile(r"(?<!\d)(?!(?:19|20)\d\d-\d{1,2}-\d{1,2}(?!\d))\d{2,6}-\d{2,6}-\d{2,8}(?:-\d{1,4})?(?!\d)")
#: 열 자리 넘는 숫자(계좌 · 붙여 쓴 번호).
_LONG_NUMBER = re.compile(r"(?<!\d)\d{10,}(?!\d)")
#: 띄어 쓴 카드 번호 — 네 자리 넷(또는 4-6-5). 앞말 없이 따로 보낸 글도 잡는다(직원이 앞 글에서 물으면 손님은 번호만 쓴다).
_CARD_BARE = re.compile(rf"(?<!\d)\d{{4}}(?:(?:{SEP}{{1,3}}\d{{4}}){{3}}|{SEP}{{1,3}}\d{{6}}{SEP}{{1,3}}\d{{5}})(?!\d)")
#: 숫자 묶음 하나(구분 글자 1~3개) — 늘 묶음 전체를 집어 줄 길이에 비례한다. 계좌인지는 :func:`_digit_run` 이 가린다.
_DIGIT_RUN = re.compile(rf"(?<!\d)\d+(?:{SEP}{{1,3}}\d+)*(?!\d)")
#: 묶음 앞 · 뒤 15자 안의 계좌 · 카드 앞말('농협 302 …' · '… 농협', R6-10).
_CONTEXT_BEFORE = re.compile(rf"(?:{MONEY_CONTEXT_ALT})[^\n\d]{{0,15}}$")
_CONTEXT_AFTER = re.compile(rf"[^\n\d]{{0,15}}(?:{MONEY_CONTEXT_ALT})")
_PRICE = re.compile(r"\d{1,3}(?:,\d{3})+")
_DATE_HEAD = re.compile(r"(?:19|20)\d\d\W\d{1,2}\W\d{1,2}(?!\d)")


def looks_like_sizes(groups: list[str]) -> bool:
    """숫자 묶음이 치수 꼴인가 — 묶음마다 네 자리 이하이고 0 · 5 로 끝난다(가로 · 세로 · 높이 mm 값)."""
    return bool(groups) and all(len(g) <= 4 and g[-1] in "05" for g in groups)


def _is_account_like(run: str) -> bool:
    """앞말 곁 숫자 묶음이 번호인가 — 숫자 아홉 개 넘음, 치수 · 천 단위 가격 · 날짜로 시작하는 줄은 아니다."""
    groups = re.findall(r"\d+", run)
    if sum(map(len, groups)) < 9 or _PRICE.fullmatch(run) or _DATE_HEAD.match(run):
        return False
    return not looks_like_sizes(groups)


def _link_token(match: re.Match[str]) -> str:
    """링크 → ``[링크:도메인]`` (사용자 · 포트 · 경로 · 물음표 뒤는 버린다)."""
    rest = match.group(0).split("://", 1)[1]
    host = re.split(r"[/?#]", rest, maxsplit=1)[0].rsplit("@", 1)[-1]
    found = _LINK_HOST.match(host)
    return f"[링크:{found.group(0) if found else ''}]"


def _card(match: re.Match[str]) -> Optional[str]:
    """띄어 쓴 카드 번호 — 네 묶음이 모두 치수 꼴(네 자리 · 0 · 5 끝 — 벽 둘의 가로 · 세로)이면 남긴다."""
    return None if looks_like_sizes(re.findall(r"\d+", match.group(0))) else NUMBER


def _digit_run(match: re.Match[str]) -> Optional[str]:
    """숫자 묶음 — 앞뒤 15자 안에 계좌 · 카드 앞말이 있으면 :func:`_is_account_like`, 없으면 앞말 없는 계좌 꼴만 가린다.

    앞말 없는 계좌 꼴: 묶음 둘 넘게 · 숫자 10~16개 · 다섯 자리 넘는 묶음이 있음(치수 값은 네 자리 이하) · 가격 꼴 아님.
    """
    run = match.group(0)
    before = match.string[max(0, match.start() - 24):match.start()]
    if _CONTEXT_BEFORE.search(before) or _CONTEXT_AFTER.match(match.string, match.end()):
        return NUMBER if _is_account_like(run) else None
    groups = re.findall(r"\d+", run)
    bare = len(groups) >= 2 and 10 <= sum(map(len, groups)) <= 16 and max(map(len, groups)) >= 5
    return NUMBER if bare and not _PRICE.fullmatch(run) else None


Repl = Callable[[re.Match[str]], Optional[str]]
#: (검사 칸, 꼴, 바꿀 글 — None 이면 남김). 위에서부터 차례로 가린다 — 검사는 같은 판정으로 센다.
_RULES: tuple[tuple[str, re.Pattern[str], Repl], ...] = (
    ("링크", _LINK, _link_token),
    ("메일", _MAIL, lambda m: MAIL),
    ("전화", _PHONE_WIDE, lambda m: PHONE),  # 넓은 꼴 먼저 — '+82 (0)10…' 전체를 한 번에(좁은 꼴이 뒤 조각만 집지 않게)
    ("전화", _PHONE_MOBILE, lambda m: PHONE),
    ("전화", _PHONE_LANDLINE, lambda m: PHONE),
    ("전화", _PHONE_SEOUL9, lambda m: PHONE),
    ("번호", _RESIDENT_NUMBER, lambda m: NUMBER),
    ("번호", _DASHED_NUMBER, lambda m: NUMBER),
    ("번호", _LONG_NUMBER, lambda m: NUMBER),
    ("번호", _CARD_BARE, _card),
    ("번호", _DIGIT_RUN, _digit_run),
)


def mask_contacts(text: str) -> str:
    """링크 · 전자 우편 · 전화 · 주민등록번호 · 긴 번호 · 카드 · 계좌 번호를 가린다(맞춘 글을 받는다)."""
    for _, rx, repl in _RULES:
        text = rx.sub(lambda m, repl=repl: repl(m) or m.group(0), text)
    return text


def contact_leaks(body: str) -> dict[str, int]:
    """전화 · 번호 · 메일 · 링크 칸 — 가림 규칙이 바꿀 자리 수(같은 숫자 자리는 한 번). PC 시범 휴대폰 꼴도 센다."""
    found: dict[str, set[int]] = {"전화": {m.start() for m in _LEAK_MOBILE.finditer(body)}, "번호": set(), "메일": set(),
                                  "링크": set()}
    for kind, rx, repl in _RULES:
        found[kind] |= {m.start() for m in rx.finditer(body) if repl(m)}
    return {kind: len(spots) for kind, spots in found.items()}
