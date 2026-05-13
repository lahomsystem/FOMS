"""FOMS Brain AX Designer – correction log helpers."""

from __future__ import annotations

from typing import Optional

from foms.persistence.designer.repositories import create_correction


def log_correction(
    before_json: dict,
    after_json: dict,
    reason_text: Optional[str] = None,
    project_id: Optional[int] = None,
    project_version_id: Optional[int] = None,
    ai_run_id: Optional[int] = None,
    user_id: Optional[int] = None,
):
    """Log a design correction entry."""
    return create_correction(
        before_json=before_json,
        after_json=after_json,
        reason_text=reason_text,
        project_id=project_id,
        project_version_id=project_version_id,
        ai_run_id=ai_run_id,
        user_id=user_id,
    )
