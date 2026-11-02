"""FOMS 공지사항 본사 직원 화면 /notices(설계서 docs/specs/2026-11-02-foms-notices_SPEC.md §5) — 뼈대. C(받는 사람 화면)가 채운다."""
from __future__ import annotations

from flask import Blueprint

notices_web_bp = Blueprint("notices_web", __name__)
