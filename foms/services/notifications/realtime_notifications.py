"""Socket.IO helpers for ERP realtime notifications (notifications context package)."""

from __future__ import annotations

import logging
from typing import Any

from flask import current_app

__all__ = ["emit_erp_notification_to_users"]

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
            room = f"user_{int(user_id)}"
        except (TypeError, ValueError):
            continue
        socketio.emit("erp_notification", data, room=room)
        sent += 1

    logger.info("[realtime] erp_notification emit 완료: %d명 (urgent=%s)", sent, data.get("urgent"))
    return sent
