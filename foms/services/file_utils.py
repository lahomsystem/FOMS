"""Filename extension validation helpers shared across upload flows."""

from __future__ import annotations

from constants import ALLOWED_EXTENSIONS, ERP_MEDIA_ALLOWED_EXTENSIONS

__all__ = [
    "allowed_file",
    "allowed_erp_media_file",
]


def allowed_file(filename: str) -> bool:
    """Return whether the filename is an allowed Excel upload extension."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def allowed_erp_media_file(filename: str) -> bool:
    """Return whether the filename is an allowed ERP media upload extension."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ERP_MEDIA_ALLOWED_EXTENSIONS
