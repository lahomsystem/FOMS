"""P0(긴급) 알림 미확인 에스컬레이션 서비스 (Phase 3C).

긴급 알림이 일정 시간(기본 5분) 내 확인(ack)되지 않으면 단계적으로 상급자에게
에스컬레이션한다:

- Stage 1(미ack 5분 경과): 수신자 팀 MANAGER 들에게 에스컬레이션 알림 + ``escalated`` 이벤트.
- Stage 2(escalate 후 다시 5분 경과, 여전히 미ack): ADMIN 들에게 알림 + ``operator_escalated`` 이벤트.

무한 루프 방지: 에스컬레이션으로 생성하는 알림은 ``is_urgent=False`` 라 다시 대상이 되지
않는다. idempotent: state 의 ``escalated_at`` 와 ``operator_escalated`` 이벤트 존재 여부로
같은 state 를 재실행해도 중복 알림/이벤트를 만들지 않는다.
"""

from __future__ import annotations

import datetime as _dt
import os
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func

from models import (
    Notification,
    NotificationEvent,
    NotificationEventType,
    NotificationUserState,
    User,
)
from foms.services.notifications.recipients import fan_out_new_notification

_ESCALATION_TITLE = "[에스컬레이션] 확인되지 않은 긴급 알림이 있습니다."


def _stage_minutes() -> int:
    """단계별 대기 분(기본 5분). env ``FOMS_ESCALATION_MINUTES`` 로 override."""
    raw = (os.environ.get("FOMS_ESCALATION_MINUTES", "") or "").strip()
    try:
        value = int(raw) if raw else 5
    except (TypeError, ValueError):
        value = 5
    return value if value >= 1 else 5


def _urgent_pending_query(db: Any):
    """긴급 & 미ack & 미resolved 인 (state, notification) 조인 쿼리."""
    return (
        db.query(NotificationUserState, Notification)
        .join(Notification, Notification.id == NotificationUserState.notification_id)
        .filter(
            Notification.is_urgent == True,  # noqa: E712
            NotificationUserState.ack_at.is_(None),
            NotificationUserState.resolved_at.is_(None),
        )
    )


def _role_user_ids(db: Any, role: str, team: Optional[str]) -> List[int]:
    """지정 role 의 활성 사용자 id 목록(team 이 있으면 팀 일치로 좁힘)."""
    q = db.query(User.id).filter(User.role == role, User.is_active == True)  # noqa: E712
    if team:
        q = q.filter(func.upper(User.team) == team.strip().upper())
    return [int(r[0]) for r in q]


def _record_event(
    db: Any,
    notification_id: int,
    user_state_id: int,
    recipient_user_id: int,
    event_type: str,
) -> None:
    """append-only 에스컬레이션 이벤트 1건 기록."""
    db.add(
        NotificationEvent(
            notification_id=notification_id,
            user_state_id=user_state_id,
            recipient_user_id=recipient_user_id,
            event_type=event_type,
        )
    )


def _has_event(db: Any, user_state_id: int, event_type: str) -> bool:
    """해당 state 에 특정 이벤트가 이미 있는지(idempotent 판정)."""
    return (
        db.query(NotificationEvent.id)
        .filter(
            NotificationEvent.user_state_id == user_state_id,
            NotificationEvent.event_type == event_type,
        )
        .first()
        is not None
    )


def _create_escalation_notification(
    db: Any, recipient_user_id: int, source: Notification, now: _dt.datetime
) -> None:
    """상급자 1인에게 generic 에스컬레이션 알림 생성(민감정보 없음, 비긴급)."""
    notif = Notification(
        order_id=source.order_id,
        notification_type="URGENT_ESCALATION",
        target_type="USER",
        target_user_id=int(recipient_user_id),
        is_urgent=False,
        title=_ESCALATION_TITLE,
        message=None,
        is_read=False,
        created_at=now,
    )
    db.add(notif)
    db.flush()
    fan_out_new_notification(db, notif, actor_user_id=None)


def _escalation_targets(
    db: Any, overdue_user_id: int, primary_role: str
) -> List[int]:
    """에스컬레이션 대상 id. primary_role(팀 매니저) 우선, 없으면 ADMIN 폴백."""
    user = db.get(User, int(overdue_user_id))
    team = getattr(user, "team", None) if user else None
    targets = _role_user_ids(db, primary_role, team)
    if not targets and primary_role != "ADMIN":
        targets = _role_user_ids(db, "ADMIN", None)
    return targets


def escalate_overdue_urgent(
    db: Any, now: Optional[_dt.datetime] = None
) -> Dict[str, int]:
    """미확인 긴급 알림을 단계적으로 에스컬레이션(idempotent).

    호출자 트랜잭션에 참여하며 별도 commit 하지 않는다(flush 만). CLI/worker 래퍼가 commit.

    :param db: SQLAlchemy 세션
    :param now: 기준 시각(테스트 주입용, 기본 현재 시각)
    :return: {escalated, operator_escalated, checked} 요약
    """
    now = now or _dt.datetime.now()
    minutes = _stage_minutes()
    stage1_cutoff = now - _dt.timedelta(minutes=minutes)
    stage2_cutoff = now - _dt.timedelta(minutes=minutes)

    escalated = 0
    operator = 0
    checked = 0
    for state, notif in _urgent_pending_query(db).all():
        checked += 1
        # Stage 1: 아직 escalate 안 됐고 생성 후 5분 경과 -> 팀 매니저 에스컬레이션.
        if state.escalated_at is None:
            if state.created_at is not None and state.created_at < stage1_cutoff:
                state.escalated_at = now
                _record_event(db, notif.id, state.id, state.user_id,
                              NotificationEventType.ESCALATED)
                for uid in _escalation_targets(db, state.user_id, "MANAGER"):
                    _create_escalation_notification(db, uid, notif, now)
                escalated += 1
            continue
        # Stage 2: escalate 후 다시 5분 경과, 여전히 미ack -> ADMIN 운영 에스컬레이션.
        if state.escalated_at < stage2_cutoff and not _has_event(
            db, state.id, NotificationEventType.OPERATOR_ESCALATED
        ):
            for uid in _role_user_ids(db, "ADMIN", None):
                _create_escalation_notification(db, uid, notif, now)
            _record_event(db, notif.id, state.id, state.user_id,
                          NotificationEventType.OPERATOR_ESCALATED)
            operator += 1

    db.flush()
    return {"escalated": escalated, "operator_escalated": operator, "checked": checked}


__all__ = ["escalate_overdue_urgent"]
