"""Canonical channel API surface (ChannelTalk integrations).

사내 채팅(``chat`` 블루프린트 · Socket.IO 채팅 이벤트)은 CHAT-DEL-01(2026-11-07)로 지웠다. 실시간 알림 연결은
:mod:`foms.services.notifications.realtime_notifications`.
"""

from foms.api.channel.channel_functions import channel_functions_bp
from foms.api.channel.channel_integration import channel_integration_bp
from foms.api.channel.channel_webhooks import channel_webhooks_bp
from foms.api.channel.channel_wam import (
    channel_shortlink_bp,
    channel_wam_api_bp,
    channel_wam_bp,
)

__all__ = [
    "channel_functions_bp",
    "channel_integration_bp",
    "channel_shortlink_bp",
    "channel_wam_api_bp",
    "channel_wam_bp",
    "channel_webhooks_bp",
]
