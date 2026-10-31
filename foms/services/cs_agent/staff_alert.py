"""초안 메모가 뜨면 상담 직원 FOMS 앱 웹 푸시(플랜 C10-5 · 설계서 17.3 '직원이 [보내기]' · 원장 R4-18).

- **받는 사람**: 켜진 우리 직원 가운데 CS 권한 팀(회계팀 포함 — :func:`team_has_capability`)의 STAFF · MANAGER 이고 **푸시 구독이
  살아 있는 사람만**(``notification_push_subscriptions.revoked_at`` 이 빈 줄). 구독이 없는 사람은 알림 줄도 만들지 않는다 — 폰으로
  닿지 않는 알림은 이 일의 뜻(90초 안 발송)이 없다. 구독 수는 관리 화면 기록판에 숫자로 보인다(:func:`subscription_counts`).
- **길**: 기존 그대로 — 사용자 지정(USER) 알림 한 줄 + 수신자 펼침(:func:`fan_out_new_notification`) → 커밋 → 푸시 일 넣기
  (:func:`~foms.services.notifications.push_sender.enqueue_push_for_notification` — 유형 :data:`NOTIFY_DRAFT_READY` 는 P1 · 급함).
- **글 없음**: 알림 줄 · 푸시에는 손님 글 · 초안을 싣지 않는다 — 데스크 상담 주소와 [보내기] 화면 주소만(푸시 문구는 유형별 일반 글).
- **스위치**: 관리 화면 '상담 직원 알림'(처음 끔). 알림이 실패해도 초안 차례는 그대로다(부르는 쪽이 기록만 남긴다).
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

from sqlalchemy import select

from foms.services.cs_agent.channel_read import naive_utc
from foms.services.cs_agent.report import desk_link
from foms.services.cs_agent.settings import read_settings
from foms.services.notifications import push_sender
from foms.services.notifications.cs_draft_link import NOTIFY_DRAFT_READY  # 푸시 P1 · 급함 유형(push_sender)
from foms.services.notifications.recipients import fan_out_new_notification
from foms.services.orders.order_mutation_policy import team_has_capability
from models import Notification, NotificationPushSubscription, User

logger = logging.getLogger(__name__)

__all__ = ["NOTIFY_DRAFT_READY", "SEND_PATH", "notify_draft_ready", "recipients", "subscription_counts"]

#: [보내기] 화면 같은 출처 경로 — 푸시 · 알림 목록의 바로가기(``foms/web/cs_agent_send.py``).
SEND_PATH = "/cs-agent/turns/{turn_id}/send?c={chat_id}"
_ROLES = ("STAFF", "MANAGER")


def _cs_staff(session: Any) -> list[Any]:
    """켜진 우리 직원 가운데 CS 권한 팀의 STAFF · MANAGER — (id, 팀)만 읽는다."""
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


def notify_draft_ready(session: Any, *, turn_id: int, brand: str, chat_id: str, now: datetime.datetime) -> list[int]:
    """초안 메모가 떴다고 구독한 상담 직원에게 알림 · 푸시. 스위치가 꺼졌거나 받을 사람이 없으면 아무것도 안 한다.

    알림 줄을 커밋한 뒤 푸시 일을 넣는다. 만든 알림 id 목록을 돌려준다(글 · 사용자 정보 없음).
    """
    if not read_settings(session, log=False).get("staff_push_enabled"):
        session.commit()
        return []
    users = recipients(session)
    if not users:
        session.commit()
        logger.info("[CS 직원 알림] 받을 사람이 없다(구독한 상담 직원 0) turn=%s", turn_id)
        return []
    path = SEND_PATH.format(turn_id=int(turn_id), chat_id=chat_id)
    message = "\n".join((f"[보내기 화면] {path}", f"[상담] {desk_link(brand, chat_id)}",
                         "[할 일] 초안을 보고 [보내기] 또는 [수정하기]를 눌러 주세요"))
    ids = []
    for uid in users:
        notification = Notification(order_id=None, notification_type=NOTIFY_DRAFT_READY, target_type="USER",
                                    target_user_id=uid, is_urgent=False, title="상담 초안이 떴어요", message=message,
                                    is_read=False, created_at=naive_utc(now))
        session.add(notification)
        session.flush()
        fan_out_new_notification(session, notification, actor_user_id=None)
        ids.append(int(notification.id))
    session.commit()
    for nid in ids:
        push_sender.enqueue_push_for_notification(nid, db=session)
    logger.info("[CS 직원 알림] 초안 알림 turn=%s 받는 사람 %d명", turn_id, len(ids))
    return ids
