"""Compatibility shim for the canonical `foms.services.channel_policy` module."""

from foms.services.channel_policy import (
    DEDUPE_WINDOWS,
    apply_attachment_policy,
    build_message_blocks,
    build_message_template,
    get_policy_version,
    get_routing_group_id,
    resolve_inbound_policy,
    resolve_push_policy,
    resolve_resend_policy,
)

__all__ = [
    "DEDUPE_WINDOWS",
    "build_message_blocks",
    "get_routing_group_id",
    "build_message_template",
    "apply_attachment_policy",
    "get_policy_version",
    "resolve_push_policy",
    "resolve_resend_policy",
    "resolve_inbound_policy",
]
