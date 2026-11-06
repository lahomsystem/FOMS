"""수수료 주인 판정용 이름 정리(FCOMM-01 §3.1 · J8).

주문의 발주사 · 대표 담당자 칸과 프리랜서 설정의 "맞출 이름"을 비교할 때 양쪽에 같은 정리를 건다.
정리 = 유니코드 NFC + 앞뒤 공백 제거. 대소문자 · 가운데 공백은 건드리지 않는다(완전 일치만 인정).
"""

from __future__ import annotations

import unicodedata
from typing import Any


def normalize_name(value: Any) -> str:
    """이름 칸 값을 비교용 글자로 정리한다.

    Args:
        value: 주문 칸 값 또는 설정값. 글자가 아니면 빈 글자로 본다.

    Returns:
        NFC 정규화 뒤 앞뒤 공백을 지운 글자. 비었으면 ``""``.
    """
    if not isinstance(value, str):
        return ""
    return unicodedata.normalize("NFC", value).strip()
