"""Socket.IO helpers for ERP realtime notifications (notifications context package).

연결 · 끊김 핸들러(:func:`register_realtime_socketio_handlers`)도 여기 둔다 — 연결 때 서버가 본인 개인 방
``user_<id>`` 에 넣고, ERP 알림(:func:`emit_erp_notification_to_users`)이 그 방으로 간다. 사내 채팅을 지우며
(CHAT-DEL-01, 2026-11-07) 채팅 핸들러에서 떼어 왔다. 시험: tests/security/test_realtime_socket_connect.py
"""

from __future__ import annotations

import logging
from typing import Any

from flask import current_app, session

from db import get_db
from foms.services.auth.partner_scope import is_partner_user
from models import User

__all__ = ["emit_erp_notification_to_users", "register_realtime_socketio_handlers", "user_room"]

USER_ROOM_PREFIX = "user_"


def user_room(user_id: Any) -> str:
    """개인 알림 방 이름."""
    return f"{USER_ROOM_PREFIX}{int(user_id)}"

logger = logging.getLogger(__name__)


def emit_erp_notification_to_users(user_ids: Any, payload: Any = None) -> int:
    """Emit an ERP notification event to each valid user room."""
    if not user_ids:
        return 0

    socketio = current_app.config.get("_SOCKETIO_INSTANCE")
    if socketio is None:
        logger.warning(
            "[realtime] _SOCKETIO_INSTANCE is None. 실시간 알림 미전송. "
            "DB에는 저장되므로 새로고침/배지 폴링으로 확인 가능. "
            "원인: Socket.IO 미초기화 또는 REDIS_URL 미설정(다중 워커 시 필수)"
        )
        return 0

    data = dict(payload or {})
    data.setdefault("kind", "erp_notification")

    sent = 0
    for user_id in user_ids:
        try:
            room = user_room(user_id)
        except (TypeError, ValueError):
            continue
        socketio.emit("erp_notification", data, room=room)
        sent += 1

    logger.info("[realtime] erp_notification emit 완료: %d명 (urgent=%s)", sent, data.get("urgent"))
    return sent


def register_realtime_socketio_handlers(socketio: Any) -> None:
    """실시간 알림 연결 핸들러(연결 · 끊김) 등록.

    Socket.IO 는 Flask ``before_request`` 문지기를 거치지 않으므로 여기서 따로 막는다 — 로그인 안 함 ·
    없거나 비활성 계정(INACTIVE-SESSION-01) · 협력사 계정(PARTNER-01)은 연결을 받지 않는다.
    """
    from flask_socketio import emit, join_room

    @socketio.on("connect")
    def handle_connect():
        user_id = session.get("user_id")
        if not user_id:
            return False
        user = get_db().query(User).filter(User.id == user_id).first()
        if user is None or not user.is_active or is_partner_user(user):
            return False
        join_room(user_room(user_id))
        emit("connected", {"user_id": user_id, "message": "연결되었습니다."})
        return None

    @socketio.on("disconnect")
    def handle_disconnect():
        return None
