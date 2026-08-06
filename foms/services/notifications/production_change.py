"""ERP 생산 파이프라인 주문 변경 → 생산 담당 팀 벨 알림.

생산(제작대기/제작중/제작완료) 단계 주문의 시공일 변경·도면 재전달/수정요청·취소를
생산 담당 팀 벨에 알린다. 패턴은 ``drawing_order_change`` 미러 — 단순화: debounce 는
order+type+팀 기준(actor 무관)이다. 생산 알림은 팀 공지 성격이라 누가 바꿨든 같은 주문의
같은 종류 변경은 60초 내 한 줄로 합친다.

수신 팀 = :data:`TARGET_TEAMS`\\ ``= ("CS", "SALES")``. 원래는 ``"PRODUCTION"`` 하나였는데
**그 팀 소속 활성 사용자가 0명**이라(운영 DB 실측 2026-08-05: CONSTRUCTION 10 · SALES 8 ·
CS 6 · DRAWING 3 · ADMIN 2, ``PRODUCTION``·``SHIPMENT`` 행 자체가 없음) ``fan_out`` 이
0건이었다 — ``notification_user_states`` 0행 = 아무에게도 안 가는 무음 알림. ADMIN 은
팬아웃 대상이 아니라(관리자에게 모든 알림 state 를 만들지 않는 것이 의도 —
``recipients`` 모듈 docstring) 관리자도 못 봤다. 실제 생산 작업 주체는 권한 정책
``PRODUCTION_EDIT`` 의 팀 집합 ``("CS", "SALES", "PRODUCTION")`` 이 정본이므로 실사용자가
있는 두 팀을 수신자로 삼는다.

``Notification.target_team`` 은 단일 문자열 컬럼이라 **팀당 row 1개**를 만든다(row 가
자기 수신 범위를 정직하게 describe 하도록 — 공용 resolver 의 팀 매칭 의미를 바꾸지 않는다).
한 사용자는 팀 하나에만 속하므로 벨에는 여전히 1건만 보인다.

호출 계약(drawing 과 동일):
    커밋 **전** ``apply_production_change_alert`` (Notification 생성/갱신 + fan_out),
    커밋 **후** ``finalize_production_change_alert`` (push enqueue + 배지 무효화 +
    realtime emit). 알림 실패가 본 트랜잭션을 죽이면 안 되므로 호출부는 try/except 로 감싼다.
    **첫 반환값은 Notification 리스트다**(팀 수만큼) — 호출부는 그대로 finalize 에 넘기는
    opaque handle 로만 쓰므로 호출 코드 변경은 없다.
"""
from __future__ import annotations

import datetime as _dt

from foms.services.datetime_kst import now_utc_naive
import logging
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from models import Notification, Order
from foms.services.production_change_alerts import PROD_STAGES

logger = logging.getLogger(__name__)

NOTIFICATION_TYPE = "PRODUCTION_ORDER_CHANGED"
#: 수신 팀(팀당 Notification row 1개). 위 모듈 docstring 의 근거 참조.
TARGET_TEAMS: Tuple[str, ...] = ("CS", "SALES")
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
    db: Session, order_id: int, team: str, *, now: _dt.datetime
) -> Optional[Notification]:
    """동일 order+type+**팀** 60초 내 최근 생산 알림(actor 무관).

    팀을 조건에 넣지 않으면 팀별 row 중 id 가 큰 하나만 잡혀 다른 팀 row 가 매번 새로
    생성된다(한 팀은 merge, 다른 팀은 중복). debounce 는 row 단위 개념이므로 row 를
    가르는 축(팀)을 그대로 따라간다.
    """
    prev = (
        db.query(Notification)
        .filter(
            Notification.order_id == order_id,
            Notification.notification_type == NOTIFICATION_TYPE,
            Notification.target_team == team,
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
) -> Tuple[List[Notification], bool]:
    """생산 파이프라인 게이트 통과 시 생산 담당 팀 알림을 생성/갱신한다(커밋 전 호출).

    :data:`TARGET_TEAMS` 의 팀마다 row 1개를 만들고 각 row 를 ``fan_out`` 한다.

    Args:
        db: 활성 세션.
        order: 대상 주문(``is_erp_order``·``erp_stage_code`` 로드 상태).
        kind: 'construction_date' | 'drawing' | 'cancelled'.
        message_detail: 메시지 상세(예 '7/6 → 7/4'). 없으면 빈 문자열.
        actor_user_id: 변경자 id(선택).
        actor_name: 변경자 표시명.

    Returns:
        ``(notifications, created_any)``. 비생산 단계·비ERP면 ``([], False)``. 리스트는
        merge 된 기존 row 와 새로 만든 row 를 모두 담는다(finalize 가 배지·realtime 을
        전부에게 돌려야 하므로). ``created_any`` 는 **하나라도** 신규면 True — push 는
        신규일 때만 나가야 하는데, 팀별로 debounce 상태가 갈릴 수 있어서 보수적으로
        "새 row 가 생겼으면 push" 로 잡는다(중복 push 보다 무음이 더 나쁘다).
    """
    if not getattr(order, "is_erp_order", False):
        return [], False
    if (getattr(order, "erp_stage_code", None) or "") not in PROD_STAGES:
        return [], False

    label = _KIND_LABEL.get(kind, "주문 변경")
    title = f"[생산] {label} — {_customer_name(order)}"
    detail = (message_detail or "").strip()
    message = f"주문 #{order.id} — {label}" + (f" ({detail})" if detail else "")

    from foms.services.notifications.recipients import fan_out_new_notification

    now = now_utc_naive()
    notifications: List[Notification] = []
    created_any = False
    for team in TARGET_TEAMS:
        prev = _find_recent_notification(db, int(order.id), team, now=now)
        if prev is not None:
            prev.title = title
            prev.message = message
            notifications.append(prev)
            continue

        notif = Notification(
            order_id=int(order.id),
            notification_type=NOTIFICATION_TYPE,
            target_type="TEAM",
            target_team=team,
            title=title,
            message=message,
            created_by_user_id=actor_user_id,
            created_by_name=actor_name or None,
        )
        db.add(notif)
        db.flush()
        fan_out_new_notification(db, notif, actor_user_id=actor_user_id)
        notifications.append(notif)
        created_any = True
    return notifications, created_any


def finalize_production_change_alert(
    db: Session,
    notifications: Optional[List[Notification]],
    *,
    created_new: bool,
) -> None:
    """커밋 이후: created_new 면 push enqueue, 항상 배지 무효화 + realtime emit.

    debounce merge(created_new=False)는 OS push 만 생략하고 배지/realtime 은 유지한다.

    Args:
        db: 활성 세션.
        notifications: :func:`apply_production_change_alert` 첫 반환값(팀별 row 리스트).
            빈 리스트·``None`` 이면 no-op — 예전 단일 Notification 을 넘겨도 죽지 않게
            받아 준다(구 호출 계약 잔존 방어).
        created_new: 하나라도 신규 row 였는지.
    """
    if not notifications:
        return
    if isinstance(notifications, Notification):  # 구 계약 방어(단일 객체)
        notifications = [notifications]
    from foms.api.notifications import (
        invalidate_badge_cache_for_user_ids,
        resolve_notification_recipient_user_ids,
    )
    from foms.services.notifications.realtime_notifications import emit_erp_notification_to_users

    if created_new:
        from foms.services.notifications.push_sender import enqueue_push_for_notification

        for notif in notifications:
            enqueue_push_for_notification(notif.id, db=db)

    for notif in notifications:
        recipient_user_ids = resolve_notification_recipient_user_ids(
            db,
            target_team=(notif.target_team or "").strip().upper() or None,
            target_manager_name=None,
            include_admin=True,
        )
        invalidate_badge_cache_for_user_ids(recipient_user_ids)
        emit_erp_notification_to_users(
            recipient_user_ids,
            {
                "notification_id": notif.id,
                "order_id": notif.order_id,
                "notification_type": NOTIFICATION_TYPE,
                "title": notif.title,
                "message": notif.message,
            },
        )
