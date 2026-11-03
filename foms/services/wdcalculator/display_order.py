"""견적 계산기 목록 보이는 차례 — 한글(ㄱ · ㄴ · ㄷ …) 먼저, 그다음 영문(a · b · c …), 그 밖(숫자 · 기호)은 뒤(사장님 11-03).

저장된 차례는 바꾸지 않는다 — 화면에 내보낼 때만 줄 세운다(설정 화면 · 계산기 화면 · 카테고리 읽기 API). 같은 글자 안에서는
숫자를 수로 견준다('폭 300mm' < '폭 1200mm'), 영문은 대 · 소문자를 가리지 않는다. 한글 음절은 유니코드 차례가 사전 차례
(가 < 까 < 나)라 그대로 쓴다.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

__all__ = ["name_key", "sorted_by_name", "sorted_categories"]

_NUMBER = re.compile(r"(\d+)")


def _script_rank(text: str) -> int:
    """첫 글자의 무리 — 한글 0 · 영문 1 · 숫자 2 · 그 밖 3(빈 글은 맨 뒤 4)."""
    for char in text:
        if char.isspace():
            continue
        if "가" <= char <= "힣" or "ㄱ" <= char <= "ㆎ":
            return 0
        if char.isascii() and char.isalpha():
            return 1
        return 2 if char.isdigit() else 3
    return 4


def name_key(name: Any) -> tuple:
    """이름 하나의 줄 세우기 열쇠 — (무리, 글 조각들). 숫자 조각은 수로 견준다."""
    text = str(name or "").strip()
    parts = tuple((0, int(part), "") if part.isdigit() else (1, 0, part)
                  for part in _NUMBER.split(text.casefold()) if part)
    return _script_rank(text), parts


def sorted_by_name(rows: Iterable[Any], field: str = "name") -> list[Any]:
    """``field`` 칸으로 줄 세운 새 목록(사전이 아닌 줄은 맨 뒤)."""
    return sorted(rows, key=lambda row: name_key(row.get(field)) if isinstance(row, Mapping) else (5, ()))


def sorted_categories(categories: Iterable[Any]) -> list[Any]:
    """카테고리와 그 안의 옵션을 모두 줄 세운 새 목록(넘겨받은 목록 · 사전은 바꾸지 않는다)."""
    out = []
    for category in sorted_by_name(categories or ()):
        if isinstance(category, Mapping) and isinstance(category.get("options"), list):
            category = {**category, "options": sorted_by_name(category["options"])}
        out.append(category)
    return out
