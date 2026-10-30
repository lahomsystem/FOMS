"""PARTNER-FOMS 18-2: 협력사 시공 달력 — 날짜마다 시공 건수(우리 회사 전체) · 그 협력사 주문 출고가.

협력사 담당자가 시공이 몰린 날을 보고 희망 시공일을 고르게 한다. 스펙 docs/specs/2026-10-19-partner-foms-mode_SPEC.md §18.4.

* 건수 = 우리 회사 전체 시공 건수(숫자만 — 고객 · 주소 · 다른 협력사 이름은 싣지 않는다). 모집단 · 셈은 우리 모바일 홈
  달력과 같다(``dashboard_control_tower._day_counts`` — 최근 60일 활성 ERP 주문의 ``order_schedule_dates`` 시공).
* 날씨 = 우리 달력과 같은 하루 날씨 · 기온 · 주마다 '시간 줄' 띠(사용자 요청 2026-10-21).
* 금액 = 그 협력사 주문의 출고가만(``_construction_amounts`` — 여러 날 시공은 날짜 수로 나눈다). 우리 전체 매출은 싣지 않는다.
* 내 회사 주문 = 칸마다 따로 세고, 날짜를 누르면 그날 내 회사 주문 목록이 뜬다(우리 모바일 홈처럼 — 사용자 2026-10-30,
  :mod:`foms.services.partners.calendar_day_orders`).
"""
from __future__ import annotations

import datetime
from typing import Any

from foms.services.common.business_calendar import get_holidays_kr
from foms.services.datetime_kst import get_today_kst
from foms.services.partners.calendar_day_orders import own_orders_by_day
from foms.services.orders.calendar_month_photos import month_photo
from foms.services.orders.dashboard_control_tower import (
    _construction_amounts,
    _day_counts,
    _man_label,
    _month_first,
    _month_gap,
    _pill_label,
    _shift_month,
    _weather_legend,
    _weather_window,
)
from models import Order

# 협력사 달력이 넘겨 볼 수 있는 달(이번 달 기준 앞뒤).
MONTH_SPAN = 6


def _base(db):
    """우리 모바일 홈 달력과 같은 모집단(시공팀 개인 거르기는 없음)."""
    return db.query(Order).filter(Order.dashboard_active_filter(days=60), Order.is_erp_order.is_(True))


def _weather_cell(wx_day: Any) -> dict[str, Any]:
    """우리 모바일 홈 달력과 같은 날씨 칸(하루 날씨 · 최고/최저 · 6시간 칸 4개). 자료 없는 날은 wx=""."""
    day = wx_day if isinstance(wx_day, dict) else {}
    wx = str(day.get("kind") or "")
    slots, detail = day.get("slots"), day.get("slot_detail")
    t_max, t_min = day.get("t_max"), day.get("t_min")
    return {
        "wx": wx,
        "t_max_label": f"{t_max}°" if wx and t_max is not None else "",
        "t_min_label": f"{t_min}°" if wx and t_min is not None else "",
        "wx_slots": list(slots) if wx and isinstance(slots, list) and len(slots) == 4 else None,
        "wx_detail": list(detail) if wx and isinstance(detail, list) and len(detail) == 4 else None,
    }


def partner_construction_calendar(db, org_id: int, month: str | None = None,
                                  today: datetime.date | None = None) -> dict[str, Any]:
    """월 달력(일요일 시작 주 격자). 칸 = 날짜 · 전체 시공 건수 · 그 협력사 출고가."""
    today = today or get_today_kst()
    this_month = today.replace(day=1)
    first = _month_first(month, today)
    if abs(_month_gap(first, this_month)) > MONTH_SPAN:
        first = this_month
    next_first = _shift_month(first, 1)
    last = next_first - datetime.timedelta(days=1)
    dates = [(first + datetime.timedelta(days=i)).isoformat() for i in range(last.day)]
    base = _base(db)
    _measure, cons_by, _as = _day_counts(base, dates)
    own_base = base.filter(Order.partner_org_id == org_id)
    amount_by, month_amount = _construction_amounts(own_base, dates)
    day_orders = own_orders_by_day(own_base, dates)
    holidays = get_holidays_kr(first.year)
    wx_days = (_weather_window(db, first) or {}).get("days") or {}

    grid_start = first - datetime.timedelta(days=(first.weekday() + 1) % 7)
    grid_end = last + datetime.timedelta(days=(5 - last.weekday()) % 7)
    weeks: list[list[dict[str, Any]]] = []
    day = grid_start
    while day <= grid_end:
        week = []
        for col in range(7):
            iso = day.isoformat()
            in_month = first <= day <= last
            count = int(cons_by.get(iso, 0) or 0) if in_month else 0
            amount = int(amount_by.get(iso, 0) or 0) if in_month else 0
            cell = {
                "iso": iso, "day": day.day, "dow": col, "in_month": in_month,
                "is_today": day == today, "is_past": day < today, "is_holiday": iso in holidays,
                "count": count, "own": len(day_orders.get(iso, ())) if in_month else 0,
                "amount_pill": _pill_label(amount), "amount_label": _man_label(amount),
            }
            cell.update(_weather_cell(wx_days.get(iso) if in_month else None))
            week.append(cell)
            day += datetime.timedelta(days=1)
        weeks.append(week)

    prev_first = _shift_month(first, -1)
    return {
        "month": first.strftime("%Y-%m"),
        "label": f"{first.year}년 {first.month}월",
        "is_this_month": first == this_month,
        "photo": month_photo(first.month),  # 우리 달력과 같은 달 사진 머리띠(흰 글씨가 읽히게)
        "prev": prev_first.strftime("%Y-%m") if abs(_month_gap(prev_first, this_month)) <= MONTH_SPAN else None,
        "next": next_first.strftime("%Y-%m") if abs(_month_gap(next_first, this_month)) <= MONTH_SPAN else None,
        "weeks": weeks,
        "construction_total": sum(int(v or 0) for v in cons_by.values()),
        "wx_legend": _weather_legend([c for w in weeks for c in w if c["in_month"] and c["wx"]]),
        "own_amount_label": _man_label(month_amount) or "0원",
        "own_total": len({row["id"] for rows in day_orders.values() for row in rows}),
        # 홈 대시보드 '오늘' 줄(우리 모바일 홈 오늘 요약 자리) — 이 달에 오늘이 있을 때만.
        "today": next(({"iso": c["iso"], "label": f"{first.month}/{c['day']} ({'일월화수목금토'[c['dow']]})",
                        "count": c["count"], "own": c["own"], "amount": c["amount_label"]}
                       for w in weeks for c in w if c["in_month"] and c["is_today"]), None),
        "day_orders": day_orders,
        # 날짜 고르기 달력(flatpickr)이 칸마다 붙일 숫자 — 이 달 칸만.
        "days": {c["iso"]: {"count": c["count"], "amount": c["amount_pill"]}
                 for w in weeks for c in w if c["in_month"]},
    }
