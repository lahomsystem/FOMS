"""FOMS Brain AX Designer – Evolution/ontology rule candidate helpers (stub)."""

from __future__ import annotations


def create_rule_candidate_from_corrections(correction_ids: list[int], candidate_json: dict) -> dict:
    """Create a rule upgrade candidate for human review.

    Stub – actual ML-based rule extraction is out of MVP scope.
    """
    from foms.persistence.designer.models import DesignerRuleCandidate
    from db import db_session

    candidate = DesignerRuleCandidate(
        source_correction_ids=correction_ids,
        candidate_json=candidate_json,
    )
    db_session.add(candidate)
    db_session.commit()
    db_session.refresh(candidate)
    return {"id": candidate.id, "status": candidate.status}
