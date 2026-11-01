"""협력사 공지 — 협력사 화면에 뜨고 "확인"을 눌러야 닫히는 창(사용자 2026-11-02).

새 표 없이 알림 표를 쓴다: 협력사 직원마다 ``Notification``(종류 ``PARTNER_NOTICE``, ``target_user_id`` = 그 직원) 한 건,
확인은 그 직원 ``NotificationUserState.ack_at``. 협력사 계정은 ``target_user_id`` 로 직접 지정한 알림만 받으므로
(``foms/services/notifications/recipients.py`` PARTNER-01) 우리 직원 알림과 섞이지 않는다. 우리 직원 긴급 창(빨간 전체
화면 · 24시간)과 달리 기한 없이 확인할 때까지 뜬다. 공지를 만드는 길은 ``tools/ops/send_partner_notice.py``.
"""
from __future__ import annotations

from typing import Any

from foms.services.datetime_kst import now_utc_naive
from foms.services.notifications.recipients import fan_out_new_notification
from models import Notification, NotificationUserState, PartnerOrg, User

PARTNER_NOTICE_TYPE = "PARTNER_NOTICE"
_PENDING_LIMIT = 5


def pending_partner_notices(db, user: Any) -> list[dict[str, Any]]:
    """이 협력사 직원이 아직 확인하지 않은 공지(오래된 것부터 최대 5건) — {id, title, message}."""
    if user is None or not getattr(user, "partner_org_id", None):
        return []
    rows = (
        db.query(Notification)
        .join(NotificationUserState, NotificationUserState.notification_id == Notification.id)
        .filter(
            NotificationUserState.user_id == user.id,
            NotificationUserState.ack_at.is_(None),
            Notification.notification_type == PARTNER_NOTICE_TYPE,
            Notification.target_user_id == user.id,
        )
        .order_by(Notification.created_at.asc(), Notification.id.asc())
        .limit(_PENDING_LIMIT)
        .all()
    )
    return [{"id": int(n.id), "title": n.title or "", "message": n.message or ""} for n in rows]


def ack_partner_notice(db, user: Any, notice_id: int) -> bool:
    """공지 확인(호출자가 commit). 내 공지가 아니면 False, 이미 확인했으면 그대로 True."""
    state = (
        db.query(NotificationUserState)
        .join(Notification, Notification.id == NotificationUserState.notification_id)
        .filter(
            NotificationUserState.notification_id == notice_id,
            NotificationUserState.user_id == user.id,
            Notification.notification_type == PARTNER_NOTICE_TYPE,
        )
        .first()
    )
    if state is None:
        return False
    now = now_utc_naive()
    if state.ack_at is None:
        state.ack_at = now
    if state.read_at is None:
        state.read_at = now
    notice = db.get(Notification, notice_id)
    if notice is not None and not notice.is_read:
        notice.is_read = True
    return True


def partner_notice_recipients(db) -> list[User]:
    """공지를 받을 협력사 직원 — 켜진 협력사의 켜진 계정."""
    return (
        db.query(User)
        .join(PartnerOrg, PartnerOrg.id == User.partner_org_id)
        .filter(User.is_active.is_(True), PartnerOrg.is_active.is_(True))
        .order_by(User.id)
        .all()
    )


def create_partner_notice(db, *, title: str, message: str, actor_user_id: int | None, actor_name: str,
                          apply: bool) -> list[dict[str, Any]]:
    """켜진 협력사 직원마다 공지 1건(호출자가 commit). 같은 제목 공지를 이미 받은 직원은 건너뛴다(다시 돌려도 안전).

    Returns:
        직원마다 {user_id, name, org, verdict(SEND | SENT | SKIP_ALREADY)}.
    """
    rows = []
    for user in partner_notice_recipients(db):
        already = db.query(Notification.id).filter(
            Notification.notification_type == PARTNER_NOTICE_TYPE,
            Notification.target_user_id == user.id,
            Notification.title == title,
        ).first()
        row = {"user_id": user.id, "name": user.name, "org_id": user.partner_org_id,
               "verdict": "SKIP_ALREADY" if already else "SEND"}
        if apply and not already:
            notice = Notification(
                notification_type=PARTNER_NOTICE_TYPE,
                target_type="USER",
                target_user_id=user.id,
                is_urgent=False,
                title=title,
                message=message,
                created_by_user_id=actor_user_id,
                created_by_name=actor_name,
                is_read=False,
            )
            db.add(notice)
            db.flush()
            fan_out_new_notification(db, notice, actor_user_id=actor_user_id)
            row["verdict"] = "SENT"
        rows.append(row)
    return rows
