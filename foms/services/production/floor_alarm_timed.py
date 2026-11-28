"""생산 현장 알람 #21 — "오늘 나가는 주문이 아직 안 끝났어요" 띠(설계서 2026-11-28 생산 현장 알람 §4-6 · 사장님 답 2차 4).

사건이 아니라 **시각**이라 웹 요청으로는 못 만든다 — WORKER 1분 알림 루프(``scripts/maintenance/run_notification_escalation.py``)의
한 단계로 돈다. 한국 시각 **오전 9시 · 오후 1시** 칸마다 그 뒤 첫 바퀴에 한 번, 공장마다 반장에게 띠 **하나**(주문마다 따로 울리지 않는다).

* 무엇을: 생산 단계 주문 가운데 출고일(지방은 상차일, 그 밖은 시공일 — 날짜 탭과 같은 :func:`~foms.services.production.ship_dates.order_ship_dates`)이
  오늘이고 그 공장 몫 제작이 안 끝난 것. 없으면 안 보낸다.
* 한 번만: 그 칸이 시작된 뒤 만든 이 종류 알림 줄이 있으면 이미 보낸 것이다(새 표 없음 — 쿼리 1). 이 프로세스가 끝냈다고 아는 칸은
  다시 묻지 않는다(쿼리 0) — 자기가 방금 만든 줄은 커밋이 실패할 수 있어 기억하지 않고, 다음 바퀴가 줄을 읽어 기억한다.
* 쿼리: 스위치 꺼짐 · 칸 전 · 끝낸 칸 = 0. 칸의 첫 바퀴 = 보냈나 찾기 1 + 주문 읽기 1 + 반장 읽기 1(+ 받는 사람마다 넣기 3).
* 커밋 · 배달은 부르는 쪽이 한다(:func:`run` → 커밋 → :func:`deliver`). 스위치 · 받는 사람 문 · 줄 만들기는 알람 모듈 것을 그대로 쓴다.
"""

from __future__ import annotations

import datetime
from typing import Any, Optional

from foms.services.datetime_kst import now_kst, to_utc_naive
from foms.services.orders.drawing_factory import factory_made, present_factories
from foms.services.production import floor_alarm
from foms.services.production import floor_alarm_rules as rules
from foms.services.production import floor_alarm_text as T
from foms.services.production.factory_constants import DEFAULT_FACTORY, account_production_factory
from foms.services.production.ship_dates import order_ship_dates, window_condition
from models import Notification, Order

#: 띠를 내는 한국 시각 칸(시) — 사장님 답 2차 4 "오전 9시 · 오후 1시 두 번".
SLOT_HOURS: tuple[int, ...] = (9, 13)
_PRODUCTION_STAGE_CODES = ("PRODUCTION", "생산")
#: 이 프로세스가 끝냈다고 아는 칸(``{'day': 'YYYY-MM-DD', 'slots': {9, 13}}``) — 날이 바뀌면 비운다.
_DONE: dict[str, Any] = {"day": "", "slots": set()}


def current_slot(now: datetime.datetime) -> Optional[int]:
    """지금 속한 칸(시) — 9시 전이면 None, 9시 ~ 13시 전 = 9, 13시 뒤 = 13."""
    passed = [hour for hour in SLOT_HOURS if now.hour >= hour]
    return passed[-1] if passed else None


def _done_slots(today: datetime.date) -> set[int]:
    if _DONE["day"] != today.isoformat():
        _DONE["day"], _DONE["slots"] = today.isoformat(), set()
    return _DONE["slots"]


def _customer(order: Any) -> str:
    sd = order.structured_data if isinstance(order.structured_data, dict) else {}
    name = ((sd.get("parties") or {}).get("customer") or {}).get("name") or getattr(order, "customer_name", None)
    return str(name or "").strip()


def due_by_factory(db: Any, today: datetime.date) -> dict[int, list[str]]:
    """공장 → 오늘 나가는데 아직 안 끝난 주문의 고객 이름들(주문 번호 순) — 쿼리 1."""
    day = today.isoformat()
    orders = (db.query(Order)
              .filter(Order.active_filter(), Order.is_erp_order.is_(True), Order.erp_stage_code.in_(_PRODUCTION_STAGE_CODES),
                      window_condition(day, day))
              .order_by(Order.id.asc()).all())
    out: dict[int, list[str]] = {}
    for order in orders:
        if today not in [ship_day for ship_day, _kind in order_ship_dates(order)]:
            continue
        sd = order.structured_data if isinstance(order.structured_data, dict) else {}
        for factory in present_factories(sd) or (DEFAULT_FACTORY,):
            if not factory_made(sd, factory):
                out.setdefault(factory, []).append(_customer(order))
    return out


def run(db: Any, *, now: Optional[datetime.datetime] = None) -> dict[str, Any]:
    """알림 루프 한 바퀴의 이 단계 — 줄을 세션에 만들기까지(커밋은 부르는 쪽).

    Args:
        db: 세션.
        now: 기준 시각(시간대 있는 KST 값 — 시험이 넣는다). 없으면 ``now_kst()``.

    Returns:
        ``{enabled, slot, orders, notifications, outbox}`` — ``outbox`` 는 커밋 뒤 :func:`deliver` 에 넘긴다(보낼 것이 없으면 None).
    """
    result: dict[str, Any] = {"enabled": floor_alarm.enabled(), "slot": None, "orders": 0, "notifications": 0, "outbox": None}
    if not result["enabled"]:
        return result
    now = now or now_kst()
    today, slot = now.date(), current_slot(now)
    if slot is None or slot in _done_slots(today):
        return result
    result["slot"] = slot
    since = to_utc_naive(now.replace(hour=slot, minute=0, second=0, microsecond=0))
    already = (db.query(Notification.id)
               .filter(Notification.notification_type == T.NOTICE_DUE_TODAY, Notification.created_at >= since).first())
    if already is not None:  # 커밋된 줄 — 이 칸은 끝났다(다른 WORKER 가 보냈어도 같다)
        _done_slots(today).add(slot)
        return result
    due = due_by_factory(db, today)
    result["orders"] = sum(len(names) for names in due.values())
    reads = rules.Reads(db, to_utc_naive(now), today)
    alarms = []
    for lead in reads.leads() if due else []:
        names = due.get(account_production_factory(lead) or DEFAULT_FACTORY)
        if names:
            title, message = T.due_today(names)
            alarms.append(rules.Alarm(int(lead.id), T.NOTICE_DUE_TODAY, title, message))
    if not alarms:  # 이 칸에 보낼 것이 없다 — 한 번 본 것으로 끝(다음 칸에 다시 본다)
        _done_slots(today).add(slot)
        return result
    outbox = floor_alarm.Outbox()
    floor_alarm.save(db, reads, rules.Plan(alarms=alarms), outbox)
    result.update(notifications=len(alarms), outbox=outbox)
    return result


def deliver(db: Any, result: dict[str, Any]) -> None:
    """커밋 뒤 — 받는 반장의 종 숫자 · 실시간(띠라 폰 알림은 없다). 보낼 것이 없으면 아무 일도 없다."""
    if result.get("outbox") is not None:
        floor_alarm.deliver(db, result["outbox"])


__all__ = ["SLOT_HOURS", "current_slot", "deliver", "due_by_factory", "run"]
