"""Compatibility shim: flat `foms.services.file_utils` → files package."""

from foms.services.files.file_utils import (
    allowed_erp_media_file,
    allowed_file,
)

__all__ = [
    "allowed_file",
    "allowed_erp_media_file",
]
