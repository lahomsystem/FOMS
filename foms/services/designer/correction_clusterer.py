"""FOMS Brain PG-B11 — Correction Clusterer.

Clusters repeated user corrections into evidence-backed RuleCandidate entries.

Contract:
- Minimum 3 independent corrections required before a cluster is formed.
- Each candidate includes supporting correction IDs as evidence.
- AI generates candidates only — human approval + replay required for promotion.
- fail_count > 0 in replay_report blocks promotion.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

MIN_CLUSTER_SIZE = 3  # minimum independent corrections to form a candidate

# Source/hint values that must never seed a rule candidate.
# These are generic upload/test markers, not independent correction evidence.
_BLOCKED_HINT_SOURCES = frozenset({
    "learning_upload",
    "raw_learning_sample",
    "learning_sample_upload",
    "qa_test",
    "qa_seed",
    "generic",
})


# ──────────────────────────────────────────────────────────
# Clustering logic
# ──────────────────────────────────────────────────────────

def cluster_corrections(
    corrections: list[dict[str, Any]],
    min_count: int = MIN_CLUSTER_SIZE,
) -> list[dict[str, Any]]:
    """Group corrections by pattern and return cluster summaries.

    Args:
        corrections: List of DesignerCorrection.after_json dicts.
        min_count: Minimum corrections to form a cluster.

    Returns:
        List of cluster dicts, each with:
          pattern_key, correction_ids, sample_deltas, count, evidence_strength
    """
    # Group by candidate_rule_hint or source field.
    # Skip corrections whose pattern key resolves to a blocked generic source —
    # these are raw uploads or test records, not independent correction evidence.
    groups: dict[str, list[dict]] = {}
    for corr in corrections:
        hint = (
            corr.get("candidate_rule_hint")
            or corr.get("source")
            or "generic"
        )
        if hint in _BLOCKED_HINT_SOURCES:
            logger.debug("[CLUSTERER] skip blocked hint source=%r", hint)
            continue
        groups.setdefault(hint, []).append(corr)

    clusters = []
    for key, group in groups.items():
        if len(group) < min_count:
            continue
        ids = [c.get("_correction_id") for c in group if c.get("_correction_id")]
        clusters.append({
            "pattern_key": key,
            "correction_ids": ids[:20],
            "sample_deltas": group[:5],
            "count": len(group),
            "evidence_strength": min(1.0, len(group) / 10.0),
        })
        logger.info("[CLUSTERER] cluster=%s count=%d evidence=%.2f",
                    key, len(group), min(1.0, len(group) / 10.0))

    return clusters


def build_rule_candidates_from_clusters(
    clusters: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert clusters into rule candidate payloads for DesignerRuleCandidate.

    Returns:
        List of candidate_json dicts (not yet saved to DB).
    """
    candidates = []
    for cluster in clusters:
        candidate_json = {
            "rule_hint": cluster["pattern_key"],
            "correction_count": cluster["count"],
            "evidence_correction_ids": cluster["correction_ids"],
            "sample_deltas": cluster["sample_deltas"],
            "evidence_strength": cluster["evidence_strength"],
            "auto_generated": True,   # must be human-reviewed before promotion
        }
        candidates.append({
            "source_correction_ids": cluster["correction_ids"],
            "candidate_json": candidate_json,
        })
    return candidates


def run_correction_clustering_pipeline(
    project_id: int | None = None,
    min_count: int = MIN_CLUSTER_SIZE,
) -> list[int]:
    """Full pipeline: load corrections → cluster → save RuleCandidates.

    Returns:
        List of newly created DesignerRuleCandidate IDs.
    """
    from db import db_session
    from foms.persistence.designer.models import DesignerCorrection, DesignerRuleCandidate

    # Load recent corrections
    q = db_session.query(DesignerCorrection)
    if project_id is not None:
        q = q.filter(DesignerCorrection.project_id == project_id)
    corrections_rows = q.order_by(DesignerCorrection.created_at.desc()).limit(500).all()

    # Build correction dicts with IDs
    correction_dicts = []
    for row in corrections_rows:
        d = dict(row.after_json or {})
        d["_correction_id"] = row.id
        correction_dicts.append(d)

    if not correction_dicts:
        logger.info("[CLUSTERER] no corrections found, skipping")
        return []

    clusters = cluster_corrections(correction_dicts, min_count=min_count)
    if not clusters:
        logger.info("[CLUSTERER] no clusters formed (min_count=%d not reached)", min_count)
        return []

    candidates = build_rule_candidates_from_clusters(clusters)

    # Save to DB
    created_ids = []
    for cand in candidates:
        rc = DesignerRuleCandidate(
            source_correction_ids=cand["source_correction_ids"],
            candidate_json=cand["candidate_json"],
            status="draft",
        )
        db_session.add(rc)
        db_session.flush()
        created_ids.append(rc.id)

    db_session.commit()
    logger.info("[CLUSTERER] created %d rule candidates", len(created_ids))
    return created_ids
