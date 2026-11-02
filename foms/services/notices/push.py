"""공지 폰 알림 + 배지 — 설계서 docs/specs/2026-11-02-foms-notices_SPEC.md §7.

* 공지가 게시를 시작하면 받는 사람(:func:`~.audience.recipients`)마다 ``Notification``(종류 ``FOMS_NOTICE``,
  ``target_type="USER"``, ``target_user_id`` = 그 사람) 한 줄 + 수신자 상태를 만들고 폰으로 보낸다. 앱 아이콘 · 종 배지
  숫자에 잡히고, 공지를 읽거나 확인하면(:mod:`.service`) 그 상태가 읽음이 되어 숫자가 준다.
* 한 번만 보낸다 — ``UPDATE notices SET push_sent_at = now WHERE id = :id AND push_sent_at IS NULL`` 선점이 0줄이면 손대지
  않는다(웹 만들기와 SIDEFX 예약 스캔이 같은 공지를 두 번 울리지 않는다).
* 지금 게시 공지는 웹이 만들기(또는 고치기로 지금 게시가 된) 뒤 RQ 로 보낸다(``enqueue=True``). 예약 공지는 SIDEFX 가 약
  60초마다 :func:`sweep_due_notice_pushes` 로 찾아 바로 보낸다(``enqueue=False`` — SIDEFX 에는 REDIS 가 없다).
  끝난 예약 공지는 보내지 않고 보낸 때만 채운다.
* 폰 발송 실패는 로그만 남긴다 — 공지 · 알림 줄은 그대로 남는다.
"""
from __future__ import annotations

import datetime
import logging
from typing import Any, Optional

from sqlalchemy import or_, update

from foms.services.datetime_kst import now_utc_naive
from foms.services.notices.audience import is_live, recipients
from foms.services.notices.service import notice_ack_row
from foms.services.notifications.notice_push import FOMS_NOTICE_TYPE
from foms.services.notifications.push_sender import (
    enqueue_push_for_notification,
    send_push_for_notification,
)
from foms.services.notifications.recipients import fan_out_new_notification
from models import Notice, Notification

__all__ = [
    "FOMS_NOTICE_TYPE",
    "dispatch_notice_push",
    "push_notice_if_due",
    "sweep_due_notice_pushes",
]

logger = logging.getLogger(__name__)


def _claim(db, notice_id: int, now: datetime.datetime) -> bool:
    """보낼 차례를 선점한다 — 이미 누가 보냈으면(``push_sent_at`` 있음) False."""
    result = db.execute(
        update(Notice)
        .where(Notice.id == int(notice_id), Notice.push_sent_at.is_(None))
        .values(push_sent_at=now)
        .execution_options(synchronize_session=False)
    )
    return (result.rowcount or 0) > 0


def _notify_one(db, notice: Notice, user: Any) -> int:
    """한 사람 몫 알림 줄 + 수신자 상태 + 공지 기록 연결. 만든 알림 id."""
    notif = Notification(
        notification_type=FOMS_NOTICE_TYPE,
        target_type="USER",
        target_user_id=int(user.id),
        is_urgent=False,
        title=(notice.title or "공지")[:200],
        message="",
        created_by_user_id=notice.created_by_user_id,
        created_by_name=notice.created_by_name,
        is_read=False,
    )
    db.add(notif)
    db.flush()
    states = fan_out_new_notification(db, notif, actor_user_id=notice.created_by_user_id)
    row = notice_ack_row(db, int(notice.id), int(user.id))
    row.notification_id = int(notif.id)
    # 알림보다 먼저 읽었으면(만들기 커밋과 발송 사이) 배지에 잡지 않는다.
    seen = row.read_at or row.ack_at
    for state in states:
        if seen is not None and state.read_at is None:
            state.read_at = seen
        if row.ack_at is not None and state.ack_at is None:
            state.ack_at = row.ack_at
    return int(notif.id)


def _deliver(db, notification_id: int, *, enqueue: bool) -> None:
    """폰 발송 한 건 — 실패는 로그만(알림 줄은 이미 커밋됐다)."""
    try:
        if enqueue:
            enqueue_push_for_notification(notification_id, db=db)
        else:
            send_push_for_notification(notification_id, db=db)
            db.commit()
    except Exception:  # noqa: BLE001 - 폰 발송 실패가 공지를 막지 않는다
        db.rollback()
        logger.warning("[NOTICE] 공지 폰 알림 발송 실패 notification=%s", notification_id, exc_info=True)


def dispatch_notice_push(db, notice: Notice, *, now: Optional[datetime.datetime] = None, enqueue: bool) -> int:
    """게시 중 공지를 받는 사람마다 알림으로 만들고 폰으로 보낸다(커밋한다). 만든 알림 수.

    게시 중이 아니거나 이미 보냈으면(선점 0줄) 0. 받는 사람이 없어도 보낸 때는 채운다(다시 보지 않는다).

    Args:
        db: 세션 — 이 함수가 commit 한다.
        notice: 보낼 공지.
        now: UTC naive 지금(비면 지금).
        enqueue: True 면 RQ 로(웹), False 면 바로 보낸다(SIDEFX — REDIS 없음).
    """
    now = now or now_utc_naive()
    if notice is None or not is_live(notice, now):
        return 0
    try:
        if not _claim(db, int(notice.id), now):
            db.rollback()
            return 0
        ids = [_notify_one(db, notice, user) for user in recipients(db, notice)]
        db.commit()
    except Exception:
        db.rollback()
        raise
    for nid in ids:
        _deliver(db, nid, enqueue=enqueue)
    logger.info("[NOTICE] 공지 %s 폰 알림 %d건", getattr(notice, "id", None), len(ids))
    return len(ids)


def push_notice_if_due(db, notice_id: Any, *, enqueue: bool = True) -> int:
    """웹 만들기 · 고치기 뒤(커밋 후) — 지금 게시 중이고 아직 안 보냈으면 보낸다. 만든 알림 수(아니면 0)."""
    try:
        notice = db.get(Notice, int(notice_id))
    except (TypeError, ValueError):
        return 0
    if notice is None or notice.push_sent_at is not None:
        return 0
    return dispatch_notice_push(db, notice, enqueue=enqueue)


def sweep_due_notice_pushes(db, now: Optional[datetime.datetime] = None) -> dict[str, int]:
    """SIDEFX 예약 공지 스캔 — 게시가 시작됐는데 아직 안 보낸 공지를 바로 보낸다.

    끝난(``ends_at`` ≤ 지금) 미발송 공지는 보내지 않고 보낸 때만 채운다. 공지 하나가 실패해도 나머지는 보낸다.

    Returns:
        ``{"notices": 보낸 공지 수, "notifications": 만든 알림 수, "expired": 보내지 않고 닫은 공지 수, "failed": 실패 수}``
    """
    now = now or now_utc_naive()
    expired = db.execute(
        update(Notice)
        .where(
            Notice.deleted_at.is_(None), Notice.push_sent_at.is_(None),
            Notice.ends_at.isnot(None), Notice.ends_at <= now,
        )
        .values(push_sent_at=now)
        .execution_options(synchronize_session=False)
    ).rowcount or 0
    db.commit()
    due = (
        db.query(Notice)
        .filter(
            Notice.deleted_at.is_(None),
            Notice.push_sent_at.is_(None),
            or_(Notice.starts_at.is_(None), Notice.starts_at <= now),
            or_(Notice.ends_at.is_(None), Notice.ends_at > now),
        )
        .order_by(Notice.id)
        .all()
    )
    sent = made = failed = 0
    for notice in due:
        try:
            count = dispatch_notice_push(db, notice, now=now, enqueue=False)
        except Exception:  # noqa: BLE001 - 다음 공지는 보낸다, 이 공지는 다음 스캔이 다시 본다
            failed += 1
            logger.exception("[NOTICE] 예약 공지 폰 알림 실패 notice=%s", getattr(notice, "id", None))
            continue
        if count:
            sent += 1
            made += count
    return {"notices": sent, "notifications": made, "expired": int(expired), "failed": failed}
