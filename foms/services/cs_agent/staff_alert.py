"""초안 메모가 뜨면 상담 직원 FOMS 앱 웹 푸시(플랜 C10-5 · 설계서 17.3 '직원이 [보내기]' · 원장 R4-18 · 검수 R16).

- **언제**: 관리 화면 '상담 직원 알림'과 '[보내기] · [수정하기] 버튼'이 모두 켜졌고(버튼이 꺼지면 알림이 여는 화면이 거절한다 —
  R16-3), 그 브랜드 운영 시간 · 영업일일 때만(:func:`.metrics.in_business_hours` — 발송 목표는 운영 시간 안만 잰다, 밤 · 주말에
  직원 폰을 깨우지 않는다 — R16-1).
- **받는 사람**: 켜진 우리 직원 가운데 CS 권한 팀(회계팀 포함 — :func:`team_has_capability`)의 STAFF · MANAGER 이고 **푸시 구독이
  살아 있는 사람만**(``notification_push_subscriptions.revoked_at`` 이 빈 줄). 구독이 없는 사람은 알림 줄도 만들지 않는다. 구독 수는
  관리 화면 기록판에 숫자로 보인다(:func:`subscription_counts`).
- **같은 상담은 하나로(R16-2)**: 같은 사람에게 간 같은 상담의 안 읽은 앞 초안 알림은 읽음으로 바꾼다(지난 초안 화면을 가리킨다).
  폰 푸시는 상담마다 같은 꼬리표라 잠금화면에서 하나로 바뀐다(:mod:`foms.services.notifications.push_sender`).
- **길**: 기존 그대로 — 사용자 지정(USER) 알림 한 줄 + 수신자 펼침(:func:`fan_out_new_notification`) → 커밋 → 푸시 일 넣기
  (:func:`~foms.services.notifications.push_sender.enqueue_push_for_notification`). 못 넣은 까닭(꺼짐 · 큐 없음)은 기록한다.
- **글 없음**: 알림 줄 · 푸시에는 손님 글 · 초안을 싣지 않는다 — 보내기 화면 · 데스크 주소만(:mod:`.cs_draft_link` 꼴 한 곳).
"""

from __future__ import annotations

import datetime
import logging
from typing import Any, Callable, Optional

from sqlalchemy import select

from foms.services.cs_agent.channel_read import naive_utc
from foms.services.cs_agent.metrics import in_business_hours
from foms.services.cs_agent.report import desk_link
from foms.services.cs_agent.settings import read_settings
from foms.services.notifications import push_sender
from foms.services.notifications.cs_draft_link import NOTIFY_DRAFT_READY, alert_message, cs_draft_chat, send_path
from foms.services.notifications.recipients import fan_out_new_notification
from foms.services.orders.order_mutation_policy import team_has_capability
from models import Notification, NotificationPushSubscription, NotificationUserState, User

logger = logging.getLogger(__name__)

__all__ = ["NOTIFY_DRAFT_READY", "notify_draft_ready", "recipients", "subscription_counts"]

_ROLES = ("STAFF", "MANAGER")


def _cs_staff(session: Any) -> list[Any]:
    """켜진 우리 직원 가운데 CS 권한 팀의 STAFF · MANAGER — (id, 팀)만 읽는다(협력사 계정은 role 도 다르지만 한 번 더 거른다)."""
    rows = session.execute(select(User.id, User.team).where(User.is_active.is_(True), User.role.in_(_ROLES),
                                                            User.partner_org_id.is_(None)))
    return [row for row in rows if team_has_capability(row.team, ("CS",))]


def _subscribed(session: Any, user_ids: list[int]) -> set[int]:
    """살아 있는 푸시 구독이 있는 사용자 id."""
    if not user_ids:
        return set()
    stmt = select(NotificationPushSubscription.user_id).where(NotificationPushSubscription.user_id.in_(user_ids),
                                                              NotificationPushSubscription.revoked_at.is_(None))
    return set(session.scalars(stmt))


def recipients(session: Any) -> list[int]:
    """받을 사람 — CS 권한 팀 직원 가운데 구독이 살아 있는 사람(id 순)."""
    staff = [int(row.id) for row in _cs_staff(session)]
    subscribed = _subscribed(session, staff)
    return sorted(uid for uid in staff if uid in subscribed)


def subscription_counts(session: Any) -> dict[str, int]:
    """관리 화면 기록판 — 상담 직원 수 · 그중 구독이 살아 있는 수(이름 없음)."""
    staff = [int(row.id) for row in _cs_staff(session)]
    return {"staff": len(staff), "subscribed": len(_subscribed(session, staff))}


def _fold_older(session: Any, users: list[int], chat_id: str, at: datetime.datetime) -> int:
    """같은 상담의 안 읽은 앞 초안 알림을 읽음으로(사람 · 알림 줄 둘 다) — 바꾼 수."""
    older = session.scalars(select(Notification).where(Notification.notification_type == NOTIFY_DRAFT_READY,
                                                       Notification.target_user_id.in_(users),
                                                       Notification.is_read.is_(False)))
    folded = [note for note in older if cs_draft_chat(note.message) == chat_id]
    for note in folded:
        note.is_read, note.read_at = True, at
    if folded:
        states = session.scalars(select(NotificationUserState).where(
            NotificationUserState.notification_id.in_([note.id for note in folded]),
            NotificationUserState.read_at.is_(None)))
        for state in states:
            state.read_at = at
    return len(folded)


def notify_draft_ready(session: Any, *, turn_id: int, brand: str, chat_id: str, now: datetime.datetime,
                       is_business_day: Optional[Callable[[datetime.date], bool]] = None) -> list[int]:
    """초안 메모가 떴다고 구독한 상담 직원에게 알림 · 푸시(모듈 설명의 조건). 만든 알림 id 목록(글 · 사용자 정보 없음).

    알림 줄을 커밋한 뒤 푸시 일을 넣는다. 조건이 아니면 아무것도 쓰지 않고 빈 목록.
    """
    cfg = read_settings(session, log=False)
    if not (cfg.get("staff_push_enabled") and cfg.get("send_buttons_enabled")):
        session.commit()
        return []
    if not in_business_hours(brand, now, is_business_day):
        session.commit()
        logger.info("[CS 직원 알림] 운영 시간 밖이라 알리지 않는다 turn=%s", turn_id)
        return []
    users = recipients(session)
    if not users:
        session.commit()
        logger.info("[CS 직원 알림] 받을 사람이 없다(구독한 상담 직원 0) turn=%s", turn_id)
        return []
    at = naive_utc(now)
    folded = _fold_older(session, users, chat_id, at)
    message = alert_message(send_path(turn_id, chat_id), desk_link(brand, chat_id))
    ids = []
    for uid in users:
        notification = Notification(order_id=None, notification_type=NOTIFY_DRAFT_READY, target_type="USER",
                                    target_user_id=uid, is_urgent=False, title="상담 초안이 떴어요", message=message,
                                    is_read=False, created_at=at)
        session.add(notification)
        session.flush()
        fan_out_new_notification(session, notification, actor_user_id=None)
        ids.append(int(notification.id))
    session.commit()
    refused: dict[str, int] = {}
    for nid in ids:
        queued = push_sender.enqueue_push_for_notification(nid, db=session) or {}
        if not queued.get("enqueued", True):
            reason = str(queued.get("reason") or "unknown")
            refused[reason] = refused.get(reason, 0) + 1
    if refused:
        logger.warning("[CS 직원 알림] 푸시를 못 넣었다(알림 줄은 있다) turn=%s reasons=%s", turn_id, refused)
    logger.info("[CS 직원 알림] 초안 알림 turn=%s 받는 사람 %d명 접은 앞 알림 %d건", turn_id, len(ids), folded)
    return ids
