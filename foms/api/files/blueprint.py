"""Shared blueprint/config for attachments routes."""

import os

from flask import Blueprint


attachments_bp = Blueprint("attachments", __name__, url_prefix="/api")
USE_DIRECT_UPLOAD = os.environ.get("USE_DIRECT_UPLOAD", "1").lower() in ("1", "true", "yes", "on")
ASYNC_ATTACHMENT_THUMBNAIL = os.environ.get("ASYNC_ATTACHMENT_THUMBNAIL", "1").lower() in (
    "1",
    "true",
    "yes",
    "on",
)


__all__ = ["ASYNC_ATTACHMENT_THUMBNAIL", "USE_DIRECT_UPLOAD", "attachments_bp"]
