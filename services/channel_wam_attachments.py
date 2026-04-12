"""Compatibility shim for the canonical `foms.services.channel_wam_attachments` module."""

from foms.services.channel_wam_attachments import (
    get_scoped_attachment,
    list_attachment_groups,
    resolve_attachment_redirect_url,
)

__all__ = [
    "get_scoped_attachment",
    "list_attachment_groups",
    "resolve_attachment_redirect_url",
]
