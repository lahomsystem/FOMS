"""Compatibility shim for the canonical `foms.services.channel_security` module."""

from foms.services.channel_security import (
    CHANNEL_SIGNING_KEY,
    SECRET_KEY,
    WAM_DEFAULT_ALLOWED_SECTIONS,
    WAM_DEFAULT_SCOPES,
    generate_wam_entry_token,
    generate_wam_launch_token,
    generate_wam_session_token,
    generate_wam_short_link_token,
    require_channel_signature,
    verify_channel_signature,
    verify_wam_entry_token,
    verify_wam_launch_token,
    verify_wam_session_token,
    verify_wam_short_link_token,
    wam_entry_serializer,
    wam_serializer,
    wam_session_serializer,
    wam_shortlink_serializer,
)

__all__ = [
    "verify_channel_signature",
    "require_channel_signature",
    "generate_wam_launch_token",
    "generate_wam_entry_token",
    "generate_wam_short_link_token",
    "generate_wam_session_token",
    "verify_wam_launch_token",
    "verify_wam_entry_token",
    "verify_wam_short_link_token",
    "verify_wam_session_token",
]
