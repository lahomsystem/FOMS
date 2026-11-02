"""FOMS 공지사항 관리자 화면(설계서 docs/specs/2026-11-02-foms-notices_SPEC.md §5) — 뼈대. B(관리자 화면)가 채운다."""
from __future__ import annotations

from flask import Blueprint

notices_admin_bp = Blueprint("notices_admin", __name__)
