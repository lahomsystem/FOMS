"""회사 무상 AS 기간 — 시공일로부터 1년(사용자 결정 D224 · D235 · 점검 2차 w6-07).

- :data:`FREE_AS_YEARS` — 무상 AS 기간(해). 이 한 곳만 고친다.
- :func:`state` — 주문의 시공일(여러 날이면 마지막 날)로 무상 기간 안 · 지남 · 모름(시공일 없음)을 가른다. 시공일과 같은 달 · 날이
  되는 1년 뒤 그날까지 안이고(시공일 다음 날부터 1년 — 민법 초일 불산입과 같은 셈), 2월 29일 시공은 다음 해 2월 28일까지다.
- :func:`label` — 승인 창 · 제안 이유에 보일 말(예: '무상 기간 지남(시공일 2024-03-01)').
- :func:`billing_for_register` — AS 접수가 접수 본체(``register_as_from_payload``)에 넘길 무상 · 유상 칸 값: 안이면 ``free``(지금
  처음 값 — 무상 추정 · 확정 전), 지남 · 모름이면 ``undecided``(미정 — 사람이 AS 화면에서 정한다). 지난 주문을 무상으로 적지 않는다.
- 순수 함수다(주문 줄 하나 · 오늘). DB 질의 없음.
"""

from __future__ import annotations

import datetime
import re
from typing import Any, Optional

__all__ = ["FREE_AS_YEARS", "IN", "OVER", "UNKNOWN", "billing_for_register", "construction_day", "label", "state"]

#: 회사 무상 AS 기간(D224 — 시공일로부터 1년).
FREE_AS_YEARS = 1
IN, OVER, UNKNOWN = "in", "over", "unknown"
_SPLIT = re.compile(r"[,|]")


def construction_day(order: Any) -> Optional[datetime.date]:
    """시공일(``structured_data.schedule.construction.date`` — 없으면 납작 칸)의 마지막 날, 못 읽으면 ``None``."""
    data = getattr(order, "structured_data", None)
    node = data.get("schedule") if isinstance(data, dict) else None
    node = node.get("construction") if isinstance(node, dict) else None
    raw = (node.get("date") if isinstance(node, dict) else None) or getattr(order, "erp_construction_date", None) or ""
    days = []
    for part in _SPLIT.split(str(raw)):
        try:
            days.append(datetime.date.fromisoformat(part.strip()[:10]))
        except ValueError:
            continue
    return max(days) if days else None


def _last_free_day(day: datetime.date) -> datetime.date:
    """무상 기간 마지막 날 — 시공일 :data:`FREE_AS_YEARS` 해 뒤 같은 달 · 날(없는 날이면 그 달 28일)."""
    try:
        return day.replace(year=day.year + FREE_AS_YEARS)
    except ValueError:
        return day.replace(year=day.year + FREE_AS_YEARS, day=28)


def state(order: Any, today: datetime.date) -> tuple[str, Optional[datetime.date]]:
    """(무상 기간 판정 :data:`IN` · :data:`OVER` · :data:`UNKNOWN`, 시공일) — 시공일이 없으면 모름."""
    day = construction_day(order)
    if day is None:
        return UNKNOWN, None
    return (IN if today <= _last_free_day(day) else OVER), day


def label(order: Any, today: datetime.date) -> str:
    """화면 말 — '무상 기간 안(시공일 …)' · '무상 기간 지남(시공일 …)' · '시공일이 없어 무상 기간을 몰라요'."""
    verdict, day = state(order, today)
    if day is None:
        return "시공일이 없어 무상 기간을 몰라요"
    return f"무상 기간 {'안' if verdict == IN else '지남'}(시공일 {day.isoformat()})"


def billing_for_register(order: Any, today: datetime.date) -> str:
    """AS 접수 무상 · 유상 칸 값 — 무상 기간 안이면 ``free``, 지남 · 모름이면 ``undecided``(사람이 정한다)."""
    return "free" if state(order, today)[0] == IN else "undecided"
