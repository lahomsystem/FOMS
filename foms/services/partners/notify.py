"""PARTNER-FOMS 6: 협력사 직원 웹 푸시 알림.

협력사 주문에 협력사가 알아야 할 일이 생기면 그 협력사의 사용 중인 직원 모두에게 알림 한 줄씩 만들고
(사람 id 지정 — 넓은 경로는 우리 직원만 받는다, ``recipients.INTERNAL_USERS_ONLY``), 커밋 뒤 웹 푸시를
예약한다. 협력사 직원이 "알림 받기"를 누른 기기로만 간다. 사용자 결정: 웹 푸시 · 네 가지 일 · 회사 직원
모두 · 밤에도 바로. 설계서 docs/specs/2026-10-20-partner-notifications_SPEC.md §0 · §5-1
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import func

from foms.services.datetime_kst import now_utc_naive
from foms.services.error_logging import log_handled_exception
from foms.services.notifications.partner_push import (
    PARTNER_AS_VISIT,
    PARTNER_CONSTRUCTION_DATE,
    PARTNER_CONSTRUCTION_DONE,
    PARTNER_DRAWING_READY,
    PARTNER_PUSH_TITLES,
    mask_customer_name,
)
from foms.services.notifications.push_sender import enqueue_push_for_notification
from foms.services.notifications.recipients import fan_out_new_notification
from models import Notification, NotificationPushSubscription, Order, User

# 같은 주문 · 같은 일 · 같은 문장이 이 시간 안에 이미 나갔으면 다시 만들지 않는다(두 번 누름 · 훅 중복).
DEDUPE_WINDOW = dt.timedelta(minutes=10)


def _customer(order: Order) -> str:
    sd = order.structured_data if isinstance(order.structured_data, dict) else {}
    name = ((sd.get("parties") or {}).get("customer") or {}).get("name") or order.customer_name or ""
    return mask_customer_name(str(name))


def partner_message(event: str, order: Order, values: dict[str, Any] | None = None) -> str:
    """잠금 화면에 보일 문장 — 주소 · 메모 없이, 고객 이름은 가려서."""
    v = values or {}
    head = f"{_customer(order)} 고객(#{order.id})"
    if event == PARTNER_DRAWING_READY:
        return f"{head} 도면이 올라왔습니다. 고객과 확인한 뒤 승인 또는 수정 요청해 주세요."
    if event == PARTNER_CONSTRUCTION_DATE:
        changed = f" (바뀜: {v['before']} → {v['after']})" if v.get("before") else ""
        return f"{head} 시공일이 {v.get('after') or '-'}로 정해졌습니다{changed}. 고객에게 알려 주세요."
    if event == PARTNER_AS_VISIT:
        when = " ".join(x for x in (v.get("date"), v.get("time")) if x)
        return f"{head} AS 방문이 {when or '-'}로 잡혔습니다. 고객에게 알려 주세요."
    if event == PARTNER_CONSTRUCTION_DONE:
        return f"{head} 시공이 끝났습니다. 완공 사진을 확인할 수 있습니다."
    return head


def partner_staff_ids(db, org_id: int) -> list[int]:
    rows = db.query(User.id).filter(User.partner_org_id == org_id, User.is_active.is_(True)).order_by(User.id).all()
    return [r.id for r in rows]


def create_partner_notifications(db, order: Order | None, event: str,
                                 values: dict[str, Any] | None = None) -> list[Notification]:
    """협력사 주문이면 그 회사 사용 중인 직원마다 알림 한 줄(커밋은 호출자). 아니면 빈 목록."""
    if order is None or not order.partner_org_id or event not in PARTNER_PUSH_TITLES:
        return []
    message = partner_message(event, order, values)
    since = now_utc_naive() - DEDUPE_WINDOW
    already = {
        r.target_user_id for r in db.query(Notification.target_user_id).filter(
            Notification.order_id == order.id, Notification.notification_type == event,
            Notification.message == message, Notification.created_at >= since,
        )
    }
    rows = []
    for user_id in partner_staff_ids(db, order.partner_org_id):
        if user_id in already:
            continue
        notification = Notification(
            order_id=order.id, notification_type=event, target_type="USER", target_user_id=user_id,
            title=f"협력사 주문 · {PARTNER_PUSH_TITLES[event]}", message=message, created_by_name="FOMS",
        )
        db.add(notification)
        db.flush()
        fan_out_new_notification(db, notification, actor_user_id=None)
        rows.append(notification)
    return rows


def notify_partner_staff(db, order: Order | None, event: str, values: dict[str, Any] | None = None) -> int:
    """원래 일이 커밋된 뒤 부른다. 알림을 만들어 커밋하고 웹 푸시를 예약한다.

    알림이 실패해도 원래 일(도면 받음 확인 · 시공일 저장 등)은 이미 끝났다 — 예외를 올리지 않고 기록만 한다.

    Returns:
        만든 알림 수.
    """
    try:
        rows = create_partner_notifications(db, order, event, values)
        if not rows:
            return 0
        db.commit()
    except Exception:  # noqa: BLE001 — 알림 실패가 끝난 일을 되돌리면 안 된다
        db.rollback()
        log_handled_exception(f"partner notify {event}")
        return 0
    for notification in rows:
        try:
            enqueue_push_for_notification(notification.id, db=db)
        except Exception:  # noqa: BLE001 — 푸시 예약 실패는 알림 줄을 지우지 않는다
            log_handled_exception(f"partner push enqueue {event}")
    return len(rows)


def _after_commit(db, order: Order | None, event: str, ready) -> int:
    """원래 일이 커밋된 뒤 부르는 공통 입구 — 협력사 주문이고 ``ready(order)`` 가 값을 주면 알린다.

    커밋 뒤 주문을 다시 읽다 실패해도 끝난 일(도면 받음 확인 · 방문일 저장 · 시공 완료)을 500 으로 바꾸지 않는다.
    """
    try:
        if order is None or not order.partner_org_id:
            return 0
        values = ready(order)
        if values is None:
            return 0
    except Exception:  # noqa: BLE001 — 알림 판정 실패가 끝난 일을 되돌리면 안 된다
        log_handled_exception(f"partner notify {event}")
        return 0
    return notify_partner_staff(db, order, event, values)


def notify_partner_drawing_ready(db, order: Order | None) -> int:
    """우리 CS 가 "도면 받음 확인"을 커밋한 뒤 — 고객컨펌 단계일 때만(협력사 차례). 수정 뒤 다시 확정도 같다."""
    return _after_commit(db, order, PARTNER_DRAWING_READY,
                         lambda o: {} if (o.erp_stage_code or "").upper() == "CONFIRM" else None)


def _as_visit_values(order: Order) -> dict[str, str] | None:
    sd = order.structured_data if isinstance(order.structured_data, dict) else {}
    visit = (sd.get("schedule") or {}).get("as_visit") or {}
    date = str(visit.get("date") or "").strip()
    return {"date": date, "time": str(visit.get("time") or "").strip()} if date else None


def notify_partner_as_visit(db, order: Order | None) -> int:
    """AS 화면이 방문일(``schedule.as_visit.date``)을 저장해 커밋한 뒤."""
    return _after_commit(db, order, PARTNER_AS_VISIT, _as_visit_values)


def notify_partner_construction_done(db, order: Order | None) -> int:
    """시공 완료(→CS)를 커밋한 뒤 — 완공 사진을 볼 수 있다."""
    return _after_commit(db, order, PARTNER_CONSTRUCTION_DONE, lambda o: {})


def partner_push_device_counts(db) -> dict[int, int]:
    """협력사 직원별 알림 받는 기기 수(구독 해제 안 된 웹 푸시) — 관리자 협력사 화면용. 0대면 CS 가 전화."""
    rows = (
        db.query(NotificationPushSubscription.user_id, func.count(NotificationPushSubscription.id))
        .join(User, User.id == NotificationPushSubscription.user_id)
        .filter(User.partner_org_id.isnot(None), NotificationPushSubscription.revoked_at.is_(None))
        .group_by(NotificationPushSubscription.user_id)
        .all()
    )
    return {user_id: count for user_id, count in rows}
