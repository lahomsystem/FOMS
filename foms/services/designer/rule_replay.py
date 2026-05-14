"""FOMS Brain PG-B11 — Rule Replay Service.

Replays a rule candidate against the approved fixture corpus and
design cases to ensure fail_count == 0 before promotion is allowed.

Contract:
- fail_count > 0 BLOCKS promotion (hard gate).
- Replay is read-only: never modifies designs or ontology.
- Replay report is stored on the DesignerRuleCandidate.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def replay_against_corpus(
    candidate_id: int,
    fixture_designs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Replay rule candidate against design fixture corpus.

    Args:
        candidate_id: DesignerRuleCandidate.id.
        fixture_designs: Optional list of design_json dicts.
                         If None, uses built-in wardrobe fixtures.

    Returns:
        Replay report dict:
          pass_count, fail_count, total_fixtures,
          new_validation_errors, affected_furniture_types.

    Raises:
        ValueError: If candidate not found or already promoted.
    """
    from db import db_session
    from foms.persistence.designer.models import DesignerRuleCandidate
    from foms.services.designer.validator import validate_design

    candidate = db_session.get(DesignerRuleCandidate, candidate_id)
    if not candidate:
        raise ValueError(f"Rule candidate {candidate_id} not found")
    if candidate.status == "promoted":
        raise ValueError(f"Candidate {candidate_id} already promoted — cannot re-run replay")

    # Use built-in fixtures if none provided
    if not fixture_designs:
        fixture_designs = _get_builtin_fixtures()

    pass_count = 0
    fail_count = 0
    new_errors: list[str] = []
    affected_types: set[str] = set()

    for design in fixture_designs:
        try:
            result = validate_design(design)
            if result.errors:
                fail_count += 1
                new_errors.extend(e.code for e in result.errors[:3])
                ftype = _get_furniture_type(design)
                affected_types.add(ftype)
            else:
                pass_count += 1
        except Exception as exc:
            fail_count += 1
            new_errors.append(str(exc))

    report = {
        "candidate_id": candidate_id,
        "pass_count": pass_count,
        "fail_count": fail_count,
        "total_fixtures": len(fixture_designs),
        "new_validation_errors": list(set(new_errors)),
        "affected_furniture_types": sorted(affected_types),
        "promotion_blocked": fail_count > 0,
    }

    # Store report on candidate
    candidate.replay_report_json = report
    db_session.commit()
    logger.info(
        "[REPLAY] candidate=%d pass=%d fail=%d blocked=%s",
        candidate_id, pass_count, fail_count, fail_count > 0,
    )
    return report


def _get_builtin_fixtures() -> list[dict[str, Any]]:
    """Return minimal built-in design fixtures for replay."""
    from foms.services.designer.assembly_factories import (
        WardrobeParams, create_wardrobe_assembly,
    )
    return [
        create_wardrobe_assembly(WardrobeParams(width=2400, height=2200, depth=600, module_count=2)).to_dict(),
        create_wardrobe_assembly(WardrobeParams(width=3000, height=2400, depth=620, module_count=3)).to_dict(),
    ]


def _get_furniture_type(design: dict[str, Any]) -> str:
    return design.get("assembly", {}).get("type", "unknown")


def check_promotion_gate(candidate_id: int) -> dict[str, Any]:
    """Check if promotion is allowed for a candidate.

    Returns:
        dict with allowed (bool) and reason (str).
    """
    from db import db_session
    from foms.persistence.designer.models import DesignerRuleCandidate

    candidate = db_session.get(DesignerRuleCandidate, candidate_id)
    if not candidate:
        return {"allowed": False, "reason": "candidate not found"}
    if candidate.status != "approved":
        return {
            "allowed": False,
            "reason": f"status={candidate.status!r}, must be 'approved' (human action required)",
        }
    if not candidate.replay_report_json:
        return {"allowed": False, "reason": "replay not run — run replay first"}
    fail_count = candidate.replay_report_json.get("fail_count", 0)
    if fail_count > 0:
        return {
            "allowed": False,
            "reason": f"replay fail_count={fail_count} > 0 — fix rule before promoting",
        }
    return {"allowed": True, "reason": "all gates passed"}
