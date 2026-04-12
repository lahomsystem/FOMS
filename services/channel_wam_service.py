"""Compatibility shim for the canonical `foms.services.channel_wam_service` module."""

from foms.services.channel_wam_service import (
    build_legacy_attachments,
    build_legacy_summary,
    build_legacy_wam_context,
    build_wam_bootstrap,
    build_wam_page,
    build_wam_request_context,
    get_wam_feature_flags,
)

__all__ = [
    "get_wam_feature_flags",
    "build_wam_request_context",
    "build_wam_page",
    "build_wam_bootstrap",
    "build_legacy_wam_context",
    "build_legacy_summary",
    "build_legacy_attachments",
]
