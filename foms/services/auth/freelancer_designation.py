"""FCOMM-01 3단계 겹 5: 직원을 프리랜서로 켤 때 옆길을 닫는다(설계서 §6.3 겹 5 · 검수 원장 A5).

관리자 설정 저장(``POST /api/admin/sales-freelancers``)이 켜진 프리랜서를 저장할 때 **같은 트랜잭션에서** 부른다.
여러 번 불러도 결과가 같다(이미 지운 회원 · 이미 숨긴 알림은 다시 세지 않는다).

- 옛 알림 숨김(``archived_at``) — 지정 전에 받은 알림 중 남기는 것은 둘뿐이다:
  나를 콕 집은 알림(``target_user``)과 담당 이름 알림(``target_manager_name``) 중 **내가 연결된 주문**의 것,
  그리고 주문이 없는 나를 콕 집은 알림(팀 펼침 공지 — ``target_team`` 이 적힌 것 — 은 뺀다).
  전체 · 역할 · 팀 경로로 받은 알림, 연결되지 않은 주문의 알림은 모두 숨긴다.
- 커밋 뒤: 이 사람의 열린 실시간 연결을 끊는다(다시 연결하면 숨긴 알림 뒤 상태로 새로 받는다). 이 서버에 붙은
  연결만 끊을 수 있다 — 다른 서버의 연결은 다음 재연결 때 닫힌다.

사내 채팅은 CHAT-DEL-01(2026-11-07)로 지워 채팅방 회원 해제는 없앴다(남은 빈 표는 아무 데도 쓰이지 않는다).
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from flask import current_app, has_app_context

from foms.services.datetime_kst import now_utc_naive
from models import (
    Notification,
    NotificationEvent,
    NotificationEventType,
    NotificationRecipientSource,
    NotificationUserState,
    OrderFreelancerLink,
)

logger = logging.getLogger(__name__)

#: 남길 수 있는 수신 경로(그 밖의 경로 — 전체 · 역할 · 팀 · 옛 되채우기 — 로 받은 알림은 숨긴다).
_KEEPABLE_SOURCES = frozenset({
    NotificationRecipientSource.TARGET_USER,
    NotificationRecipientSource.TARGET_MANAGER_NAME,
})
#: 숨김 감사 이벤트에 남기는 이유.
HIDE_REASON = "freelancer_designation"
_CHUNK = 500


def keeps_notification(source: Any, order_id: Any, target_team: Any, linked_order_ids: set[int]) -> bool:
    """지정 뒤에도 남길 알림인가(순수 함수 — 시험이 직접 부른다).

    Args:
        source: state 의 ``recipient_source``.
        order_id: 알림의 주문 번호(없으면 None).
        target_team: 알림의 ``target_team``(공지 팀 펼침이면 적혀 있다).
        linked_order_ids: 이 프리랜서가 연결된 주문 번호.
    """
    if source not in _KEEPABLE_SOURCES:
        return False
    if order_id is not None:
        return int(order_id) in linked_order_ids
    return source == NotificationRecipientSource.TARGET_USER and not str(target_team or "").strip()


def hide_stale_notifications(db: Any, user_id: int, actor_user_id: Optional[int] = None) -> int:
    """지정 전에 받은 알림 중 남기지 않을 것을 숨긴다(``archived_at``) → 숨긴 수.

    여러 줄을 한 번에 숨기고, 감사 이벤트는 보관 일괄 처리(``archive-all``)와 같이 대표 한 줄만 남긴다.
    """
    uid = int(user_id)
    linked = {
        int(oid)
        for (oid,) in db.query(OrderFreelancerLink.order_id).filter(OrderFreelancerLink.user_id == uid).distinct()
    }
    rows = (
        db.query(
            NotificationUserState.id,
            NotificationUserState.notification_id,
            NotificationUserState.recipient_source,
            Notification.order_id,
            Notification.target_team,
        )
        .join(Notification, Notification.id == NotificationUserState.notification_id)
        .filter(NotificationUserState.user_id == uid, NotificationUserState.archived_at.is_(None))
        .all()
    )
    hide = [r for r in rows if not keeps_notification(r.recipient_source, r.order_id, r.target_team, linked)]
    if not hide:
        return 0
    now = now_utc_naive()
    state_ids = [int(r.id) for r in hide]
    for start in range(0, len(state_ids), _CHUNK):
        chunk = state_ids[start:start + _CHUNK]
        (db.query(NotificationUserState)
         .filter(NotificationUserState.id.in_(chunk), NotificationUserState.archived_at.is_(None))
         .update({NotificationUserState.archived_at: now}, synchronize_session=False))
    db.add(NotificationEvent(
        notification_id=max(int(r.notification_id) for r in hide),
        actor_user_id=actor_user_id,
        recipient_user_id=uid,
        event_type=NotificationEventType.ARCHIVE,
        metadata_json={"bulk": True, "count": len(state_ids), "reason": HIDE_REASON},
    ))
    return len(state_ids)


def apply_designation_side_effects(db: Any, user_id: int, actor_user_id: Optional[int] = None) -> dict[str, int]:
    """켜진 프리랜서로 저장할 때 같은 트랜잭션에서 부른다(커밋은 부르는 쪽).

    연결 다시 맞추기(``resync_freelancer_links``) **뒤에** 불러야 "연결된 주문" 판정이 새 연결을 본다.

    Returns:
        ``{"notifications_hidden": m}`` — 감사 줄에 그대로 싣는다.
    """
    hidden = hide_stale_notifications(db, user_id, actor_user_id)
    db.flush()
    return {"notifications_hidden": hidden}


def disconnect_realtime(user_id: int) -> int:
    """커밋 뒤: 이 서버에 붙은 이 사람의 실시간 연결을 끊는다 → 끊은 수. 실패해도 저장 결과는 그대로다."""
    if not has_app_context():
        return 0
    socketio = current_app.config.get("_SOCKETIO_INSTANCE")
    server = getattr(socketio, "server", None) if socketio is not None else None
    if server is None:
        return 0
    try:
        sids = [sid for sid, _eio_sid in server.manager.get_participants("/", f"user_{int(user_id)}")]
        for sid in sids:
            server.disconnect(sid, namespace="/")
    except Exception:  # noqa: BLE001 — 끊기 실패가 설정 저장을 되돌리면 안 된다(다음 재연결 때 닫힌다)
        logger.warning("[FCOMM] 프리랜서 지정 뒤 실시간 연결 끊기 실패 user=%s", user_id, exc_info=True)
        return 0
    return len(sids)


__all__ = [
    "HIDE_REASON",
    "apply_designation_side_effects",
    "disconnect_realtime",
    "hide_stale_notifications",
    "keeps_notification",
]
