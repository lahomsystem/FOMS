"""ERP 생산 파이프라인 주문 변경 → 생산팀 벨 알림.

생산(제작대기/제작중/제작완료) 단계 주문의 시공일 변경·도면 재전달/수정요청·취소를
생산팀 벨에 알린다. 패턴은 ``drawing_order_change`` 미러 — 단순화: debounce 는
order+type 기준(actor 무관)이다. 생산 알림은 팀 공지 성격이라 누가 바꿨든 같은 주문의
같은 종류 변경은 60초 내 한 줄로 합친다.

호출 계약(drawing 과 동일):
    커밋 **전** ``apply_production_change_alert`` (Notification 생성/갱신 + fan_out),
    커밋 **후** ``finalize_production_change_alert`` (push enqueue + 배지 무효화 +
    realtime emit). 알림 실패가 본 트랜잭션을 죽이면 안 되므로 호출부는 try/except 로 감싼다.
"""
from __future__ import annotations

import datetime as _dt
import logging
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from models import Notification, Order
from foms.services.production_change_alerts import PROD_STAGES

logger = logging.getLogger(__name__)

NOTIFICATION_TYPE = "PRODUCTION_ORDER_CHANGED"
TARGET_TEAM = "PRODUCTION"
DEBOUNCE_SECONDS = 60

_KIND_LABEL = {
    "construction_date": "시공일 변경",
    "drawing": "도면 변경",
    "cancelled": "주문 취소",
}


def _customer_name(order: Order) -> str:
    """주문 고객명(structured_data.parties.customer.name). 없으면 '-'."""
    sd = order.structured_data if isinstance(order.structured_data, dict) else {}
    name = ((sd.get("parties") or {}).get("customer") or {}).get("name")
    return (name or "").strip() or "-"


def _find_recent_notification(
    db: Session, order_id: int, *, now: _dt.datetime
) -> Optional[Notification]:
    """동일 order+type 60초 내 최근 생산 알림(actor 무관)."""
    prev = (
        db.query(Notification)
        .filter(
            Notification.order_id == order_id,
            Notification.notification_type == NOTIFICATION_TYPE,
        )
        .order_by(Notification.id.desc())
        .first()
    )
    if prev is None or prev.created_at is None:
        return None
    if (now - prev.created_at).total_seconds() > DEBOUNCE_SECONDS:
        return None
    return prev


def apply_production_change_alert(
    db: Session,
    order: Order,
    kind: str,
    message_detail: str,
    *,
    actor_user_id: Optional[int],
    actor_name: str,
) -> Tuple[Optional[Notification], bool]:
    """생산 파이프라인 게이트 통과 시 생산팀 알림을 생성/갱신한다(커밋 전 호출).

    Args:
        db: 활성 세션.
        order: 대상 주문(``is_erp_order``·``erp_stage_code`` 로드 상태).
        kind: 'construction_date' | 'drawing' | 'cancelled'.
        message_detail: 메시지 상세(예 '7/6 → 7/4'). 없으면 빈 문자열.
        actor_user_id: 변경자 id(선택).
        actor_name: 변경자 표시명.

    Returns:
        ``(notification_or_None, created_new)``. 비생산 단계·비ERP면 ``(None, False)``,
        debounce merge 면 ``(prev, False)``, 신규면 ``(notif, True)``.
    """
    if not getattr(order, "is_erp_order", False):
        return None, False
    if (getattr(order, "erp_stage_code", None) or "") not in PROD_STAGES:
        return None, False

    label = _KIND_LABEL.get(kind, "주문 변경")
    title = f"[생산] {label} — {_customer_name(order)}"
    detail = (message_detail or "").strip()
    message = f"주문 #{order.id} — {label}" + (f" ({detail})" if detail else "")

    now = _dt.datetime.now()
    prev = _find_recent_notification(db, int(order.id), now=now)
    if prev is not None:
        prev.title = title
        prev.message = message
        return prev, False

    notif = Notification(
        order_id=int(order.id),
        notification_type=NOTIFICATION_TYPE,
        target_type="TEAM",
        target_team=TARGET_TEAM,
        title=title,
        message=message,
        created_by_user_id=actor_user_id,
        created_by_name=actor_name or None,
    )
    db.add(notif)
    db.flush()
    from foms.services.notifications.recipients import fan_out_new_notification

    fan_out_new_notification(db, notif, actor_user_id=actor_user_id)
    return notif, True


def finalize_production_change_alert(
    db: Session,
    notification: Optional[Notification],
    *,
    created_new: bool,
) -> None:
    """커밋 이후: created_new 면 push enqueue, 항상 배지 무효화 + realtime emit.

    debounce merge(created_new=False)는 OS push 만 생략하고 배지/realtime 은 유지한다.
    """
    if notification is None:
        return
    from foms.api.notifications import (
        invalidate_badge_cache_for_user_ids,
        resolve_notification_recipient_user_ids,
    )
    from foms.services.notifications.realtime_notifications import emit_erp_notification_to_users

    if created_new:
        from foms.services.notifications.push_sender import enqueue_push_for_notification

        enqueue_push_for_notification(notification.id, db=db)

    recipient_user_ids = resolve_notification_recipient_user_ids(
        db,
        target_team=TARGET_TEAM,
        target_manager_name=None,
        include_admin=True,
    )
    invalidate_badge_cache_for_user_ids(recipient_user_ids)
    emit_erp_notification_to_users(
        recipient_user_ids,
        {
            "notification_id": notification.id,
            "order_id": notification.order_id,
            "notification_type": NOTIFICATION_TYPE,
            "title": notification.title,
            "message": notification.message,
        },
    )
