"""
Canonical files API package (Wave 3).

Registry and product code import `foms.api.files` directly.
Wave 8 (W8-B5): legacy `apps.api.files` direct-import bridge removed.
"""
from foms.services.storage import get_storage

from foms.api.files.routes import (
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
