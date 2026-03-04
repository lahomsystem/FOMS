"""Socket.IO 기반 ERP 실시간 알림 전송 유틸."""
import logging
from flask import current_app

logger = logging.getLogger(__name__)


def emit_erp_notification_to_users(user_ids, payload=None):
    """지정 사용자 room(user_{id})으로 ERP 알림 이벤트를 전송."""
    if not user_ids:
        return 0

    socketio = current_app.config.get('_SOCKETIO_INSTANCE')
    if socketio is None:
        logger.warning(
            "[realtime] _SOCKETIO_INSTANCE is None. 실시간 알림 미전송. "
            "DB에는 저장되므로 새로고침/배지 폴링으로 확인 가능. "
            "원인: Socket.IO 미초기화 또는 REDIS_URL 미설정(다중 워커 시 필수)"
        )
        return 0

    data = dict(payload or {})
    data.setdefault('kind', 'erp_notification')

    sent = 0
    for uid in user_ids:
        try:
            room = f'user_{int(uid)}'
        except (TypeError, ValueError):
            continue
        socketio.emit('erp_notification', data, room=room)
        sent += 1
    logger.info("[realtime] erp_notification emit 완료: %d명 (urgent=%s)", sent, data.get('urgent'))
    return sent

