"""Channel web pages: /chat HTML (owner: ``foms.web.channel``). JSON/Socket.IO: ``foms.api.channel``."""

from __future__ import annotations

import os

from flask import Blueprint, Response, current_app, render_template

from foms.web.auth import login_required
from foms.services.storage import get_storage

USE_DIRECT_UPLOAD = os.environ.get("USE_DIRECT_UPLOAD", "1").lower() in ("1", "true", "yes", "on")

channel_chat_pages_bp = Blueprint("channel_chat_pages", __name__, url_prefix="")


def _chat_use_direct_upload() -> bool:
    """채팅 페이지/스크립트용 direct upload 여부 (공통)."""
    try:
        storage = get_storage()
        return USE_DIRECT_UPLOAD and storage.storage_type in ("r2", "s3")
    except Exception:
        return False


@channel_chat_pages_bp.route("/chat")
@login_required
def chat():
    """채팅 페이지 (Quest 10)."""
    socketio_available = (
        current_app.config.get("SOCKETIO_AVAILABLE", False)
        and current_app.config.get("_SOCKETIO_INSTANCE") is not None
    )
    use_direct_upload = _chat_use_direct_upload()
    return render_template(
        "channel/chat.html",
        socketio_available=socketio_available,
        use_direct_upload=use_direct_upload,
    )


@channel_chat_pages_bp.route("/chat/scripts.js")
@login_required
def chat_scripts_js():
    """채팅 스크립트 번들 (외부 JS로 분리하여 </script> 파싱 이슈 제거)."""
    body = render_template(
        "partials/chat_scripts_bundle.html",
        use_direct_upload=_chat_use_direct_upload(),
    )
    return Response(body, mimetype="application/javascript; charset=utf-8")


__all__ = [
    "USE_DIRECT_UPLOAD",
    "_chat_use_direct_upload",
    "channel_chat_pages_bp",
    "chat",
    "chat_scripts_js",
]
