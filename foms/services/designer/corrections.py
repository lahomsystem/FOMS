"""FOMS Brain AX Designer — correction log helpers (DK-B8 enhanced).

DK-B8: CorrectionDelta shape with target_id, before, after, reason,
source, validated, candidate_rule_hint.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

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
    """Log a design correction entry (legacy interface — kept for backward compat)."""
    return create_correction(
        before_json=before_json,
        after_json=after_json,
        reason_text=reason_text,
        project_id=project_id,
        project_version_id=project_version_id,
        ai_run_id=ai_run_id,
        user_id=user_id,
    )


def build_manual_edit_delta(
    target_id: str,
    before: dict[str, Any],
    after: dict[str, Any],
    reason: Optional[str] = None,
    validated: bool = True,
    candidate_rule_hint: Optional[str] = None,
) -> dict[str, Any]:
    """Build a CorrectionDelta dict from a manual property edit.

    DK-B8: used when user edits a component property directly in Inspector.
    """
    # Invalid if before == after
    if before == after:
        validated = False

    return {
        "correction_id": str(uuid.uuid4()),
        "target_id": target_id,
        "before": before,
        "after": after,
        "reason": reason,
        "source": "user_manual_edit",
        "validated": validated,
        "candidate_rule_hint": candidate_rule_hint,
    }


def log_correction_delta(
    delta: dict[str, Any],
    project_id: Optional[int] = None,
    project_version_id: Optional[int] = None,
    user_id: Optional[int] = None,
) -> Any:
    """Log a CorrectionDelta dict (DK-B8 standard format).

    Stores the full delta as before_json/after_json for retrieval.
    """
    return create_correction(
        before_json=delta.get("before", {}),
        after_json=delta.get("after", {}),
        reason_text=delta.get("reason"),
        project_id=project_id,
        project_version_id=project_version_id,
        ai_run_id=None,
        user_id=user_id,
    )
