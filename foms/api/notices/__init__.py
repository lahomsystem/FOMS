"""FOMS 공지사항 JSON API(설계서 docs/specs/2026-11-02-foms-notices_SPEC.md §4) — 뼈대. A(백엔드)가 채운다."""
from __future__ import annotations

from flask import Blueprint

notices_admin_api_bp = Blueprint("notices_admin_api", __name__, url_prefix="/api/admin/notices")
notices_api_bp = Blueprint("notices_api", __name__, url_prefix="/api/notices")
