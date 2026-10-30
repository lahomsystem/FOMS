"""협력사 시공 달력 — 날짜마다 그 협력사 주문 목록(칸 표시 · 날짜를 누르면 뜨는 목록).

우리 모바일 홈 달력은 날짜를 누르면 그날 현장 목록 시트가 뜬다. 협력사 달력도 같은 모양으로 하되 **자기 회사
주문만** 싣는다(다른 협력사 · 우리 직접 주문은 칸의 전체 건수 숫자로만 보인다). 사용자 요청 2026-10-30.

* 그날 = 우리 시공일(``order_schedule_dates`` construction — 여러 날 시공은 날마다) + 아직 시공일을 안 정한 주문의
  희망 시공일(:func:`foms.services.partners.schedule_request.pending_request_ids_by_date`, "희망" 표시).
* 모집단은 달력 숫자 · 출고가와 같은 ``base``(호출자가 회사로 거른 쿼리)라 칸 숫자와 목록 수가 맞는다.
"""
from __future__ import annotations

from typing import Any

from foms.services.partners.orders import partner_stage_label
from foms.services.partners.schedule_request import pending_request_ids_by_date
from models import Order, OrderScheduleDate


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _row(order: Order, requested: bool) -> dict[str, Any]:
    sd = _dict(order.structured_data)
    status = sd.get("drawing_status")
    if requested:
        time = _dict(_dict(sd.get("partner_intake")).get("requested_construction")).get("time")
    else:
        time = _dict(_dict(sd.get("schedule")).get("construction")).get("time")
    stage = (order.erp_stage_code or "").upper()
    return {
        "id": order.id,
        "name": _text(order.customer_name),
        "addr": _text(order.address),
        "product": _text(order.product),
        "time": _text(time),
        "requested": requested,
        "manager": _text(_dict(_dict(sd.get("parties")).get("manager")).get("partner_user_name")),
        "stage_label": partner_stage_label(stage, order.as_axis_status,
                                           None if stage != "CONFIRM" else status == "CONFIRMED",
                                           status == "TRANSFERRED"),
    }


def own_orders_by_day(own_base, dates: list[str]) -> dict[str, list[dict[str, Any]]]:
    """날짜 → 그날 시공(또는 희망 시공) 자기 회사 주문 줄. 시간 순(시간 없는 줄은 뒤), 같은 시간은 번호 순.

    Args:
        own_base: 회사로 거른 주문 쿼리(달력 출고가와 같은 모집단).
        dates: 'YYYY-MM-DD' 목록(그 달 날짜).
    """
    if not dates:
        return {}
    pairs = (
        own_base.join(OrderScheduleDate, OrderScheduleDate.order_id == Order.id)
        .filter(OrderScheduleDate.kind == "construction", OrderScheduleDate.date.in_(list(dates)))
        .with_entities(OrderScheduleDate.date, Order.id)
        .distinct()
        .all()
    )
    by_day: dict[str, list[tuple[int, bool]]] = {}
    for day, order_id in pairs:
        by_day.setdefault(str(day), []).append((int(order_id), False))
    for order_id, day in pending_request_ids_by_date(own_base, dates).items():
        by_day.setdefault(day, []).append((order_id, True))
    ids = {order_id for rows in by_day.values() for order_id, _ in rows}
    if not ids:
        return {}
    orders = {o.id: o for o in own_base.session.query(Order).filter(Order.id.in_(ids)).all()}
    out: dict[str, list[dict[str, Any]]] = {}
    for day, rows in by_day.items():
        items = [_row(orders[order_id], requested) for order_id, requested in rows if order_id in orders]
        items.sort(key=lambda r: (r["time"] == "", r["time"], r["id"]))
        out[day] = items
    return out
