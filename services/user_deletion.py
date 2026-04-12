"""Compatibility shim for the canonical `foms.services.user_deletion` module."""

from foms.services.user_deletion import (
    detach_user_references_for_delete,
    ensure_order_attachment_user_fk_set_null,
)

__all__ = [
    "detach_user_references_for_delete",
    "ensure_order_attachment_user_fk_set_null",
]
