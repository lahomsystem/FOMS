"""FOMS Brain PG-L5 — Self-Evaluation Dashboard Service.

Computes monthly improvement scorecard to track learning progress.

Metrics tracked:
  extraction_correction_rate   낮을수록 좋음 (추출 후 수정 비율)
  candidate_approval_rate      높을수록 좋음 (후보 승인 비율)
  rule_candidate_pass_rate     높을수록 좋음 (룰 후보 replay 통과율)
  new_archetype_candidates     증가할수록 좋음 (신규 archetype 발견)
  design_cases_accumulated     증가할수록 좋음 (누적 승인 설계 사례)
  cost_per_approved_case       낮을수록 좋음 (추출 비용 효율)

Scorecard is saved monthly to `designer_eval_snapshots` (in-memory for now,
full DB persistence in later iteration).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────
# Scorecard shape
# ──────────────────────────────────────────────────────────

@dataclass
class EvalSnapshot:
    """Monthly self-evaluation snapshot."""

    period: str              # "2026-05" format
    captured_at: str         # ISO timestamp

    # Extraction quality
    total_extractions: int = 0
    corrected_extractions: int = 0
    extraction_correction_rate: float = 0.0   # lower = better

    # Candidate quality
    total_candidates: int = 0
    approved_candidates: int = 0
    candidate_approval_rate: float = 0.0      # higher = better

    # Rule / replay
    total_rule_candidates: int = 0
    replay_passed_rules: int = 0
    rule_candidate_pass_rate: float = 0.0     # higher = better

    # Learning growth
    design_cases_accumulated: int = 0
    new_archetype_candidates: int = 0

    # Cost
    total_extraction_cost_usd: float = 0.0
    cost_per_approved_case: float = 0.0

    # Gate
    regression_detected: bool = False         # True blocks promotion
    notes: list[str] = field(default_factory=list)

    def overall_health_score(self) -> float:
        """0.0–1.0 composite health score."""
        scores = []
        # Correction rate: 0% = 1.0, 100% = 0.0
        scores.append(1.0 - self.extraction_correction_rate)
        # Approval rate: 0% = 0.0, 100% = 1.0
        scores.append(self.candidate_approval_rate)
        # Rule pass rate
        scores.append(self.rule_candidate_pass_rate)
        return sum(scores) / len(scores) if scores else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "period": self.period,
            "captured_at": self.captured_at,
            "extraction_correction_rate": round(self.extraction_correction_rate, 4),
            "candidate_approval_rate": round(self.candidate_approval_rate, 4),
            "rule_candidate_pass_rate": round(self.rule_candidate_pass_rate, 4),
            "design_cases_accumulated": self.design_cases_accumulated,
            "new_archetype_candidates": self.new_archetype_candidates,
            "total_extraction_cost_usd": round(self.total_extraction_cost_usd, 4),
            "cost_per_approved_case": round(self.cost_per_approved_case, 4),
            "overall_health_score": round(self.overall_health_score(), 4),
            "regression_detected": self.regression_detected,
            "notes": self.notes,
        }


# ──────────────────────────────────────────────────────────
# Snapshot computation
# ──────────────────────────────────────────────────────────

def compute_snapshot(period: str | None = None) -> EvalSnapshot:
    """Compute current self-evaluation snapshot.

    Args:
        period: "YYYY-MM" string. Defaults to current month.

    Returns:
        EvalSnapshot with computed metrics.
    """
    now = datetime.now(timezone.utc)
    if period is None:
        period = now.strftime("%Y-%m")

    snap = EvalSnapshot(
        period=period,
        captured_at=now.isoformat(),
    )

    # Corrections
    try:
        from db import db_session
        from foms.persistence.designer.models import DesignerCorrection
        snap.total_extractions = db_session.query(DesignerCorrection).count()
        snap.corrected_extractions = snap.total_extractions  # all corrections = post-extraction fixes
        if snap.total_extractions > 0:
            snap.extraction_correction_rate = min(1.0, snap.corrected_extractions / max(snap.total_extractions, 1))
    except Exception as exc:
        logger.warning("[EVAL] corrections query failed: %s", exc)
        snap.notes.append(f"corrections_error: {exc}")

    # Extraction candidates (DB-level)
    try:
        from foms.persistence.designer.models import DesignerExtractionCandidate
        snap.total_candidates = db_session.query(DesignerExtractionCandidate).count()
        snap.approved_candidates = db_session.query(DesignerExtractionCandidate).filter(
            DesignerExtractionCandidate.approved == True  # noqa: E712
        ).count()
        if snap.total_candidates > 0:
            snap.candidate_approval_rate = snap.approved_candidates / snap.total_candidates
    except Exception as exc:
        logger.warning("[EVAL] candidates query failed: %s", exc)

    # Rule candidates
    try:
        from foms.persistence.designer.models import DesignerRuleCandidate
        snap.total_rule_candidates = db_session.query(DesignerRuleCandidate).count()
        snap.replay_passed_rules = db_session.query(DesignerRuleCandidate).filter(
            DesignerRuleCandidate.status.in_(["approved", "promoted"])
        ).count()
        if snap.total_rule_candidates > 0:
            snap.rule_candidate_pass_rate = snap.replay_passed_rules / snap.total_rule_candidates
    except Exception as exc:
        logger.warning("[EVAL] rule_candidates query failed: %s", exc)

    # Design cases accumulated
    try:
        from foms.persistence.designer.models import DesignerDesignCase
        snap.design_cases_accumulated = db_session.query(DesignerDesignCase).count()
    except Exception as exc:
        logger.warning("[EVAL] design_cases query failed: %s", exc)

    # Archetype candidates
    try:
        from foms.services.designer.product_archetype_learning import run_archetype_discovery_pipeline
        candidates = run_archetype_discovery_pipeline()
        snap.new_archetype_candidates = len(candidates)
    except Exception as exc:
        logger.warning("[EVAL] archetype discovery failed: %s", exc)

    # Cost per approved case
    if snap.approved_candidates > 0:
        snap.cost_per_approved_case = snap.total_extraction_cost_usd / snap.approved_candidates

    # Regression gate: extraction correction rate > 80% is a warning
    if snap.extraction_correction_rate > 0.8:
        snap.regression_detected = True
        snap.notes.append("High correction rate (>80%) — Gemini prompt may need tuning")

    logger.info(
        "[EVAL] period=%s health=%.2f corrections=%.1f%% approvals=%.1f%% cases=%d",
        period,
        snap.overall_health_score(),
        snap.extraction_correction_rate * 100,
        snap.candidate_approval_rate * 100,
        snap.design_cases_accumulated,
    )
    return snap


def save_snapshot_to_db(snap: EvalSnapshot) -> int | None:
    """Persist an EvalSnapshot to designer_eval_snapshots table.

    Returns row ID or None on failure.
    """
    try:
        from db import db_session
        from sqlalchemy import text

        db_session.execute(
            text("""
                INSERT INTO designer_eval_snapshots
                  (period, captured_at, extraction_correction_rate,
                   candidate_approval_rate, rule_candidate_pass_rate,
                   design_cases_accumulated, new_archetype_candidates,
                   total_extraction_cost_usd, overall_health_score,
                   regression_detected, notes_json)
                VALUES
                  (:period, NOW(), :corr_rate, :appr_rate, :rule_rate,
                   :cases, :archetypes, :cost, :health, :regression, CAST(:notes AS JSON))
                ON CONFLICT DO NOTHING
            """),
            {
                "period": snap.period,
                "corr_rate": snap.extraction_correction_rate,
                "appr_rate": snap.candidate_approval_rate,
                "rule_rate": snap.rule_candidate_pass_rate,
                "cases": snap.design_cases_accumulated,
                "archetypes": snap.new_archetype_candidates,
                "cost": snap.total_extraction_cost_usd,
                "health": snap.overall_health_score(),
                "regression": snap.regression_detected,
                "notes": __import__("json").dumps(snap.notes, ensure_ascii=False),
            },
        )
        db_session.commit()
        logger.info("[EVAL] snapshot saved for period=%s", snap.period)
        return 1
    except Exception as exc:
        logger.warning("[EVAL] DB save failed (non-fatal): %s", exc)
        return None


def run_monthly_evaluation(period: str | None = None, save_to_db: bool = True) -> dict[str, Any]:
    """Compute and optionally persist the monthly evaluation snapshot.

    Returns:
        EvalSnapshot.to_dict()
    """
    snap = compute_snapshot(period)
    if save_to_db:
        save_snapshot_to_db(snap)
    return snap.to_dict()


# ──────────────────────────────────────────────────────────
# Trend comparison
# ──────────────────────────────────────────────────────────

def compare_snapshots(
    current: EvalSnapshot,
    previous: EvalSnapshot | None,
) -> dict[str, Any]:
    """Compare two snapshots to show improvement/regression."""
    if previous is None:
        return {"comparison": "no_previous", "trend": "baseline"}

    delta_health = current.overall_health_score() - previous.overall_health_score()
    delta_cases = current.design_cases_accumulated - previous.design_cases_accumulated
    delta_correction = current.extraction_correction_rate - previous.extraction_correction_rate

    trend = "improving" if delta_health > 0.02 else ("regressing" if delta_health < -0.02 else "stable")

    return {
        "period_current": current.period,
        "period_previous": previous.period,
        "health_delta": round(delta_health, 4),
        "cases_delta": delta_cases,
        "correction_rate_delta": round(delta_correction, 4),
        "trend": trend,
        "regression_gate": current.regression_detected,
    }
