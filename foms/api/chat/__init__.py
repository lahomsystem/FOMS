"""Canonical chat API surface."""

from foms.api.chat.routes import chat_bp
from foms.api.chat.socketio_handlers import register_chat_socketio_handlers

__all__ = ["chat_bp", "register_chat_socketio_handlers"]
