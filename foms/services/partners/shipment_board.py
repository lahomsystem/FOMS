"""협력사 '출고' 탭 — 우리 출고 탭(/erp/shipment)의 하루치 출고표를 그 협력사 주문만으로(읽기만).

사용자 2026-11-12: "출고 탭을 만들어 > 협력사 본인들 스케줄 알 수 있게 (우리 erp 출고탭에서 라운즈 것만 따로
보여 줘) · 모바일 대응". 협력사는 주문 · 실측까지만 하고 시공 · 출고는 우리가 하므로, 협력사 담당자가 "언제 ·
누가 · 몇 시에" 가는지를 우리 출고표와 같은 순서로 본다.

* 그날 줄 = 우리 출고 탭과 같은 규칙 — 우리 시공일(``order_schedule_dates`` construction, 여러 날이면 날마다) +
  AS 주문의 AS 방문일(as_visit) + 아직 우리 시공일이 없는 주문의 희망 시공일("희망 · 확정 전").
  모두 ``partner_org_id`` 로 그 회사 주문만 거른다.
* 시공자 묶음 · 번호 · 사람 색 = 우리 태블릿 하루치 출고표와 같은 함수(:func:`build_tablet_day_sheet`).
* 싣는 칸 = 번호 · 제품 · 현장주소 · 고객 · 연락처 · 시공시간 · 담당 · 시공자. 금액 · 자수 · 우리 메모 · AS 내용 ·
  도면 담당은 싣지 않는다 — 화면에는 ORM 이 아니라 이 모듈이 만든 dict 만 넘긴다.
* 날짜 띠 = 오늘부터 14일(우리 출고 탭 날짜 버튼과 같은 폭). 그 밖의 날은 날짜 칸(``?date=``)으로.
"""
from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy import and_, or_

from foms.services.erp_template_filters import strip_product_w_filter
from foms.services.erp_shipment_settings import load_erp_shipment_settings, normalize_erp_shipment_workers
from foms.services.partners.schedule_request import clean_date, pending_request_ids_by_date
from foms.services.shipment.tablet_day_sheet import build_tablet_day_sheet
from foms.services.shipment_dashboard_display import sort_shipment_rows
from foms.services.shipment_dashboard_helpers import AS_SHIPMENT_STATUSES, visible_items_for_dates
from foms.services.common.business_calendar import get_holidays_kr
from models import Order, OrderScheduleDate

STRIP_DAYS = 14
_WEEKDAYS = "월화수목금토일"


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _base(db, org_id: int):
    """그 회사의 살아 있는 주문(지운 것 · 초안 제외)."""
    return db.query(Order).filter(Order.active_filter(), Order.partner_org_id == org_id)


def _ids_by_day(base, dates: list[str]) -> dict[str, dict[int, bool]]:
    """날짜 → {주문 번호: 희망(확정 전)인가}. 우리 출고 탭과 같은 술어(시공 · AS 방문) + 확정 대기 희망 시공일."""
    out: dict[str, dict[int, bool]] = {}
    if not dates:
        return out
    pairs = (
        base.join(OrderScheduleDate, OrderScheduleDate.order_id == Order.id)
        .filter(
            or_(
                and_(Order.status.in_(AS_SHIPMENT_STATUSES), OrderScheduleDate.kind == "as_visit"),
                OrderScheduleDate.kind == "construction",
            ),
            OrderScheduleDate.date.in_(list(dates)),
        )
        .with_entities(OrderScheduleDate.date, Order.id)
        .distinct()
        .all()
    )
    for day, order_id in pairs:
        out.setdefault(str(day), {})[int(order_id)] = False
    for order_id, day in pending_request_ids_by_date(base, dates).items():
        out.setdefault(day, {}).setdefault(order_id, True)
    return out


def _strip(today: datetime.date, counts: dict[str, int], selected: str) -> list[dict[str, Any]]:
    holidays = get_holidays_kr(today.year) | get_holidays_kr((today + datetime.timedelta(days=STRIP_DAYS)).year)
    days = []
    for i in range(STRIP_DAYS):
        d = today + datetime.timedelta(days=i)
        iso = d.isoformat()
        days.append({
            "iso": iso, "day": d.day, "weekday": _WEEKDAYS[d.weekday()],
            "count": counts.get(iso, 0), "is_today": i == 0, "is_selected": iso == selected,
            "is_off": d.weekday() >= 5 or iso in holidays,
        })
    return days


def _pick_day(requested: str, today: datetime.date, counts: dict[str, int]) -> str:
    """고른 날. 주소에 날짜가 없으면 오늘, 오늘이 비면 띠 안에서 일이 있는 가장 가까운 날(빈 첫 화면을 피한다)."""
    if requested:
        return requested
    for i in range(STRIP_DAYS):
        iso = (today + datetime.timedelta(days=i)).isoformat()
        if counts.get(iso):
            return iso
    return today.isoformat()


def _product_text(items: list[dict], fallback: str) -> str:
    names = [strip_product_w_filter(_text(it.get("product_name"))) for it in items if isinstance(it, dict)]
    names = [n for n in names if n]
    if not names:
        return strip_product_w_filter(fallback) or ""
    return names[0] + (f" 외 {len(names) - 1}" if len(names) > 1 else "")


def _row(entry: dict[str, Any], requested: bool) -> dict[str, Any]:
    """협력사에게 보여 줄 한 줄(dict). 금액 · 자수 · 우리 메모 · AS 내용은 넣지 않는다."""
    order = entry["order"]
    sd = _dict(order.structured_data)
    shipment = _dict(sd.get("shipment"))
    if requested:
        time, plan = _text(_dict(_dict(sd.get("partner_intake")).get("requested_construction")).get("time")), True
    else:
        time, plan = _text(shipment.get("construction_time")), False
        if not time:
            time, plan = _text(_dict(_dict(sd.get("schedule")).get("construction")).get("time")), True
    return {
        "id": order.id,
        "no": entry["no"],
        "is_as": entry["is_as"],
        "requested": requested,
        "customer": _text(order.customer_name),
        "phone": _text(order.phone),
        "address": _text(order.address),
        "product": _product_text(getattr(order, "shipment_visible_items", None) or [], _text(order.product)),
        "time": time,
        "time_is_plan": plan and bool(time),
        "manager": _text(_dict(_dict(sd.get("parties")).get("manager")).get("partner_user_name")),
        "workers": [{"name": w["name"], "color": w["color_index"]} for w in entry["workers"]],
    }


def partner_shipment_board(db, org_id: int, date: str | None, today: datetime.date) -> dict[str, Any]:
    """협력사 출고 탭 한 화면 — 날짜 띠(14일 · 날마다 내 회사 건수) + 고른 날 시공자 묶음.

    Args:
        db: 세션.
        org_id: 협력사 회사 번호(로그인한 협력사 계정의 회사 — 호출자가 정한다).
        date: 주소의 ``?date=`` (틀린 값은 버린다).
        today: 오늘(KST).

    Returns:
        {'selected', 'label', 'is_today', 'is_outside', 'days', 'groups': [{'unassigned', 'lead', 'rows': [...]}],
         'total', 'unassigned'}.
    """
    base = _base(db, org_id)
    strip_dates = [(today + datetime.timedelta(days=i)).isoformat() for i in range(STRIP_DAYS)]
    wanted = clean_date(date)
    by_day = _ids_by_day(base, strip_dates if not wanted or wanted in strip_dates else strip_dates + [wanted])
    counts = {day: len(ids) for day, ids in by_day.items()}
    selected = _pick_day(wanted, today, counts)

    picked = by_day.get(selected) or {}
    orders = base.filter(Order.id.in_(list(picked))).all() if picked else []
    for order in orders:
        order.shipment_visible_items = visible_items_for_dates(order, target_date=selected)
    sort_shipment_rows(orders)
    workers = normalize_erp_shipment_workers(load_erp_shipment_settings().get("construction_workers", []))
    sheet = build_tablet_day_sheet(orders, workers, selected)

    groups = []
    for group in sheet["groups"]:
        rows = [_row(entry, picked.get(entry["order"].id, False)) for entry in group["rows"]]
        lead = rows[0]["workers"][0] if rows and rows[0]["workers"] and not group["unassigned"] else None
        groups.append({"unassigned": group["unassigned"], "lead": lead, "rows": rows})
    day = datetime.date.fromisoformat(selected)
    return {
        "selected": selected,
        "label": f"{day.month}월 {day.day}일 ({_WEEKDAYS[day.weekday()]})",
        "is_today": day == today,
        "is_outside": selected not in strip_dates,
        "days": _strip(today, counts, selected),
        "groups": groups,
        "total": sheet["total"],
        "unassigned": sheet["unassigned"],
    }
