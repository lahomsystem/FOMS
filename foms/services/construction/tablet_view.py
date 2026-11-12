"""태블릿 가로 시공 탭 — 화면 모드 고르기 · 상세(3분할) 왼쪽 목록 (설계서 tablet-production-ui §13.3 · P13-3 · P13-4).

모드 (같은 주소 ``/erp/construction/dashboard``, 태블릿 가로에서만 보이는 표면)
* ``first``  — 첫 화면(날짜 버튼 + 시공자 묶음). ``?date=`` · ``?worker=``.
* ``detail`` — 상세 = 지금 3분할. ``?focus_order=`` (+ ``date`` · ``worker``) — 왼쪽은 그날 · 그 시공자 집.
* ``search`` — ``?q=`` 찾기 결과를 3분할 왼쪽에(지금 검색 그대로).
* ``undated`` — ``?undated=1`` 날짜 미정 집(시공 단계 · 시공일 없음)을 3분할 왼쪽에(D43 a51, 캡 200).
* ``''``     — 태블릿 가로 표면이 아니다(PC · 폰 · 코호트 밖) — 지금 그대로.

판정은 ``erp_mobile_v2 and coarse_pointer and wide_only`` 일 때만 한다. 폰은 화면 긴 변이 992px 보다 짧아
태블릿 가로 CSS 가 절대 안 보이므로 첫 화면 쿼리 둘을 아낀다(``wide_only_surfaces`` = 화면 긴 변 쿠키).
읽기만 한다.
"""
from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy import select

from foms.services.construction.tablet_first import (
    DAY_ROWS_CAP,
    fetch_day_orders,
    fetch_undated_orders,
    is_as_status,
    parse_day,
    production_note,
    scope_conditions,
    time_sort_key,
)
from foms.services.datetime_kst import get_today_kst
from models import OrderScheduleDate

_WEEKDAYS = ("월", "화", "수", "목", "금", "토", "일")


def tablet_mode(*, mobile_v2: bool, coarse: bool, wide: bool, focus_order_id: Any, q: str, undated: bool = False) -> str:
    """태블릿 가로 화면 모드(위 머리말)."""
    if not (mobile_v2 and coarse and wide):
        return ""
    if focus_order_id:
        return "detail"
    if (q or "").strip():
        return "search"
    return "undated" if undated else "first"


def day_label(day: str | None) -> str:
    """``11/13(금)``."""
    if not day:
        return ""
    d = datetime.date.fromisoformat(day)
    return f"{d.month}/{d.day}({_WEEKDAYS[d.weekday()]})"


def resolve_focus_day(db: Any, order_id: int, today: datetime.date | None = None, *, is_as: bool = False) -> str | None:
    """옛 딥링크(날짜 없음)의 날짜 — 오늘 이후 가장 가까운 날, 없으면 가장 최근 날(쿼리 1).

    첫 화면 짝 규칙(D43)과 같은 종류를 먼저 본다: AS 상태 집 = AS 방문일, 그 밖 = 시공일. 그 종류가 없을 때만 다른 종류.
    (AS 집을 시공일로 열면 그날 첫 화면에 그 집이 없어 왼쪽 목록과 수가 어긋났다 — 스테이징 11-12.)
    """
    rows = db.execute(
        select(OrderScheduleDate.kind, OrderScheduleDate.date).where(
            OrderScheduleDate.order_id == order_id, OrderScheduleDate.kind.in_(("construction", "as_visit")))
    ).all()
    want = "as_visit" if is_as else "construction"
    days = sorted({str(d) for k, d in rows if k == want and parse_day(d)}) or sorted({str(d) for _k, d in rows if parse_day(d)})
    if not days:
        return None
    base = (today or get_today_kst()).isoformat()
    upcoming = [d for d in days if d >= base]
    return upcoming[0] if upcoming else days[-1]


def build_detail(db: Any, *, focus: Any, user: Any, mine_only: bool, partner_org: str,
                 date_arg: Any, worker_arg: Any, today: datetime.date | None = None) -> dict:
    """상세 왼쪽 목록 = 고른 날 · 고른 시공자 집(쿼리 B 그날 하나). 누른 집은 늘 든다(맨 앞에 끼움).

    Args:
        focus: 라우트가 이미 찾고 범위(mine)를 본 주문 1건.
        date_arg: ``?date=``(없으면 그 주문 시공일로 잡는다). worker_arg: ``?worker=``(없으면 전체).

    Returns:
        {'orders': 주문 목록(시간 순), 'date', 'date_label', 'worker', 'focus_id'}.
    """
    day = parse_day(date_arg) or resolve_focus_day(db, focus.id, today, is_as=is_as_status(focus))
    worker = str(worker_arg or "").strip()
    orders: list[Any] = []
    if day:
        conds = scope_conditions(user=user, mine_only=mine_only, partner_org=partner_org, worker=worker)
        orders = sorted((o for _d, o in fetch_day_orders(db, conds, [day])), key=lambda o: (time_sort_key(o), o.id))
    if all(o.id != focus.id for o in orders):
        orders = [focus] + orders
    return {"orders": orders, "date": day, "date_label": day_label(day), "worker": worker, "focus_id": focus.id}


def build_undated(db: Any, *, user: Any, mine_only: bool, partner_org: str, date_arg: Any, worker_arg: Any) -> dict:
    """``?undated=1`` 상세 왼쪽 = 날짜 미정 집(D43 a51) — 첫 화면과 같은 범위 · 사람 칸, 캡 200(넘치면 ``more``).

    Returns:
        {'orders', 'count'(보이는 수), 'more'(캡 넘음), 'date', 'worker', 'focus_id'(첫 집)}.
    """
    worker = str(worker_arg or "").strip()
    conds = scope_conditions(user=user, mine_only=mine_only, partner_org=partner_org, worker=worker)
    rows = fetch_undated_orders(db, conds)
    more = len(rows) > DAY_ROWS_CAP
    rows = rows[:DAY_ROWS_CAP]
    return {"orders": rows, "count": len(rows), "more": more, "date": parse_day(date_arg) or "",
            "worker": worker, "focus_id": rows[0].id if rows else None}


def annotate_rows(rows: list[dict]) -> None:
    """3분할 줄 DTO 에 상세 가운데 안내 한 줄을 단다(D43 — 같은 말 한 번): 생산중 · AS 방문 집만."""
    for row in rows:
        if row.get("stage") == "생산중":
            row["tablet_note"] = production_note(row.get("structured_data") or {})
        elif row.get("stage") == "AS 방문":
            row["tablet_note"] = "AS 방문 집이에요"
