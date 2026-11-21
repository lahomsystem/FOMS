"""한 주문의 시공일 전부를 읽는 한 곳 (묶음 B — 틀린 완료 막기).

주문 하나에 시공일이 여럿일 수 있다. 주문 칸(``schedule.construction.date``)은 쉼표로 이은
글이고("2026-11-05, 2026-11-17"), 제품마다 ``items[*].construction_date`` 가 따로 있다.
평면 칸 ``erp_construction_date`` 는 그 글에서 "먼저 적힌 날"일 뿐이라 남은 시공을 못 본다.

읽는 곳은 ``structured_data`` 다 — 정본이고, 완료 단추가 있는 화면의 줄이 이미 들고 있어
추가 질의가 없다. ``order_schedule_dates`` 표는 저장 훅이 만드는 사본이라 화면 판정에 쓰지 않는다.

순수 함수만 둔다(DB · 요청 문맥 없음). 못 읽는 날짜 글은 버리고 예외를 내지 않는다.
"""
from __future__ import annotations

import datetime
import re
from typing import Any, Iterable, Optional

from foms.services.datetime_kst import get_today_kst
from foms.services.orders.drawing_confirm_partial import active_items

__all__ = [
    "all_construction_dates",
    "attach_remaining_construction_notes",
    "pick_nearest_date",
    "production_split_note",
    "remaining_construction_dates",
    "remaining_construction_note",
    "short_date_label",
    "split_date_text",
]

#: 토큰 맨 앞의 ``YYYY-MM-DD``(구분자 - / . , 한 자리 월 · 일 허용) 또는 붙여 쓴 ``YYYYMMDD``.
#: 뒤에 숫자가 이어지면 날짜가 아니다.
_DATE_TOKEN_RE = re.compile(r"^(?:(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})|(\d{4})(\d{2})(\d{2}))(?!\d)")

#: "두 번" 처럼 읽히게 하는 셈말. 표에 없는 수는 숫자로 적는다.
_COUNT_WORDS = {2: "두", 3: "세", 4: "네", 5: "다섯"}


def split_date_text(raw: Any) -> list[str]:
    """쉼표로 이은 날짜 글을 ``YYYY-MM-DD`` 목록으로(정렬 · 중복 제거). 못 읽는 토큰은 버린다."""
    # 숫자 값(JSON 20261105 등)은 글로 적힌 날이 아니라 버린다 — 붙여 쓴 날은 글일 때만 읽는다.
    if raw is None or isinstance(raw, (dict, list, tuple, set, bool, int, float)):
        return []
    found: set[str] = set()
    for token in str(raw).split(","):
        match = _DATE_TOKEN_RE.match(token.strip())
        if not match:
            continue
        year, month, mday = (part for part in match.groups() if part is not None)
        try:
            day = datetime.date(int(year), int(month), int(mday))
        except ValueError:
            continue
        found.add(day.isoformat())
    return sorted(found)


def all_construction_dates(sd: Any) -> list[str]:
    """주문 칸 글 + 취소 안 된 제품 칸의 시공일 전부(``YYYY-MM-DD``, 정렬 · 중복 제거)."""
    if not isinstance(sd, dict):
        return []
    found: set[str] = set()
    schedule = sd.get("schedule")
    construction = schedule.get("construction") if isinstance(schedule, dict) else None
    if isinstance(construction, dict):
        found.update(split_date_text(construction.get("date")))
    for item in active_items(sd):
        found.update(split_date_text(item.get("construction_date")))
    return sorted(found)


def remaining_construction_dates(sd: Any, after: datetime.date) -> list[str]:
    """``after`` 보다 뒤(당일 제외)인 시공일만."""
    limit = after.isoformat()
    return [day for day in all_construction_dates(sd) if day > limit]


def short_date_label(day_iso: str) -> str:
    """``2026-11-05`` → ``11/5`` (화면 한 줄용)."""
    day = datetime.date.fromisoformat(day_iso)
    return f"{day.month}/{day.day}"


def remaining_construction_note(sd: Any, today: Optional[datetime.date] = None) -> str:
    """[시공 완료] 확인 창의 한 줄 — 오늘보다 뒤 시공일이 남았을 때만. 없으면 빈 글."""
    remaining = remaining_construction_dates(sd, today or get_today_kst())
    if not remaining:
        return ""
    return " · ".join(short_date_label(day) for day in remaining) + " 시공이 남아 있어요"


def attach_remaining_construction_notes(rows: Iterable[Any],
                                        today: Optional[datetime.date] = None) -> None:
    """시공 화면 줄 DTO(``structured_data`` 를 든 dict)마다 ``remaining_construction_note`` 를 단다.

    템플릿이 줄 · 카드 뿌리에 ``data-remaining-construction`` 으로 그리고, 확인 창이 주문 번호로 찾아 읽는다.
    """
    day = today or get_today_kst()
    for row in rows:
        if isinstance(row, dict):
            row["remaining_construction_note"] = remaining_construction_note(row.get("structured_data"), day)


def production_split_note(sd: Any) -> str:
    """[제작 완료] 확인 창의 한 줄 — 서로 다른 시공일이 둘 이상일 때만. 아니면 빈 글.

    제작 완료는 원래 시공일 전에 누르므로 "남은 시공" 기준을 쓰면 늘 뜬다 — 날짜 수로 가른다.
    """
    days = all_construction_dates(sd)
    if len(days) < 2:
        return ""
    count = _COUNT_WORDS.get(len(days), str(len(days)))
    labels = " · ".join(short_date_label(day) for day in days)
    return f"시공일이 {labels} {count} 번이에요. 제품이 모두 제작됐나요?"


def pick_nearest_date(days: Iterable[str], today: datetime.date) -> Optional[datetime.date]:
    """여러 날 가운데 오늘 이후(오늘 포함) 가장 가까운 날, 모두 지났으면 마지막 날. 없으면 None."""
    ordered = sorted(day for day in days if day)
    if not ordered:
        return None
    limit = today.isoformat()
    upcoming = [day for day in ordered if day >= limit]
    return datetime.date.fromisoformat(upcoming[0] if upcoming else ordered[-1])
