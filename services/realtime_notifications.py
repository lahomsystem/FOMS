"""Socket.IO 기반 ERP 실시간 알림 전송 유틸."""
from flask import current_app


def emit_erp_notification_to_users(user_ids, payload=None):
    """지정 사용자 room(user_{id})으로 ERP 알림 이벤트를 전송."""
    if not user_ids:
        return 0

    socketio = current_app.config.get('_SOCKETIO_INSTANCE')
    if socketio is None:
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
    return sent

