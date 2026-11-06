"""프리랜서 영업 차감 알림 ``SALES_COMMISSION_DEDUCTION``(설계서 FCOMM-01 §7 · D17).

영업 귀속 차감(부서 SALES · 귀속 사람 = 켜진 프리랜서)이 생기거나 취소되면 그 프리랜서 한 명에게 알림 한
줄을 만들고(사람 id 지정), 커밋 뒤 웹 푸시를 예약한다. 선례 :mod:`foms.services.partners.notify` 와 같은
틀이다 — 원래 일(차감 저장)이 커밋된 **뒤에** 부르고, 알림이 실패해도 끝난 일을 되돌리지 않는다.

폰 배너 글은 :mod:`foms.services.notifications.push_sender` 가 이 줄의 글을 읽지 않고 따로 만든다
(잠금 화면에 사유를 싣지 않는다). 누르면 내 수수료 화면(:data:`MY_COMMISSION_URL`)으로 간다.
"""
from __future__ import annotations

from typing import Any, Optional

from foms.services.error_logging import log_handled_exception
from foms.services.notifications.push_sender import enqueue_push_for_notification
from foms.services.notifications.recipients import fan_out_new_notification
from foms.services.sales_commission.settings import is_freelancer
from models import Notification, Order, User

NOTIFICATION_TYPE = "SALES_COMMISSION_DEDUCTION"
#: 프리랜서 내 수수료 화면(T7). 폰 알림 · 알림 목록이 같은 곳을 연다.
MY_COMMISSION_URL = "/erp/my-commission"
_SALES = "SALES"


def _customer_name(order: Order) -> str:
    sd = order.structured_data if isinstance(order.structured_data, dict) else {}
    name = ((sd.get("parties") or {}).get("customer") or {}).get("name") or order.customer_name or ""
    return " ".join(str(name).split()) or f"#{order.id}"


def _amount(deduction: dict) -> int:
    try:
        return abs(int(deduction.get("amount") or 0))
    except (TypeError, ValueError):
        return 0


def deduction_message(customer: str, amount: int, reason: str, *, voided: bool) -> str:
    """알림 목록에 보일 문장(해요체)."""
    if voided:
        return f"{customer} 주문 차감 {amount:,}원이 취소됐어요"
    return f"{customer} 주문에 차감 {amount:,}원이 생겼어요 — {reason}"


def freelancer_target(db, deduction: Any) -> Optional[int]:
    """알림 받을 프리랜서 id — 영업 귀속이고 귀속 사람이 켜진 프리랜서인 활성 계정일 때만. 아니면 None."""
    if not isinstance(deduction, dict):
        return None
    if str(deduction.get("department") or "").strip().upper() != _SALES:
        return None
    try:
        uid = int(deduction.get("charge_to_user_id"))
    except (TypeError, ValueError):
        return None
    user = db.query(User).filter(User.id == uid, User.is_active.is_(True)).first()
    if user is None or not is_freelancer(db, user):
        return None
    return uid


def create_deduction_notification(db, order_id: int, deduction: Any, *, voided: bool,
                                  actor_user_id: Optional[int] = None) -> Optional[Notification]:
    """프리랜서 대상이면 알림 한 줄 + 받는 사람 state(커밋은 부르는 쪽). 대상이 아니면 None."""
    target = freelancer_target(db, deduction)
    if target is None:
        return None
    order = db.get(Order, order_id)
    if order is None:
        return None
    message = deduction_message(_customer_name(order), _amount(deduction),
                                str(deduction.get("reason") or ""), voided=voided)
    notification = Notification(
        order_id=order_id, notification_type=NOTIFICATION_TYPE, target_type="USER", target_user_id=target,
        title="수수료 차감 취소" if voided else "수수료 차감", message=message,
        created_by_user_id=actor_user_id, created_by_name="FOMS",
    )
    db.add(notification)
    db.flush()
    fan_out_new_notification(db, notification, actor_user_id=actor_user_id)
    return notification


def notify_freelancer_deduction(db, order_id: int, deduction: Any, *, voided: bool,
                                actor_user_id: Optional[int] = None) -> int:
    """차감 저장이 커밋된 뒤 부른다. 알림을 만들어 커밋하고 웹 푸시를 예약한다.

    Returns:
        만든 알림 수(0 또는 1). 실패해도 예외를 올리지 않는다 — 차감은 이미 저장됐다.
    """
    try:
        notification = create_deduction_notification(db, order_id, deduction, voided=voided,
                                                     actor_user_id=actor_user_id)
        if notification is None:
            return 0
        db.commit()
    except Exception:  # noqa: BLE001 — 알림 실패가 끝난 차감 저장을 되돌리면 안 된다
        db.rollback()
        log_handled_exception(f"sales commission deduction notify order={order_id}")
        return 0
    try:
        enqueue_push_for_notification(notification.id, db=db)
    except Exception:  # noqa: BLE001 — 푸시 예약 실패는 알림 줄을 지우지 않는다
        log_handled_exception(f"sales commission deduction push order={order_id}")
    return 1


__all__ = [
    "MY_COMMISSION_URL",
    "NOTIFICATION_TYPE",
    "create_deduction_notification",
    "deduction_message",
    "freelancer_target",
    "notify_freelancer_deduction",
]
