"""Compatibility shim for the canonical `foms.services.file_utils` module."""

from foms.services.file_utils import (
    allowed_erp_media_file,
    allowed_file,
)

__all__ = [
    "allowed_file",
    "allowed_erp_media_file",
]
