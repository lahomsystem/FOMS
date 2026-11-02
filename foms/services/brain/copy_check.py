"""바깥 사본 점검(설계서 7.8 다음 6 · 판 1 완료 기준 'D84 네 건') — 정본 값을 베껴 둔 바깥 글(채널톡 매크로 · 스토어 상세 구획 ·
화면 · 양식)이 정본과 어긋났는지 본다.

- brain 은 사본 글을 두지 않는다 — ``copy_in`` 링크(정본 항목 → ``macro:<id>`` 등)의 실음 칸에 **마지막 본 글의 지문**
  (:func:`text_digest` — sha256)과 확인 날만 둔다(:data:`foms.services.brain.gates.LINK_PAYLOAD_KEYS`). 글이 바뀌었는지는 지문으로,
  어긋났는지는 아래 점검으로 본다.
- 점검 둘은 **순수 함수**다(글을 인자로 받는다 — 매크로 · 스토어 글을 읽어 오는 길은 부르는 쪽 몫, DB · 네트워크 없음):
  :func:`copy_mismatch`('사본 글 속 숫자 ≠ 가리킨 값') · :func:`unlinked_macros`('어느 항목에도 없는 매크로').
- 결과에는 숫자 · 짧은 값 · 키만 싣는다(사본 글 자체는 싣지 않는다).
"""

from __future__ import annotations

import datetime
import hashlib
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from sqlalchemy import select

from foms.persistence.brain.models import BrainLink
from foms.services.brain.store import in_force, is_current

MACRO = "macro:"
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
_SPACE = re.compile(r"\s+")


def text_digest(text: str) -> str:
    """글 지문 — 띄어쓰기를 하나로 맞춘 글의 sha256 16진 64자(링크 실음 칸 ``seen_digest`` — 글 자체는 두지 않는다)."""
    return hashlib.sha256(_SPACE.sub(" ", str(text or "")).strip().encode("utf-8")).hexdigest()


def _number(raw: str) -> Decimal | None:
    """숫자 글 → 수(쉼표는 뗀다 — '150,000' 과 '150000' 은 같다). 못 읽으면 ``None``."""
    try:
        return Decimal(raw.replace(",", ""))
    except InvalidOperation:
        return None


def _text(number: Decimal) -> str:
    """수 → 글(지수 꼴 없이)."""
    return format(number.normalize(), "f")


def numbers_in(text: str) -> list[Decimal]:
    """글 속 숫자들(차례대로)."""
    found = (_number(m) for m in _NUMBER.findall(str(text or "")))
    return [n for n in found if n is not None]


def _plain(text: Any) -> str:
    """견주기 꼴 — 띄어쓰기를 빼고 소문자."""
    return _SPACE.sub("", str(text or "")).lower()


def copy_mismatch(pointed: Iterable[Any], copy_text: str) -> dict[str, list[str]]:
    """'사본 글 속 숫자 ≠ 가리킨 값' — 가리킨 정본 값(숫자 · 짧은 말)과 사본 글 하나를 견준다.

    Args:
        pointed: 정본 값들 — 수(또는 숫자 글)는 숫자로, 그 밖의 글('기본 몰딩' 같은 고른 값 이름)은 말로 견준다.
        copy_text: 사본 글(매크로 · 스토어 구획 글 — 부르는 쪽이 읽어 온 것).

    Returns:
        ``{"extra": 사본에만 있는 숫자, "missing": 사본에 없는 정본 값}`` — 둘 다 비면 맞음. 사본 글은 싣지 않는다.
    """
    want_numbers: list[Decimal] = []
    want_words: list[str] = []
    for value in pointed:
        if isinstance(value, bool):
            continue
        number = _number(str(value)) if isinstance(value, (int, float, Decimal, str)) and _NUMBER.fullmatch(
            str(value).strip()) else None
        if number is not None:
            want_numbers.append(number)
        elif str(value).strip():
            want_words.append(str(value).strip())
    seen = numbers_in(copy_text)
    extra = sorted({_text(n) for n in seen if n not in want_numbers}, key=Decimal)
    missing = [_text(n) for n in dict.fromkeys(want_numbers) if n not in seen]
    missing += [w for w in want_words if _plain(w) not in _plain(copy_text)]
    return {"extra": extra, "missing": missing}


def mismatched(pointed: Iterable[Any], copy_text: str) -> bool:
    """사본이 정본과 어긋났나(:func:`copy_mismatch` 가 무엇이든 낸다)."""
    found = copy_mismatch(pointed, copy_text)
    return bool(found["extra"] or found["missing"])


def unlinked_macros(macro_ids: Iterable[str], refs: Iterable[str]) -> list[str]:
    """'어느 항목에도 없는 매크로' — 매크로 id 가운데 어떤 ``copy_in`` 링크 끝(``macro:<id>``)에도 없는 것(id 차례대로)."""
    linked = {r[len(MACRO):] for r in refs if isinstance(r, str) and r.startswith(MACRO)}
    return sorted({str(m).strip().lower() for m in macro_ids if str(m).strip()} - linked)


def macro_refs(session: Any, today: datetime.date) -> set[str]:
    """지금 · 유효 기간 안 ``copy_in`` 링크의 매크로 끝(:func:`unlinked_macros` 재료 — 키만)."""
    return set(session.execute(select(BrainLink.to_key).where(
        BrainLink.kind == "copy_in", is_current(BrainLink), in_force(BrainLink, today),
        BrainLink.to_key.like(MACRO + "%"))).scalars())
