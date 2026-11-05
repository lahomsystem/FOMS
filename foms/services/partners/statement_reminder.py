"""협력사 명세서 발행 알림 — 출고 전날까지 발행 안 된 협력사 주문을 우리 CS 에 알린다(사용자 결정 2026-11-05, 설계서 0.1-13).

발행은 사람이 누른다(설계서 열린 질문 7). 이 알림은 누를 차례를 놓치지 않게만 한다 — 명세서를 만들거나 발행하지 않는다.

* 대상: 단가표(ACTIVE)가 있는 협력사의 주문, 지우지 않음, 발행(ISSUED) 명세서 없음, 출고일이 KST 내일 이하이고
  :data:`LOOKBACK_DAYS` 일 안(오래 지난 옛 주문을 날마다 깨우지 않게). 옵션이 아직 없는 주문도 넣는다(운영 11-05: 출고 가까운 8건 중
  6건이 옵션 없음 — 그게 막힌 곳이다).
* 때: KST :data:`SEND_HOUR` 시 이후 첫 바퀴. 워커 알림 루프(1분)에 얹는다(``run_notification_escalation``).
* 한 번만: 주문 · 출고일마다 한 번. 알린 열쇠는 SystemSetting :data:`STATE_KEY` 에 남기고, 그 줄을 잠근 같은 트랜잭션에서 알림을 만든다
  (워커가 둘이어도 두 번 안 간다). 출고일이 바뀌면 새 열쇠라 다시 알린다.
"""
from __future__ import annotations

import copy
import datetime
from typing import Any, Optional

from sqlalchemy.orm.attributes import flag_modified

from foms.services.datetime_kst import now_kst
from foms.services.notifications.recipients import fan_out_new_notification
from foms.services.partners.statements import ISSUED, ship_date
from foms.services.partners.view import build_partner_order_view
from models import Notification, Order, PartnerPriceList, PartnerStatement, SystemSetting

STATE_KEY = "partner_statement_reminder_state"
NOTIFICATION_TYPE = "PARTNER_STATEMENT_DUE"
TITLE = "협력사 명세서 발행 대기"
SEND_HOUR = 9
LOOKBACK_DAYS = 7
#: 알린 열쇠를 남겨 두는 날 수(지난 열쇠는 지운다).
KEEP_DAYS = 30


def _candidates(db, today: datetime.date) -> list[tuple[Order, datetime.date]]:
    org_ids = {oid for (oid,) in db.query(PartnerPriceList.partner_org_id).filter(
        PartnerPriceList.status == "ACTIVE").distinct().all()}
    if not org_ids:
        return []
    issued = {oid for (oid,) in db.query(PartnerStatement.order_id).filter(
        PartnerStatement.status == ISSUED).distinct().all()}
    orders = db.query(Order).filter(Order.active_filter(), Order.partner_org_id.in_(org_ids),
                                    Order.status != "CANCELLED").all()
    floor, ceil = today - datetime.timedelta(days=LOOKBACK_DAYS), today + datetime.timedelta(days=1)
    out = []
    for order in orders:
        on_date = ship_date(order)
        if order.id not in issued and on_date is not None and floor <= on_date <= ceil:
            out.append((order, on_date))
    return sorted(out, key=lambda pair: (pair[1], pair[0].id))


def _message(order: Order, on_date: datetime.date, today: datetime.date) -> str:
    customer = build_partner_order_view(order).get("customer_name") or ""
    when = "내일" if on_date > today else ("오늘" if on_date == today else "지난")
    head = f"[협력사] 주문 #{order.id}" + (f" ({customer})" if customer else "")
    return f"{head} {when} 출고({on_date.month}월 {on_date.day}일)인데 명세서가 아직 발행되지 않았습니다. 협력사 명세서에서 확인해 주세요."


def remind_unissued_partner_statements(db, *, now: Optional[datetime.datetime] = None) -> dict[str, Any]:
    """알릴 주문에 CS 알림을 만든다(커밋은 부르는 쪽). → ``{checked, reminded, created_notification_ids, recipient_user_ids}``."""
    now = now or now_kst()
    result: dict[str, Any] = {"checked": 0, "reminded": 0, "created_notification_ids": [], "recipient_user_ids": []}
    if now.hour < SEND_HOUR:
        return result
    today = now.date()
    row = db.get(SystemSetting, STATE_KEY, populate_existing=True, with_for_update=True)
    state = copy.deepcopy(row.setting_value) if row is not None and isinstance(row.setting_value, dict) else {}
    alerted = dict(state.get("alerted") or {})
    pairs = _candidates(db, today)
    result["checked"] = len(pairs)
    recipients: set[int] = set()
    for order, on_date in pairs:
        key = f"{order.id}:{on_date.isoformat()}"
        if key in alerted:
            continue
        note = Notification(order_id=order.id, notification_type=NOTIFICATION_TYPE, target_team="CS", title=TITLE,
                            message=_message(order, on_date, today), created_by_name="FOMS")
        db.add(note)
        db.flush()
        recipients.update(int(s.user_id) for s in fan_out_new_notification(db, note, actor_user_id=None))
        result["created_notification_ids"].append(note.id)
        alerted[key] = today.isoformat()
    if not result["created_notification_ids"]:
        return result
    floor = (today - datetime.timedelta(days=KEEP_DAYS)).isoformat()
    state["alerted"] = {k: v for k, v in alerted.items() if str(v) >= floor}
    if row is None:
        row = SystemSetting(setting_key=STATE_KEY, description="협력사 명세서 발행 알림 — 알린 주문 · 출고일", version=1)
        db.add(row)
    row.setting_value = state
    flag_modified(row, "setting_value")
    db.flush()
    result["reminded"] = len(result["created_notification_ids"])
    result["recipient_user_ids"] = sorted(recipients)
    return result
