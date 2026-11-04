"""출고 화면 협력사 희망 시공일 2주 판 자료(설계서 2026-11-04-shipment-partner-request-board §2.1 · §2.5).

새 집계는 없다 — 날짜 칸 숫자는 왼쪽 "날짜별 잔여 시공"과 같은 ``remaining_panel_dates`` 를 그대로 쓰고, 판 안 주문의
자수는 라우트가 이미 읽은 ``partner_pending`` 주문에서 센다. 판 밖 주문만 :func:`pending_units` 로 따로 읽는다.
"""
from __future__ import annotations

import datetime
from typing import Any

from foms.services.orders.team_labels import team_label
from foms.services.shipment_dashboard_helpers import order_spec_units
from foms.services.partners.schedule_request import recent_partner_schedule_changes
from models import Order

def pending_units(db, order_ids: set[int]) -> dict[int, float]:
    """주문 번호별 자수(W/300 합) — 판 밖 확정 대기 건만 따로 읽을 때. 몇 건이라 주문째 읽는다."""
    if not order_ids:
        return {}
    orders = db.query(Order).filter(Order.id.in_(sorted(order_ids))).all()
    return {int(o.id): round(order_spec_units(o), 1) for o in orders}


BOARD_DAYS = 14
DOW = ("월", "화", "수", "목", "금", "토", "일")
#: 남은 자수가 이보다 적으면 빨강 · "거의 찼어요"(목업 E안).
TIGHT_UNITS = 15
#: 판 아래 기록에 처음 보이는 줄 수(나머지는 [더 보기]).
HISTORY_SHOWN = 6
_KST = datetime.timedelta(hours=9)


def _md_dow(day: str) -> str:
    try:
        d = datetime.date.fromisoformat(day)
    except (TypeError, ValueError):
        return ""
    return f"{day[5:]} ({DOW[d.weekday()]})"


def build_request_board(
    db,
    pending: list[dict[str, Any]],
    partner_pending: list[tuple[Any, str]],
    remaining_panel_dates: list[dict[str, Any]],
    today: datetime.date,
) -> dict[str, Any]:
    """판 자료 ``{days, later, single_partner, history, history_more, count}``. pending 은 ``shipment_pending_requests``."""
    units = {int(o.id): round(order_spec_units(o, target_date=day), 1) for o, day in partner_pending}
    missing = {p["id"] for p in pending if p["id"] not in units}
    units.update(pending_units(db, missing))
    partners = {p["partner_name"] for p in pending if p["partner_name"]}
    single = next(iter(partners)) if len(partners) == 1 else ""

    first = (today + datetime.timedelta(days=1)).isoformat()
    last = (today + datetime.timedelta(days=BOARD_DAYS)).isoformat()
    tomorrow = first
    by_date: dict[str, list[dict[str, Any]]] = {}
    later: list[dict[str, Any]] = []
    for p in pending:
        chip = {**p, "units": units.get(p["id"], 0.0), "label_partner": "" if single else p["partner_name"]}
        if p["date"] and first <= p["date"] <= last:
            by_date.setdefault(p["date"], []).append(chip)
        else:
            later.append(chip)

    days = []
    for item in remaining_panel_dates:
        day = item.get("date") or ""
        if not (first <= day <= last):
            continue
        total = float(item.get("total_capacity") or 0)
        used = float(item.get("used_capacity") or 0)
        remaining = round(total - used, 1)
        days.append({
            "date": day, "label": _md_dow(day), "is_tomorrow": day == tomorrow,
            "is_off": bool(item.get("is_weekend") or item.get("is_holiday")),
            "is_holiday": bool(item.get("is_holiday")),
            "remaining": remaining, "tight": remaining < TIGHT_UNITS,
            "fill": int(max(0, min(100, (used / total * 100) if total > 0 else 0))),
            "items": by_date.get(day, []),
        })

    history = []
    for h in recent_partner_schedule_changes(db):
        at = h["at"] + _KST if isinstance(h["at"], datetime.datetime) else None
        history.append({
            **h, "at_text": at.strftime("%m-%d %H:%M") if at else "",
            "hope_text": _md_dow(h["hope"]) if h["hope"] else "", "after_text": _md_dow(h["after"]),
            "before_text": _md_dow(h["before"]) if h["before"] else "",
            "moved": bool(h["hope"]) and not h["before"] and h["hope"] != h["after"],
            "actor": " ".join(x for x in (h["actor_name"], f"({team_label(h['actor_team'])})" if h["actor_team"] else "") if x),
        })
    return {
        "count": len(pending), "days": days, "later": later, "single_partner": single,
        "history": history[:HISTORY_SHOWN], "history_more": history[HISTORY_SHOWN:],
        "earliest": next((d for d in days if d["items"]), None),
        "tight_units": TIGHT_UNITS,
    }
