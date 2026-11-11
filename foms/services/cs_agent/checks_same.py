"""숫자 검사의 '같은 값' — 허용 목록 값을 같은 뜻의 다른 단위로 넓히고, 손님이 말한 치수 · 개수를 더한다(사장님 11-11 바꿔 묻기 대응).

관리 패널 '숫자 같은 값 알아보기'(:mod:`.onto_settings`, 처음 끔)가 켜졌을 때만 :func:`.checks.check_draft` 가 부른다. 끄면 예전처럼
글자 그대로 같은 값 · 같은 단위만 통과한다(:func:`.checks._value_allowed`).

- **단위 바꾸기(정확히 같을 때만)**: 길이 mm · cm · m(350mm = 35cm = 0.35m), 때 주 = 주일, 주 ↔ 일(× 7) · 시간 ↔ 분(× 60) ·
  년 ↔ 개월(× 12). 나눠 떨어지지 않으면 넓히지 않는다(10일은 주로 바꾸지 않는다). 금액 · 비율은 넓히지 않는다.
- **손님이 말한 수**: 손님 글의 '수'(종류 ``number``) 가운데 때 단위가 아닌 것(치수 · 개수 · 층 · 평 …)만 더한다 — 손님이 말한
  가로 1200 을 초안이 되풀이해도 막지 않는다. 금액(손님 예산에 맞춰 주게 된다 — D164) · 기간 · 날짜 · 전화 · 계좌 꼴은 더하지 않는다.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from foms.services.cs_agent.checks_read import TIME_UNITS, normalize, read_numbers, split_links

__all__ = ["customer_tokens", "widen"]

Token = tuple[Decimal, str, str]  # 값 · 종류 · 단위

#: 길이 단위 → mm 몇 배.
_LENGTH = {"mm": Decimal(1), "cm": Decimal(10), "m": Decimal(1000)}
#: 같은 때 단위의 다른 이름.
_TIME_SAME = {"주일": "주"}
#: 때 단위 짝(큰 단위, 작은 단위, 몇 배).
_TIME_STEPS: tuple[tuple[str, str, int], ...] = (("주", "일", 7), ("시간", "분", 60), ("년", "개월", 12))
_PLACES = Decimal("0.001")


def _exact(value: Decimal) -> bool:
    """소수 셋째 자리 안에서 딱 떨어지는가(0.35m 는 되고 0.3333… 은 안 된다)."""
    return value == value.quantize(_PLACES)


def _time_units(unit: str) -> tuple[str, ...]:
    """같은 때 단위 이름들(주 → 주 · 주일)."""
    return ("주", "주일") if _TIME_SAME.get(unit, unit) == "주" else (unit,)


def _same(value: Decimal, kind: str, unit: str) -> set[tuple[Decimal, str]]:
    """한 값과 같은 (값, 단위) 짝들 — 자기 자신 포함."""
    out = {(value, unit)}
    if kind != "number":
        return out
    if unit in _LENGTH:
        base = value * _LENGTH[unit]
        out.update((base / factor, other) for other, factor in _LENGTH.items() if _exact(base / factor))
        return out
    unit = _TIME_SAME.get(unit, unit)
    for big, small, times in _TIME_STEPS:
        if unit == big:
            out.add((value * times, small))
        elif unit == small and value % times == 0:
            out.update((value / times, name) for name in _time_units(big))
    for one_value, one_unit in list(out):
        out.update((one_value, name) for name in _time_units(one_unit))
    return out


def widen(tokens: dict[Decimal, set[tuple[str, str]]]) -> dict[Decimal, set[tuple[str, str]]]:
    """허용 목록 값마다 같은 값을 더한 새 표(원래 표는 그대로)."""
    out: dict[Decimal, set[tuple[str, str]]] = {value: set(kinds) for value, kinds in tokens.items()}
    for value, kinds in tokens.items():
        for kind, unit in kinds:
            for same_value, same_unit in _same(value, kind, unit):
                out.setdefault(same_value, set()).add((kind, same_unit))
    return out


def customer_tokens(texts: Iterable[str]) -> list[Token]:
    """손님 글에서 더해도 되는 수 — 종류 ``number`` 이고 때 단위가 아닌 것만(치수 · 개수 …)."""
    out: list[Token] = []
    for text in texts:
        if not isinstance(text, str) or not text.strip():
            continue
        for value, kind, unit in read_numbers(split_links(normalize(text))[1]).values:
            if kind == "number" and unit not in TIME_UNITS:
                out.append((value, kind, unit))
    return out
