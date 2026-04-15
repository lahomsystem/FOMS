"""Shared chat blueprint."""

from flask import Blueprint


chat_bp = Blueprint("chat", __name__, url_prefix="")


__all__ = ["chat_bp"]
