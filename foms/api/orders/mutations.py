"""Compatibility bridge for legacy field-update mutations."""

from .field_update import (
    ORDER_UPDATE_ALLOWED_FIELDS,
    STRUCTURED_SYNC_FIELDS,
    ensure_path,
    update_order_field_response,
)

__all__ = [
    "ORDER_UPDATE_ALLOWED_FIELDS",
    "STRUCTURED_SYNC_FIELDS",
    "ensure_path",
    "update_order_field_response",
]
