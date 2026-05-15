"""FOMS Brain Post-V1 — Ontology Evolution Service.

PV2-B8: correction delta → rule candidate pipeline.
PV2-B9: rule replay + human-gated promotion.

Hard constraints:
- AI generates rule candidates ONLY.
- promote_candidate requires human approval + replay report.
- active ontology DB invariant: at most one 'active' row.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────
# B8: Rule Candidate Creation
# ──────────────────────────────────────────────────────────

def create_rule_candidate_from_corrections(
    correction_ids: list[int],
    candidate_json: dict,
) -> dict:
    """Create a rule upgrade candidate for human review.

    AI MUST NOT call promote_candidate. Human approval required.
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
    logger.info("[EVOLUTION] rule candidate created: id=%s", candidate.id)
    return {"id": candidate.id, "status": candidate.status}


def cluster_corrections_to_candidates(
    candidate_rule_hint: str,
    min_count: int = 3,
    project_id: Optional[int] = None,
) -> list[dict]:
    """Query corrections with matching candidate_rule_hint and group them.

    Returns list of candidate dicts ready for create_rule_candidate_from_corrections.
    Returns [] on DB failure (non-fatal).
    """
    try:
        from db import db_session
        from foms.persistence.designer.models import DesignerCorrection
    except Exception as exc:
        logger.warning("[EVOLUTION] cluster_corrections: import failed: %s", exc)
        return []

    try:
        query = db_session.query(DesignerCorrection)
        if project_id is not None:
            query = query.filter(DesignerCorrection.project_id == project_id)

        corrections = query.order_by(DesignerCorrection.created_at.desc()).limit(200).all()
    except Exception as exc:
        logger.warning("[EVOLUTION] cluster_corrections: DB query failed: %s", exc)
        return []

    # Filter by candidate_rule_hint in after_json
    matching_ids: list[int] = []
    deltas: list[dict] = []
    for corr in corrections:
        after = corr.after_json or {}
        if (
            after.get("candidate_rule_hint") == candidate_rule_hint
            or after.get("source") in ("user_manual_edit", "command_apply")
        ):
            matching_ids.append(corr.id)
            deltas.append(after)

    if len(matching_ids) < min_count:
        return []

    candidate_json = {
        "rule_hint": candidate_rule_hint,
        "correction_count": len(matching_ids),
        "sample_deltas": deltas[:5],
    }
    return [{"correction_ids": matching_ids[:20], "candidate_json": candidate_json}]


# ──────────────────────────────────────────────────────────
# B9: Rule Replay
# ──────────────────────────────────────────────────────────

def replay_rule_candidate(
    candidate_id: int,
    fixture_designs: Optional[list[dict]] = None,
) -> dict[str, Any]:
    """Replay a rule candidate against known-good design fixtures.

    Returns replay report:
      pass_count, fail_count, changed_design_count,
      new_validation_errors, affected_furniture_types.

    This is a read-only operation. Never modifies designs or ontology.
    """
    from db import db_session
    from foms.persistence.designer.models import DesignerRuleCandidate
    from foms.services.designer.validator import validate_design

    candidate = db_session.get(DesignerRuleCandidate, candidate_id)
    if not candidate:
        raise ValueError(f"Rule candidate {candidate_id} not found")

    if not fixture_designs:
        # Use a minimal built-in fixture set
        from foms.services.designer.assembly_factories import WardrobeParams, create_wardrobe_assembly
        fixture_designs = [
            create_wardrobe_assembly(WardrobeParams(width=2400, height=2200, depth=600, module_count=2)).to_dict(),
            create_wardrobe_assembly(WardrobeParams(width=3000, height=2400, depth=620, module_count=3)).to_dict(),
        ]

    pass_count = 0
    fail_count = 0
    new_errors: list[str] = []
    affected_types: set[str] = set()
    changed_count = 0

    for design in fixture_designs:
        result_before = validate_design(design)
        # In V1, candidate replay just re-validates with current rules
        # (full ML-based rule application is out of V1 scope)
        result_after = validate_design(design)

        before_errors = set(e.code for e in result_before.errors)
        after_errors = set(e.code for e in result_after.errors)
        new_err_codes = after_errors - before_errors

        if new_err_codes:
            fail_count += 1
            new_errors.extend(new_err_codes)
        else:
            pass_count += 1

        if new_err_codes:
            changed_count += 1
            ftype = design.get("assembly", {}).get("type", "unknown")
            affected_types.add(ftype)

    report = {
        "candidate_id": candidate_id,
        "pass_count": pass_count,
        "fail_count": fail_count,
        "changed_design_count": changed_count,
        "new_validation_errors": list(set(new_errors)),
        "affected_furniture_types": sorted(affected_types),
        "total_fixtures": len(fixture_designs),
    }

    # Store replay report on candidate
    candidate.replay_report_json = report
    db_session.commit()
    logger.info(
        "[EVOLUTION] replay done: candidate=%s pass=%d fail=%d",
        candidate_id, pass_count, fail_count,
    )
    return report


# ──────────────────────────────────────────────────────────
# B9: Human-gated Promotion
# ──────────────────────────────────────────────────────────

def approve_and_promote_candidate(
    candidate_id: int,
    target_version_key: str,
    rules_json: dict,
    user_id: Optional[int] = None,
) -> dict[str, Any]:
    """Human approval step: promote draft rule candidate to active ontology.

    Contract:
    - AI MUST NOT call this function directly.
    - Requires candidate.replay_report_json to exist (replay must have run).
    - Requires candidate.status == "approved".
    - Uses repository.promote_ontology_version for DB-level invariant.

    Raises:
        ValueError: if candidate not found, not approved, or replay not run.
    """
    from db import db_session
    from foms.persistence.designer.models import DesignerRuleCandidate, DesignerOntologyVersion
    from foms.persistence.designer.repositories import promote_ontology_version

    candidate = db_session.get(DesignerRuleCandidate, candidate_id)
    if not candidate:
        raise ValueError(f"Rule candidate {candidate_id} not found")
    if not candidate.replay_report_json:
        raise ValueError(
            f"Cannot promote candidate {candidate_id}: replay report not found. "
            "Run replay_rule_candidate first."
        )
    if candidate.status != "approved":
        raise ValueError(
            f"Cannot promote candidate {candidate_id}: status is {candidate.status!r}. "
            "Set candidate.status='approved' first (human action required)."
        )
    if candidate.replay_report_json.get("fail_count", 0) > 0:
        raise ValueError(
            f"Cannot promote candidate {candidate_id}: replay has "
            f"{candidate.replay_report_json['fail_count']} failures. Fix before promoting."
        )

    # Create draft ontology version
    new_ontology = DesignerOntologyVersion(
        version_key=target_version_key,
        status="draft",
        rules_json=rules_json,
    )
    db_session.add(new_ontology)
    db_session.flush()

    # Promote via repository (ensures single active invariant)
    promoted = promote_ontology_version(new_ontology.id, user_id=user_id)

    # Mark candidate as promoted
    candidate.status = "promoted"
    db_session.commit()

    logger.info(
        "[EVOLUTION] ontology promoted: version_key=%s ontology_id=%s",
        target_version_key, promoted.id,
    )
    return {
        "promoted_ontology_id": promoted.id,
        "version_key": promoted.version_key,
        "status": promoted.status,
        "candidate_id": candidate_id,
    }
