"""Compatibility shim for the canonical `foms.services.channel_identity` module."""

from foms.services.channel_identity import (
    get_user_by_manager_id,
    is_action_allowed_for_manager,
)

__all__ = [
    "get_user_by_manager_id",
    "is_action_allowed_for_manager",
]
