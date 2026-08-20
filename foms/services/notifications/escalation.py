"""P0(긴급) 알림 미확인 에스컬레이션 서비스 (Phase 3C).

긴급 알림이 일정 시간(기본 5분) 내 확인(ack)되지 않으면 단계적으로 상급자에게
에스컬레이션한다:

- Stage 1(미ack 5분 경과): 수신자 팀 MANAGER 들에게 에스컬레이션 알림 + ``escalated`` 이벤트.
- Stage 2(escalate 후 다시 5분 경과, 여전히 미ack): ADMIN 들에게 알림 + ``operator_escalated`` 이벤트.

무한 루프 방지: 에스컬레이션으로 생성하는 알림은 ``is_urgent=False`` 라 다시 대상이 되지
않는다. idempotent: state 의 ``escalated_at`` 와 ``operator_escalated`` 이벤트 존재 여부로
같은 state 를 재실행해도 중복 알림/이벤트를 만들지 않는다.

중복 억제(원본 단위): 같은 원본 알림이 여러 수신자에게 팬아웃돼 state 가 N 개여도 상급자
1인이 받는 에스컬레이션 알림은 원본당 1건이다. 이미 통보한 대상 id 는 이벤트
``metadata_json['escalation_target_user_ids']`` 에 남기고, 이후 스윕/단계에서 제외한다.

본문: in-app 알림 message 에는 원본 제목·담당자·경과·원본 본문 요약을 담는다(수신자가
무슨 일인지 알 수 있어야 한다). push/realtime payload 는 Spec D2 대로 generic 유지 —
``_build_payload`` 는 ``notification.message`` 를 읽지 않는다.

배달(badge/realtime/push)은 ``finalize_escalation_delivery`` — 호출자가 **commit 이후**
실행한다(멘션/도면 finalize 패턴과 동일).
"""

from __future__ import annotations

import datetime as _dt

from foms.services.datetime_kst import now_utc_naive
import logging
import os
from typing import Any, Dict, Iterable, List, Optional, Set

from sqlalchemy import func

from models import (
    Notification,
    NotificationEvent,
    NotificationEventType,
    NotificationUserState,
    User,
)
from foms.services.notifications.recipients import fan_out_new_notification

logger = logging.getLogger(__name__)

_ESCALATION_TITLE = "[에스컬레이션] 확인되지 않은 긴급 알림이 있습니다."
_SOURCE_MESSAGE_LIMIT = 160
_TARGETS_META_KEY = "escalation_target_user_ids"


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
    target_user_ids: Optional[Iterable[int]] = None,
) -> None:
    """append-only 에스컬레이션 이벤트 1건 기록.

    :param target_user_ids: 이번에 에스컬레이션 알림을 보낸 상급자 id 목록. 다음 스윕이
        같은 원본으로 같은 사람에게 또 보내지 않도록 metadata 에 남긴다.
    """
    metadata = None
    if target_user_ids is not None:
        metadata = {_TARGETS_META_KEY: [int(x) for x in target_user_ids]}
    db.add(
        NotificationEvent(
            notification_id=notification_id,
            user_state_id=user_state_id,
            recipient_user_id=recipient_user_id,
            event_type=event_type,
            metadata_json=metadata,
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


def _shorten(text: Optional[str], limit: int = _SOURCE_MESSAGE_LIMIT) -> str:
    """원본 본문을 한 줄 요약으로 자른다(줄바꿈 제거, 초과분은 말줄임)."""
    raw = " ".join(str(text or "").split())
    if not raw:
        return ""
    return raw if len(raw) <= limit else raw[: limit - 1].rstrip() + "…"


def _owner_label(db: Any, user_id: Optional[int]) -> str:
    """미확인 담당자 표기(이름 + 팀). 조회 실패 시 '담당자 미상'."""
    user = db.get(User, int(user_id)) if user_id is not None else None
    if user is None:
        return "담당자 미상"
    name = (getattr(user, "name", None) or getattr(user, "username", None) or "").strip()
    team = (getattr(user, "team", None) or "").strip()
    if not name:
        return "담당자 미상"
    return f"{name}({team})" if team else name


def _build_escalation_message(
    db: Any, source: Notification, overdue_user_id: Optional[int], minutes: int, stage: int
) -> str:
    """에스컬레이션 알림 본문(원본 제목·담당자·경과·원본 요약).

    :param stage: 1=담당자 미확인, 2=매니저까지 미확인(운영 에스컬레이션)
    :return: in-app 알림 목록에 그대로 표시되는 한 줄 본문
    """
    owner = _owner_label(db, overdue_user_id)
    if stage >= 2:
        head = f"{owner} 미확인 · 매니저 단계에서도 {minutes}분 더 지났습니다."
    else:
        head = f"{owner}가 {minutes}분 동안 확인하지 않았습니다."
    parts = [head, f"원본: {source.title}"]
    body = _shorten(getattr(source, "message", None))
    if body:
        parts.append(body)
    if source.order_id:
        parts.append(f"주문 #{int(source.order_id)}")
    return " · ".join(parts)


def _create_escalation_notification(
    db: Any,
    recipient_user_id: int,
    source: Notification,
    now: _dt.datetime,
    message: Optional[str] = None,
) -> Notification:
    """상급자 1인에게 에스컬레이션 알림 생성(비긴급 — 재-escalation 방지).

    본문에는 무슨 알림이 방치됐는지 담는다. push/realtime 은 generic payload 유지라
    잠금화면에는 노출되지 않는다.

    :return: flush 된 Notification (id 확보). 배달은 호출부 commit 후 finalize.
    """
    notif = Notification(
        order_id=source.order_id,
        notification_type="URGENT_ESCALATION",
        target_type="USER",
        target_user_id=int(recipient_user_id),
        is_urgent=False,
        title=_ESCALATION_TITLE,
        message=message,
        is_read=False,
        created_at=now,
    )
    db.add(notif)
    db.flush()
    fan_out_new_notification(db, notif, actor_user_id=None)
    return notif


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


def _already_notified_user_ids(db: Any, source_notification_id: int) -> Set[int]:
    """이 원본 알림 때문에 이미 에스컬레이션 알림을 받은 사용자 id(과거 스윕 포함)."""
    rows = (
        db.query(NotificationEvent.metadata_json)
        .filter(
            NotificationEvent.notification_id == int(source_notification_id),
            NotificationEvent.event_type.in_(
                [
                    NotificationEventType.ESCALATED,
                    NotificationEventType.OPERATOR_ESCALATED,
                ]
            ),
        )
        .all()
    )
    seen: Set[int] = set()
    for (metadata,) in rows:
        if not isinstance(metadata, dict):
            continue
        for uid in metadata.get(_TARGETS_META_KEY) or []:
            try:
                seen.add(int(uid))
            except (TypeError, ValueError):
                continue
    return seen


def escalate_overdue_urgent(
    db: Any, now: Optional[_dt.datetime] = None
) -> Dict[str, Any]:
    """미확인 긴급 알림을 단계적으로 에스컬레이션(idempotent).

    호출자 트랜잭션에 참여하며 별도 commit 하지 않는다(flush 만). CLI/worker 래퍼가
    commit 한 뒤 ``finalize_escalation_delivery`` 로 배달한다.

    :param db: SQLAlchemy 세션
    :param now: 기준 시각(테스트 주입용, 기본 현재 시각)
    :return: {escalated, operator_escalated, checked, created_notification_ids,
              recipient_user_ids}
    """
    now = now or now_utc_naive()
    minutes = _stage_minutes()
    stage1_cutoff = now - _dt.timedelta(minutes=minutes)
    stage2_cutoff = now - _dt.timedelta(minutes=minutes)

    escalated = 0
    operator = 0
    checked = 0
    created_notification_ids: List[int] = []
    recipient_user_ids: List[int] = []
    # 원본 알림 id -> 이미 통보한 상급자 id (과거 스윕 + 이번 스윕 누적).
    notified_by_source: Dict[int, Set[int]] = {}

    def _fresh_targets(source_id: int, candidates: Iterable[int]) -> List[int]:
        """이 원본으로 아직 통보받지 않은 대상만 남기고, 통보 예정으로 표시한다."""
        seen = notified_by_source.get(int(source_id))
        if seen is None:
            seen = _already_notified_user_ids(db, source_id)
            notified_by_source[int(source_id)] = seen
        fresh: List[int] = []
        for uid in candidates:
            uid = int(uid)
            if uid in seen:
                continue
            seen.add(uid)
            fresh.append(uid)
        return fresh

    def _notify(source: Notification, uids: List[int], stage: int, overdue_user_id: int) -> None:
        """대상 목록에 에스컬레이션 알림을 1인 1건씩 생성한다."""
        if not uids:
            return
        message = _build_escalation_message(db, source, overdue_user_id, minutes, stage)
        for uid in uids:
            created = _create_escalation_notification(db, uid, source, now, message)
            created_notification_ids.append(int(created.id))
            recipient_user_ids.append(int(uid))

    for state, notif in _urgent_pending_query(db).all():
        checked += 1
        # Stage 1: 아직 escalate 안 됐고 생성 후 5분 경과 -> 팀 매니저 에스컬레이션.
        if state.escalated_at is None:
            if state.created_at is not None and state.created_at < stage1_cutoff:
                state.escalated_at = now
                targets = _fresh_targets(
                    notif.id, _escalation_targets(db, state.user_id, "MANAGER")
                )
                _notify(notif, targets, 1, state.user_id)
                _record_event(
                    db,
                    notif.id,
                    state.id,
                    state.user_id,
                    NotificationEventType.ESCALATED,
                    target_user_ids=targets,
                )
                escalated += 1
            continue
        # Stage 2: escalate 후 다시 5분 경과, 여전히 미ack -> ADMIN 운영 에스컬레이션.
        if state.escalated_at < stage2_cutoff and not _has_event(
            db, state.id, NotificationEventType.OPERATOR_ESCALATED
        ):
            targets = _fresh_targets(notif.id, _role_user_ids(db, "ADMIN", None))
            _notify(notif, targets, 2, state.user_id)
            _record_event(
                db,
                notif.id,
                state.id,
                state.user_id,
                NotificationEventType.OPERATOR_ESCALATED,
                target_user_ids=targets,
            )
            operator += 1

    db.flush()
    # recipient 중복 제거(동일 매니저가 여러 원본에서  Escalation 받을 수는 있음 —
    # badge invalidate 용 set 만 정리; push 는 notif id 별로 유지).
    unique_recipients = sorted(set(recipient_user_ids))
    return {
        "escalated": escalated,
        "operator_escalated": operator,
        "checked": checked,
        "created_notification_ids": created_notification_ids,
        "recipient_user_ids": unique_recipients,
    }


def finalize_escalation_delivery(
    db: Any,
    created_notification_ids: Optional[List[int]] = None,
    recipient_user_ids: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """에스컬레이션 알림 commit 이후 badge + realtime + push 배달.

    ``escalate_overdue_urgent`` 가 만든 id 목록을 받아 멘션/도면 finalize 와 동일 계약을
    적용한다. 이 함수는 commit 하지 않는다(enqueue 는 이미 커밋된 row 를 worker 가 재조회).

    :param db: SQLAlchemy 세션(badge/enqueue 헬퍼용)
    :param created_notification_ids: 이번 스윕에서 생성한 escalation 알림 id
    :param recipient_user_ids: 배지 invalidate + socket emit 대상
    :return: {pushed, realtime_sent, recipients}
    """
    ids = [int(x) for x in (created_notification_ids or []) if x is not None]
    recipients = [int(x) for x in (recipient_user_ids or []) if x is not None]
    if not ids and not recipients:
        return {"pushed": 0, "realtime_sent": 0, "recipients": 0}

    from foms.api.notifications import invalidate_badge_cache_for_user_ids
    from foms.services.notifications.push_sender import enqueue_push_for_notification
    from foms.services.notifications.realtime_notifications import (
        emit_erp_notification_to_users,
    )

    if recipients:
        invalidate_badge_cache_for_user_ids(recipients)

    realtime_sent = 0
    if recipients:
        # DB is_urgent=False 유지(루프 방지). 클라 강조용으로 payload urgent=true (Spec D2).
        realtime_sent = emit_erp_notification_to_users(
            recipients,
            {
                "title": _ESCALATION_TITLE,
                "message": "",
                "urgent": True,
                "notification_type": "URGENT_ESCALATION",
                "kind": "erp_notification",
            },
        )

    pushed = 0
    for nid in ids:
        try:
            result = enqueue_push_for_notification(nid, db=db)
            if result.get("enqueued"):
                pushed += 1
        except Exception:
            logger.exception(
                "[escalation] push enqueue failed notification_id=%s", nid
            )

    return {
        "pushed": pushed,
        "realtime_sent": int(realtime_sent),
        "recipients": len(recipients),
    }


__all__ = ["escalate_overdue_urgent", "finalize_escalation_delivery"]
