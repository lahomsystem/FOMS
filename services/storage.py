"""Compatibility shim for the canonical storage helpers."""

from foms.services.storage import (
    BOTO3_AVAILABLE,
    PILLOW_AVAILABLE,
    StorageAdapter,
    get_storage,
)

__all__ = [
    "BOTO3_AVAILABLE",
    "PILLOW_AVAILABLE",
    "StorageAdapter",
    "get_storage",
]
