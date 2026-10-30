"""협력사 주문 목록 — 한 줄 목록 칸(시공일 D-몇) · 정렬 단추(사용자 2026-10-30, 목업 승인).

휴대폰 목록이 주문 한 건에 화면 반을 써서 한 줄 목록으로 바꿨다. 줄 왼쪽 날짜 칸 = 우리 시공일(없으면 확정 전
희망 시공일, 주황), 정렬 = 시공일 빠른 순(기본) · 도면 나온 순 · 최근 등록 순. "지금 내 차례"는 정렬과 상관없이 위.
"""
from __future__ import annotations

import datetime
import re
from typing import Any

from models import Order

SORTS = (("date", "시공일 빠른 순"), ("drawing", "도면 나온 순"), ("recent", "최근 등록 순"))
DEFAULT_SORT = "date"
SOON_DAYS = 5
_DOW = "월화수목금토일"
_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")


def pick_sort(value: Any) -> str:
    """요청 인자 → 정렬 키(모르는 값은 기본)."""
    value = str(value or "").strip()
    return value if value in dict(SORTS) else DEFAULT_SORT


def _date(text: Any) -> datetime.date | None:
    m = _DATE_RE.match(str(text or "").strip())
    if not m:
        return None
    try:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def date_cell(day: datetime.date | None, requested: bool, today: datetime.date) -> dict[str, Any]:
    """줄 왼쪽 날짜 칸. 지난 날은 D+몇, 5일 안은 soon(빨강), 희망은 req(주황)."""
    if day is None:
        return {"none": True}
    gap = (day - today).days
    return {
        "none": False, "md": f"{day.month}/{day.day:02d}", "dw": _DOW[day.weekday()],
        "dd": "오늘" if gap == 0 else (f"D-{gap}" if gap > 0 else f"D+{-gap}"),
        "req": requested, "soon": not requested and 0 <= gap <= SOON_DAYS,
    }


def _drawing_times(db, ids: list[int]) -> dict[int, str]:
    """주문별 마지막 도면 전달 시각(UTC 문자열). 회사 주문 몇 건이라 칸 하나만 꺼낸다."""
    if not ids:
        return {}
    expr = Order.structured_data["last_drawing_transfer"]["transferred_at"].as_string()
    return {r[0]: str(r[1]) for r in db.query(Order.id, expr).filter(Order.id.in_(ids)).all() if r[1]}


def decorate_rows(db, rows: list[dict[str, Any]], today: datetime.date) -> None:
    """줄마다 날짜 칸 · 정렬 값 · 도면 전달 시각을 채운다(그 자리에서 고친다)."""
    times = _drawing_times(db, [row["id"] for row in rows])
    for row in rows:
        ours = _date(row.get("construction_date"))
        wish = None if ours else _date(row.get("requested_construction"))
        row["sort_day"] = ours or wish
        row["date_cell"] = date_cell(ours or wish, ours is None and wish is not None, today)
        row["drawing_at"] = times.get(row["id"], "")


def sort_rows(rows: list[dict[str, Any]], sort: str) -> list[dict[str, Any]]:
    """정렬. 내 차례는 늘 위(그 안에서도 같은 정렬). 날짜 · 도면이 없는 줄은 아래(번호 큰 순)."""
    if sort == "date":
        key = lambda r: (not r["turn"], r["sort_day"] is None, r["sort_day"] or datetime.date.max, -r["id"])  # noqa: E731
    elif sort == "drawing":
        key = lambda r: (not r["turn"], not r["drawing_at"], _neg(r["drawing_at"]), -r["id"])  # noqa: E731
    else:
        key = lambda r: (not r["turn"], -r["id"])  # noqa: E731
    return sorted(rows, key=key)


def _neg(text: str) -> tuple[int, ...]:
    """문자열 시각을 내림차순 정렬 키로(글자마다 음수)."""
    return tuple(-ord(c) for c in text)
