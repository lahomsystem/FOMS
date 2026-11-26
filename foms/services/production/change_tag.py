"""도면 칸 손님 이름 아래 빨간 표 — 무엇이 바뀌었는지(사장님 2026-11-26 "무엇이 바뀌었는지 붙이기").

'바뀐 것' 줄(``production_change_alerts`` 의 ``home_alerts`` — ``kind`` 가 든 dict 목록)을 받아 짧은 글 하나로 줄인다.
순수 계산 · 쿼리 0. 표 자리는 시공일 줄(``home_parts.html`` ``.pp-duerow``) — 이름 줄에 두면 긴 표가 손님 이름을 밀어낸다.
"""
from __future__ import annotations

from typing import Any

#: 바뀐 것 줄의 ``kind`` → 표에 붙이는 낱말.
CHANGE_TAG_NOUNS: dict[str, str] = {"construction_date": "시공일", "drawing": "도면", "factory": "공장"}


def change_tag(alerts: Any) -> str:
    """ "시공일 바뀜" · "도면 바뀜", 둘 이상이면 "시공일 외 1건 바뀜"(맨 앞 = 가장 새 줄).

    이름을 모르는 줄만 있으면 지금 글 "바뀜", 줄이 없으면 "".
    """
    items = [a for a in (alerts or []) if isinstance(a, dict)]
    if not items:
        return ""
    noun = next((CHANGE_TAG_NOUNS[a.get("kind")] for a in items if a.get("kind") in CHANGE_TAG_NOUNS), "")
    if not noun:
        return "바뀜"
    return f"{noun} 외 {len(items) - 1}건 바뀜" if len(items) > 1 else f"{noun} 바뀜"


__all__ = ["CHANGE_TAG_NOUNS", "change_tag"]
