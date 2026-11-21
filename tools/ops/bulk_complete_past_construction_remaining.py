"""BACKLOG-COMPLETE-01 남은 시공 판정 — 뒤 시공일 · 남은 제품(순수 함수, 핵심은 bulk_complete_past_construction_core.py).

지난 주문 일괄 완료 도구가 "아직 시공이 남은 주문"을 닫지 않게 하는 두 판정을 모은다.

* :func:`later_construction_date` — 기준일 뒤로 남은 시공일(한 주문 여러 시공일 1단계).
* :func:`items_construction_open` — '시공 끝' 제품도 남은 제품도 있는 부분 시공 중 주문
  (제품마다 '시공 끝' 2단계 N7 — 스위치와 상관없이 자료로만 판정한다).

이 도구는 foms 를 import 하지 않는다(psycopg 만으로 도는 운영 도구). 앱 규칙과 같은 판정을 한 벌 더 두고,
순수 시험(``tests/domains/test_bulk_complete_past_construction_plan.py``)이 두 벌을 견준다.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

__all__ = [
    "ITEMS_CONSTRUCTION_OPEN_REASON", "items_construction_open", "later_construction_date", "text_dates",
]

#: plan 제외 사유 — 앱 문지기 코드(``ITEMS_CONSTRUCTION_OPEN``)의 소문자 꼴.
ITEMS_CONSTRUCTION_OPEN_REASON = "items_construction_open"

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATE_TOKEN_RE = re.compile(r"^(?:(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})|(\d{4})(\d{2})(\d{2}))(?!\d)")
#: 앱 ``structured_item_uid`` 와 같은 규칙 — 서버가 단 UUID4 글(36자)만 제품 이름표로 본다.
_UID_LENGTH = 36


def text_dates(raw: Any) -> list[str]:
    """쉼표로 이은 시공일 글 → ``YYYY-MM-DD`` 목록(정렬 · 중복 제거, 못 읽는 토큰은 버림).

    앱의 ``foms.services.orders.construction_dates.split_date_text`` 와 같은 규칙이다
    (이 도구는 foms 를 import 하지 않아 한 벌 더 둔다 — 순수 시험이 두 벌을 견준다).
    """
    found: set[str] = set()
    for token in str(raw or "").split(","):
        m = _DATE_TOKEN_RE.match(token.strip())
        if not m:
            continue
        y, mo, d = (g for g in m.groups() if g is not None)
        try:
            found.add(date(int(y), int(mo), int(d)).isoformat())
        except ValueError:
            continue
    return sorted(found)


def _item_dates(items: Any) -> list[str]:
    """제품 칸 ``items[*].construction_date`` 의 날짜 전부(취소 제품도 넣는다 — 잘못 빼도 해가 없다)."""
    rows = items if isinstance(items, list) else []
    return [d for it in rows if isinstance(it, dict) for d in text_dates(it.get("construction_date"))]


def later_construction_date(row: dict[str, Any], cutoff: str | None) -> str | None:
    """``cutoff`` 이후(당일 포함)로 남은 가장 이른 시공일. 없으면 None.

    일정 표(``later_construction_date`` 칸) · 주문 칸 글(``construction_text``) · 제품 칸
    (``items``) 가운데 하나라도 걸리면 남은 것으로 본다 — 표가 뒤처져도 글에 적힌 날은 잡는다.
    """
    found = []
    from_table = str(row.get("later_construction_date") or "").strip()
    if _DATE_RE.match(from_table):
        found.append(from_table)
    if cutoff:
        texts = text_dates(row.get("construction_text")) + _item_dates(row.get("items"))
        found.extend(d for d in texts if d >= cutoff)
    return min(found) if found else None


def _item_uid(item: dict[str, Any]) -> str | None:
    value = item.get("uid")
    value = value.strip() if isinstance(value, str) else ""
    return value if len(value) == _UID_LENGTH else None


def items_construction_open(row: Any) -> bool:
    """부분 시공 중인가 — 취소 안 된 제품 가운데 '시공 끝' 제품도 남은 제품도 있다.

    앱 ``item_construction_done.is_partial_open`` 과 같은 규칙이다(취소 = ``cancel`` dict, 이름표 = 36자
    uid, 기록 = ``item_construction_done[uid]`` dict). 후보 행(``items`` · ``item_construction_done`` 칸)과
    주문 ``structured_data`` 를 둘 다 받는다 — 두 곳의 열쇠 이름이 같다.
    """
    source = row if isinstance(row, dict) else {}
    items = source.get("items")
    marks = source.get("item_construction_done")
    if not isinstance(items, list) or not isinstance(marks, dict):
        return False
    done = remaining = False
    for item in items:
        if not isinstance(item, dict) or isinstance(item.get("cancel"), dict):
            continue
        uid = _item_uid(item)
        if uid is not None and isinstance(marks.get(uid), dict):
            done = True
        else:
            remaining = True
    return done and remaining
