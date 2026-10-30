"""초안 차례 기록의 칸 꼴 검사 — 코드 · id · 숫자 · 비용 · 가린 글(:mod:`.turns` 가 쓴다, 500줄 상한으로 나눴다).

글처럼 생긴 값은 코드 칸에 넣지 않고, 꼴이 틀린 값은 비운 뒤 칸 이름만 경고한다(값은 로그에 싣지 않는다). 가린 칸에는 한 번 더
가리고 가림 검사가 0 인 글만 넣는다(원장 R1-20). 로거 이름은 :mod:`.turns` 와 같다 — 기존 시험이 그 이름으로 경고를 본다.
"""

from __future__ import annotations

import enum
import logging
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Optional

from foms.services.cs_agent.masking import mask, require_masked

logger = logging.getLogger("foms.services.cs_agent.turns")

__all__ = ["ID_PATTERN", "check_codes", "checked_id", "code", "cost", "count", "masked_or_none", "reason"]

#: 채널톡 id 꼴 — 빈칸 없는 ASCII 64자까지(손님 글이 자리를 바꿔 들어오면 여기서 걸린다).
ID_PATTERN = re.compile(r"[\x21-\x7e]{1,64}")
#: 코드 칸 꼴 — 빈칸 · 줄바꿈 없는 짧은 이름(한글 이름도 된다). 글처럼 생긴 값은 칸에 넣지 않는다.
_CODE = re.compile(r"[\w.:/\-]+")
_CHECK_CODE = re.compile(r"[a-z][a-z0-9_]{0,47}")
_REASON_MAX = 48
_INT_MAX = 2**31 - 1
#: 비용 칸 ``Numeric(12, 6)`` — 소수 여섯째 자리, 정수 여섯 자리까지.
_COST_SCALE = Decimal(10) ** -6
_COST_MAX = Decimal(10) ** 6 - _COST_SCALE


def masked_or_none(text: Optional[str]) -> Optional[str]:
    """가린 사본 — 한 번 더 가리고 가림 검사가 0 일 때만 돌려준다. ``None`` · 빈 글은 ``None``."""
    if text is None:
        return None
    if not isinstance(text, str):
        raise TypeError("가린 글은 글자열이다")
    return require_masked(mask(text)) if text.strip() else None


def check_codes(codes: Iterable[Any]) -> list[str]:
    """검사 코드 목록(겹침 없이 순서대로). 코드 글자열이나 ``code`` 속성이 있는 검사 결과 항목을 받는다."""
    if isinstance(codes, (str, bytes)):
        raise TypeError("check_codes 는 코드 목록이다")
    out: list[str] = []
    for item in codes:
        value = getattr(item, "code", item)
        if not isinstance(value, str) or not _CHECK_CODE.fullmatch(value):
            raise ValueError("검사 코드 꼴이 아니다(영문 소문자 · 숫자 · 밑줄)")
        if value not in out:
            out.append(value)
    return out


def checked_id(value: Any) -> str:
    """채널톡 id 꼴인 값만."""
    if not isinstance(value, str) or not ID_PATTERN.fullmatch(value):
        raise ValueError("채널톡 id 꼴이 아니다")
    return value


def reason(value: Any) -> str:
    """이유 코드(비면 안 된다)."""
    found = code(value, _REASON_MAX, "error_code")
    if found is None:
        raise ValueError("이유 코드 꼴이 아니다")
    return found


def code(value: Any, limit: int, field: str) -> Optional[str]:
    """코드 칸 값 — 꼴이 맞는 짧은 이름만. 비었으면 ``None``, 꼴이 틀리면 경고하고 ``None``(값은 로그에 싣지 않는다)."""
    if isinstance(value, enum.Enum):
        value = value.value
    if value is None or value == "":
        return None
    if isinstance(value, str) and len(value) <= limit and _CODE.fullmatch(value):
        return value
    logger.warning("[CS 초안] 기록 칸 꼴이 틀려 비운다 field=%s", field)
    return None


def count(value: Any, field: str) -> Optional[int]:
    """0 이상 정수 칸(토큰 · 밀리초). 꼴이 틀리면 경고하고 ``None``."""
    if value is None:
        return None
    if not isinstance(value, bool) and isinstance(value, (int, float, Decimal)):
        try:
            number = int(round(value))
        except (ValueError, OverflowError, InvalidOperation):
            number = -1
        if 0 <= number <= _INT_MAX:
            return number
    logger.warning("[CS 초안] 기록 칸 꼴이 틀려 비운다 field=%s", field)
    return None


def cost(value: Any) -> Optional[Decimal]:
    """비용(달러) — 0 이상, 소수 여섯째 자리까지. 꼴이 틀리면 경고하고 ``None``."""
    if value is None:
        return None
    if not isinstance(value, bool) and isinstance(value, (int, float, Decimal)):
        try:
            amount = Decimal(str(value))
        except InvalidOperation:
            amount = Decimal("NaN")
        if amount.is_finite() and Decimal(0) <= amount <= _COST_MAX:
            return amount.quantize(_COST_SCALE)
    logger.warning("[CS 초안] 기록 칸 꼴이 틀려 비운다 field=cost_usd")
    return None
