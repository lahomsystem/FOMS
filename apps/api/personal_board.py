"""
개인 맞춤형 브리핑 보드 API — thin adapter (Wave 3).

계획서: docs/plans/2026-03-02-personal-briefing-board-plan.md
Canonical logic: `foms.api.personal_board`.
"""
from flask import Blueprint

from apps.auth import login_required
from foms.api.personal_board import (
    DEFAULT_OWNER_TEAM_BY_STAGE,
    personal_board_summary_response,
)

personal_board_bp = Blueprint(
    "personal_board",
    __name__,
    url_prefix="/api/personal-board",
)

__all__ = [
    "DEFAULT_OWNER_TEAM_BY_STAGE",
    "personal_board_bp",
    "personal_board_summary_response",
]


@personal_board_bp.route("/summary", methods=["GET"])
@login_required
def api_summary():
    """GET /api/personal-board/summary — 위임."""
    return personal_board_summary_response()
