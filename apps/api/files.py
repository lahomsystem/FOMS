"""Thin adapter: files API; canonical implementation in `foms.api.files` (Wave 3)."""

from foms.services.storage import get_storage

from foms.api.files import (
    build_file_download_url,
    build_file_view_url,
    files_bp,
)

__all__ = [
    "build_file_download_url",
    "build_file_view_url",
    "files_bp",
    "get_storage",
]
