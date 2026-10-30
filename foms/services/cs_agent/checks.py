"""보내기 전 검사 — AI 초안이 손님께 나가도 되는지 코드로 본다(LLM 아님).

플랜 ``docs/plans/2026-10-27-cs-ai-agent-plan.md`` C2-2 · 설계서 4절 6 · 7절(말투) · 2.6(톡톡).
순수 함수다: 네트워크 · DB · 채널톡이 없다. PC 시범 ``work/post_drafts.py`` 의 ``check_reply`` · ``NAVER_BANS`` ·
``tone_problems`` 를 옮겨 넓혔다 — 옮긴 꼴은 상수 주석에 '시범' 이라고 적었다.

- 막음(:attr:`CheckResult.problems`): 금지 꼴(:mod:`.checks_rules` — 다른 브랜드 · 할인 · 환불 · 날짜 확답 · 연락 시각 약속 ·
  내부 말 · 가림 표시 · 톡톡) · 허용 목록 밖 링크 · 허용 목록(초안 속 숫자 · 금액 · 날짜는 계산기 · 확정 값과 값 · 종류 ·
  단위가 같을 때만 통과 — 한글 숫자 · 띄어 쓴 금액도 같은 값으로 읽는다, 원장 R1-11 · R6-5) · 비공개 메모 문장 · 예시에만
  있는 낱말(R1-12 · R1-10).
- 알림만(:attr:`CheckResult.warnings`): 말투 꼴(이모지 여러 개 · 한 덩어리 120자 넘음 · 해요체 — D35 로 보류).
- 이유 글에는 초안을 옮기지 않는다 — 바뀌지 않는 코드 · 짧은 이유 · 건수만(로그 · 보고에 손님 글이 섞이지 않게).

글 맞추기 · 숫자 · 링크 읽기는 :mod:`.checks_read`. 같은 규칙을 사람 답 사후 점검(:func:`audit_staff_reply` — 플랜 C1-3
월요일판, 브랜드 섞임 · 계좌)이 같이 쓴다.
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, NamedTuple, Optional, Union

from foms.services.cs_agent.checks_read import (
    NON_DIGIT,
    TIME_UNITS,
    Found,
    clean_host,
    host_allowed,
    id_code,
    normalize,
    read_numbers,
    split_links,
    squash,
)
from foms.services.cs_agent.checks_rules import (
    MEDIUM_NAVER_TALK,
    check_brand,
    is_naver_talk,
    other_brand_count,
    pattern_codes,
    talktalk_codes,
)

__all__ = [
    "DEFAULT_LINK_HOSTS",
    "MEDIUM_NAVER_TALK",
    "REASONS",
    "CheckResult",
    "Problem",
    "audit_staff_reply",
    "check_draft",
    "is_naver_talk",
    "numbers_in",
    "tone_warnings",
]

#: 허용 목록 값 — 숫자거나, 초안과 같은 규칙으로 읽을 글('150,000원' · '5~7일' · 계산기 결과 글 · 승인 지식 글).
Allowed = Union[int, float, Decimal, str]

#: 기본 허용 링크 집 — 톡톡에서도 된다(플랜 C2-2 '스마트스토어 링크는 허용'). 아래 집(m.smartstore.naver.com)도 된다.
DEFAULT_LINK_HOSTS: tuple[str, ...] = ("smartstore.naver.com", "naver.me")
#: 말투: 한 덩어리(빈 줄로 나뉜 글)가 이만큼(자) 넘으면 알림(시범 · 직원 글 평균 39자, D35).
TONE_BLOCK_CHARS = 120
#: 비공개 메모 한 마디(한글 · 영문 · 숫자만 센 글자 수)가 이만큼 이상이면, 초안에 통째로 있을 때 막는다(R1-12).
LEAK_MIN_CHARS = 8
#: 그보다 긴 마디는 이만큼 이어진 글자가 초안에 있으면 막는다(일부만 옮겨 적은 것도 잡는다).
LEAK_WINDOW_CHARS = 12

#: 문제 코드 → 짧은 이유. 시범에 있던 것은 시범 문구 그대로(PC 시범 기록과 같게 읽히도록). 초안 글은 넣지 않는다.
REASONS: dict[str, str] = {
    "empty": "답이 비었음",
    "other_brand": "다른 브랜드 이름",
    "account_number": "기본 안내 계좌가 아닌 계좌 번호",
    "phone_number": "허용 목록에 없는 전화번호",
    "discount_promise": "할인 약속",
    "refund_promise": "환불 약속",
    "date_promise": "날짜 확답",
    "contact_time_promise": "연락 시간 약속",
    "internal_words": "내부 말 노출",
    "ai_mention": "AI 표시 · 자기소개(직원이 보내는 글)",
    "human_claim": "사람이라고 하는 말(정체는 직원이 직접 답한다)",
    "mask_marker": "가림 표시가 답에 섞임",
    "link_not_allowed": "허용 목록 밖 링크",
    "number_not_allowed": "계산기 · 확정 값에 없는 숫자 · 금액",
    "date_not_confirmed": "확정 안 된 날짜",
    "human_only_amount": "사람만 말하는 항목의 금액 · 배수",
    "private_memo_leak": "비공개 메모 문장이 섞임",
    "example_only_word": "예시에만 있는 낱말",
    "talktalk_outside": "톡톡 상담 바깥으로 옮기기",
    "talktalk_link": "톡톡 상담에 바깥 링크",
    "talktalk_phone_ask": "톡톡에서 손님 번호 받기",
    "tone_emoji": "말투: 이모지 여러 개",
    "tone_long_block": "말투: 한 덩어리가 너무 김(120자 넘음 — 짧은 글로 나눌 것)",
    "tone_haeyo": "말투: 해요체 끝맺음(~요)",
}


@dataclass(frozen=True)
class Problem:
    """걸린 규칙 하나 — ``code`` 는 바뀌지 않는 이름, ``reason`` 은 짧은 한글 이유, ``count`` 는 걸린 곳 수."""

    code: str
    reason: str
    count: int = 1


@dataclass(frozen=True)
class CheckResult:
    """검사 결과. ``problems`` 가 하나라도 있으면 올리지 않는다 — ``warnings``(말투)는 보여 주기만 한다."""

    problems: tuple[Problem, ...] = ()
    warnings: tuple[Problem, ...] = ()

    @property
    def ok(self) -> bool:
        """막을 문제가 없으면 참."""
        return not self.problems

    @property
    def codes(self) -> tuple[str, ...]:
        """막은 문제 코드(나온 순서)."""
        return tuple(p.code for p in self.problems)


#: 비공개 메모를 마디로 나누는 곳(문장 끝 · 줄바꿈 · 쉼표 · 가운뎃점).
_CLAUSE = re.compile(r"[.!?\n,·;:]+")
#: 이모지(시범 _EMO 와 같은 범위).
_EMOJI = re.compile(f"[{chr(0x2600)}-{chr(0x27BF)}{chr(0x1F000)}-{chr(0x1FAFF)}]")
#: 해요체 끝맺음 '~요'(시범 _HAEYO). '세요 · 까요 · 시요 · 니요'(직원 말투 '가능하세요')와 '필요 · 중요 · 주요 · 수요'는 뺀다.
_HAEYO = re.compile(r"(?<![세까시니필중주수])요[!.~^]*(?!\w)")
#: 덩어리 나누기 — 빈 줄(시범).
_BLANK_LINE = re.compile(r"\n\s*\n")


class _AllowedSet(NamedTuple):
    """허용 목록 — 숫자로 준 값(단위 안 가림) · 글에서 읽은 값마다 (종류, 단위) · 전화/계좌 꼴(숫자만) · 날짜."""

    loose: frozenset[Decimal]
    tokens: dict[Decimal, set[tuple[str, str]]]
    ids: frozenset[str]
    dates: frozenset[tuple[Optional[int], int, int]]


def _account_digits(accounts: Iterable[str]) -> frozenset[str]:
    """기본 안내 계좌(D11)를 숫자만으로 — 붙임표 · 띄어쓰기가 달라도 같은 계좌다."""
    return frozenset(NON_DIGIT.sub("", normalize(a)) for a in accounts)


def _allowed_from(items: Iterable[Allowed], dates: Iterable[datetime.date]) -> _AllowedSet:
    """허용 목록 만들기 — 숫자 값은 그대로(단위를 가리지 않음), 글은 초안과 같은 규칙으로 읽어 (값, 종류, 단위)로 둔다."""
    loose: set[Decimal] = set()
    tokens: dict[Decimal, set[tuple[str, str]]] = {}
    ids: set[str] = set()
    days = {(d.year, d.month, d.day) for d in dates}
    for item in items:
        if item is None or isinstance(item, bool):
            continue
        if isinstance(item, (int, float, Decimal)):
            loose.add(Decimal(str(item)))
            continue
        found = read_numbers(split_links(normalize(str(item)))[1])
        for value, kind, unit in found.values:
            tokens.setdefault(value, set()).add((kind, unit))
        ids.update(digits for digits, _ in found.ids)
        days.update(found.dates)
    return _AllowedSet(frozenset(loose), tokens, frozenset(ids), frozenset(days))


def _value_allowed(value: Decimal, kind: str, unit: str, allowed: _AllowedSet) -> bool:
    """초안 숫자가 허용 목록에 있는가(R6-5) — 금액은 금액끼리, 비율은 같은 꼴(% · 배 · 분수)끼리, 때 단위(시 · 일 · 분 …)는
    같은 단위끼리만. 그 밖의 수는 한쪽에 단위가 없거나 같은 단위면 된다('가로 1200' 과 '1,200mm')."""
    if value in allowed.loose:
        return True
    for other_kind, other_unit in allowed.tokens.get(value, ()):
        if other_kind != kind:
            continue
        if kind == "amount" or unit == other_unit:
            return True
        if kind == "number" and unit not in TIME_UNITS and other_unit not in TIME_UNITS and not (unit and other_unit):
            return True
    return False


def _date_allowed(day: tuple[Optional[int], int, int], allowed: frozenset[tuple[Optional[int], int, int]]) -> bool:
    """초안 속 날짜가 확정 값과 같은가 — 해가 한쪽에 없으면 달 · 날만 견준다."""
    year, month, dom = day
    return any(m == month and d == dom and (year is None or y is None or y == year) for y, m, d in allowed)


def _number_codes(found: Found, allowed: _AllowedSet, accounts: frozenset[str], human_only: bool) -> list[str]:
    """허용 목록 검사 — 전화 · 계좌 꼴 · 날짜 · 숫자 값이 계산기 · 확정 값에 있을 때만 통과(R1-11 · R6-5 · D11)."""
    known_ids = allowed.ids | accounts
    codes = [id_code(digits, ctx) for digits, ctx in found.ids if digits not in known_ids]
    codes += ["date_not_confirmed" for day in found.dates if not _date_allowed(day, allowed.dates)]
    for value, kind, unit in found.values:
        if human_only and kind != "number":
            codes.append("human_only_amount")
        elif not _value_allowed(value, kind, unit, allowed):
            codes.append("number_not_allowed")
    return codes


def _private_leaks(draft: str, snippets: Iterable[str]) -> int:
    """비공개 메모 마디가 초안에 든 수 — 짧은 마디는 통째로, 긴 마디는 ``LEAK_WINDOW_CHARS`` 자 이어진 곳으로 본다."""
    snippets = list(snippets)
    if not snippets:
        return 0
    size = LEAK_WINDOW_CHARS
    grams = {draft[k:k + size] for k in range(len(draft) - size + 1)}  # 초안의 이어진 글자 묶음 — 긴 메모도 한 번에 견준다
    hits = 0
    for snippet in snippets:
        for clause in _CLAUSE.split(normalize(snippet)):
            part = squash(clause)
            if len(part) < LEAK_MIN_CHARS:
                continue
            if len(part) <= size:
                hits += part in draft
            else:
                hits += any(part[k:k + size] in grams for k in range(len(part) - size + 1))
    return hits


def _example_hits(draft: str, words: Iterable[str]) -> int:
    """예시에만 있는 낱말이 초안에 든 수 — 두 글자 이상만(한 글자는 어디에나 있다)."""
    return sum(1 for word in words if len(part := squash(normalize(word))) >= 2 and part in draft)


def _problems(codes: Iterable[str]) -> tuple[Problem, ...]:
    """코드 목록 → 코드마다 한 줄(처음 나온 순서 · 건수)."""
    counts: dict[str, int] = {}
    for code in codes:
        counts[code] = counts.get(code, 0) + 1
    return tuple(Problem(code, REASONS[code], n) for code, n in counts.items())


def tone_warnings(text: str) -> tuple[Problem, ...]:
    """말투 꼴(D35 — 보류): 이모지 여러 개 · 한 덩어리 120자 넘음 · 해요체 끝맺음. 막지 않고 보여 주기만 한다."""
    body = normalize(text)
    codes = ["tone_emoji"] if len(_EMOJI.findall(body)) > 1 else []
    if any(len(part.strip()) > TONE_BLOCK_CHARS for part in _BLANK_LINE.split(body)):
        codes.append("tone_long_block")
    if _HAEYO.search(body):
        codes.append("tone_haeyo")
    return _problems(codes)


def check_draft(
    text: str,
    *,
    brand: str,
    medium: Optional[str] = None,
    allowed_numbers: Iterable[Allowed] = (),
    confirmed_dates: Iterable[datetime.date] = (),
    private_snippets: Iterable[str] = (),
    example_only_words: Iterable[str] = (),
    human_only_amounts: bool = False,
    allowed_accounts: Iterable[str] = (),
    allowed_link_hosts: Iterable[str] = (),
) -> CheckResult:
    """AI 초안의 '손님께 보낼 답' 칸 보내기 전 검사(모르는 브랜드면 ``ValueError``).

    Args:
        text: 손님께 보낼 답(가린 글). '직원 참고' 칸은 넣지 않는다 — 그 칸은 ``private_snippets`` 로.
        brand: 'LAHOM' · 'HAUD' — 다른 브랜드 이름을 막는다.
        medium: 상담 매체(시범 꼴 'appNaverTalk'). 톡톡이거나 모르면(None · '') 톡톡 규칙을 더한다 — 일부러 막는 쪽이니
            C3 는 상담의 매체를 꼭 넘긴다(R6-20).
        allowed_numbers: 계산기 결과 · 확정 값 · 승인 지식 글. 숫자 값(int · Decimal)은 단위를 가리지 않고, 글은 같은 규칙으로
            읽어 값 · 종류(금액 · 비율 · 수) · 단위(개 · 시 · 일 · cm …)가 맞을 때만 허용한다(R6-5). 손님 글에서 온 금액은
            금액으로 넣지 않는다(손님 예산에 값을 맞춰 주는 약속이 된다) — 손님 규격은 단위 붙은 글로만('가로 1200mm').
        confirmed_dates: 확정된 날(실측 · 시공). 초안 속 날짜와 날짜 확답은 여기 있을 때만 통과한다.
        private_snippets: 비공개 메모(직원 내부 메모 · 이전 AI 메모의 직원 참고 칸 · 이번 초안의 직원 참고) — 마디가 섞이면 막음.
        example_only_words: 후보 예시에만 있고 이 상담 · 지식에는 없는 고유 낱말(R1-10, 고르는 것은 호출 쪽).
        human_only_amounts: 재료에 사람만 말하는 항목(지식의 [사람] — 지방 운임 · 커스텀 등)이 있으면 True. 초안 속 금액 ·
            배수 · % · 분수를 허용 목록과 상관없이 막는다(설계서 12절 · D17).
        allowed_accounts: 기본 안내 계좌 번호(D11 — 이 계좌만 허용, 번호는 저장소 밖 지식에서).
        allowed_link_hosts: 기본(스마트스토어 · naver.me)에 더할 링크 집. 톡톡이면 네이버 안쪽만 남는다.

    Returns:
        :class:`CheckResult` — ``ok`` 가 거짓이면 올리지 않는다. 말투 꼴은 ``warnings`` 에만 있다.
    """
    brand = check_brand(brand)
    body = normalize(text)
    squashed = squash(body)
    allowed = _allowed_from(allowed_numbers, confirmed_dates)
    hosts = tuple(clean_host(h) for h in (*DEFAULT_LINK_HOSTS, *allowed_link_hosts))
    links, unlinked = split_links(body)
    codes = ["empty"] if len(squashed) < 2 else []
    codes += pattern_codes(body, brand, allowed.dates)
    codes += ["link_not_allowed" for host in links if not host_allowed(host, hosts)]
    if not medium or is_naver_talk(medium):
        codes += talktalk_codes(body, links, hosts)
    codes += _number_codes(read_numbers(unlinked), allowed, _account_digits(allowed_accounts), human_only_amounts)
    codes += ["private_memo_leak"] * _private_leaks(squashed, private_snippets)
    codes += ["example_only_word"] * _example_hits(squashed, example_only_words)
    return CheckResult(_problems(codes), tone_warnings(body))


def audit_staff_reply(text: str, *, brand: str, allowed_accounts: Iterable[str] = ()) -> CheckResult:
    """사람(직원) 공개 답 사후 점검 — 브랜드 섞임 · 기본 안내 계좌가 아닌 계좌 번호만 센다(플랜 C1-3 월요일판 · R5-11).

    직원은 할인 · 날짜를 말할 수 있으니 그 꼴은 보지 않는다. 금액 검산(계산기와 견주기)은 계산기(C2-1 · C3-1)가 선 뒤 더한다.

    Raises:
        ValueError: 모르는 브랜드.
    """
    body = normalize(text)
    codes = ["other_brand"] * other_brand_count(body, brand)
    accounts = _account_digits(allowed_accounts)
    for digits, ctx in read_numbers(split_links(body)[1]).ids:
        if digits not in accounts and id_code(digits, ctx) == "account_number":
            codes.append("account_number")
    return CheckResult(_problems(codes))


def numbers_in(text: str) -> frozenset[Decimal]:
    """글 속 숫자 · 금액 값 — '십오만 원' · '15 만원' · '₩150,000' 도 150000 하나로 읽는다(허용 목록 만들기 · 시험용).

    전화 · 계좌 꼴 묶음 · 날짜 · 링크는 빼고 숫자 값만 돌려준다(분수 '1/2 가격' 은 0.5).
    """
    return frozenset(v for v, _, _ in read_numbers(split_links(normalize(text))[1]).values)
