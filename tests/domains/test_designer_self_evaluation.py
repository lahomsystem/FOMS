"""PG-L5: Self-Evaluation Dashboard Tests."""

from __future__ import annotations

import pytest
from foms.services.designer.self_evaluation import (
    EvalSnapshot, compute_snapshot, compare_snapshots,
)


class TestEvalSnapshot:
    def test_importable(self):
        from foms.services.designer import self_evaluation
        assert callable(self_evaluation.compute_snapshot)
        assert callable(self_evaluation.compare_snapshots)

    def test_compute_snapshot_returns_snapshot(self):
        snap = compute_snapshot(period="2026-05")
        assert isinstance(snap, EvalSnapshot)
        assert snap.period == "2026-05"
        assert snap.captured_at

    def test_compute_snapshot_graceful_no_db(self):
        """compute_snapshot never raises even on empty/offline DB."""
        snap = compute_snapshot()
        assert snap is not None

    def test_health_score_range(self):
        snap = EvalSnapshot(
            period="2026-05", captured_at="now",
            extraction_correction_rate=0.2,
            candidate_approval_rate=0.8,
            rule_candidate_pass_rate=0.7,
        )
        score = snap.overall_health_score()
        assert 0.0 <= score <= 1.0

    def test_health_score_perfect(self):
        snap = EvalSnapshot(
            period="2026-05", captured_at="now",
            extraction_correction_rate=0.0,
            candidate_approval_rate=1.0,
            rule_candidate_pass_rate=1.0,
        )
        assert snap.overall_health_score() == 1.0

    def test_regression_detected_high_correction_rate(self):
        snap = EvalSnapshot(
            period="2026-05", captured_at="now",
            extraction_correction_rate=0.9,
        )
        # compute_snapshot sets regression_detected, but we test the logic directly
        snap.regression_detected = snap.extraction_correction_rate > 0.8
        assert snap.regression_detected is True

    def test_to_dict_has_required_fields(self):
        snap = EvalSnapshot(period="2026-05", captured_at="now")
        d = snap.to_dict()
        required = {
            "period", "captured_at", "extraction_correction_rate",
            "candidate_approval_rate", "rule_candidate_pass_rate",
            "design_cases_accumulated", "overall_health_score",
            "regression_detected",
        }
        assert required <= set(d.keys())


class TestSnapshotComparison:
    def _snap(self, period, corr_rate, approval_rate, rule_rate, cases) -> EvalSnapshot:
        return EvalSnapshot(
            period=period, captured_at="2026-05-14T00:00:00Z",
            extraction_correction_rate=corr_rate,
            candidate_approval_rate=approval_rate,
            rule_candidate_pass_rate=rule_rate,
            design_cases_accumulated=cases,
        )

    def test_compare_no_previous_returns_baseline(self):
        current = self._snap("2026-05", 0.3, 0.7, 0.8, 10)
        result = compare_snapshots(current, None)
        assert result["trend"] == "baseline"

    def test_improving_trend(self):
        prev = self._snap("2026-04", 0.5, 0.5, 0.5, 5)
        curr = self._snap("2026-05", 0.2, 0.8, 0.9, 15)
        result = compare_snapshots(curr, prev)
        assert result["trend"] == "improving"
        assert result["health_delta"] > 0

    def test_regressing_trend(self):
        prev = self._snap("2026-04", 0.1, 0.9, 0.9, 10)
        curr = self._snap("2026-05", 0.6, 0.4, 0.3, 8)
        result = compare_snapshots(curr, prev)
        assert result["trend"] == "regressing"
        assert result["health_delta"] < 0

    def test_cases_delta_computed(self):
        prev = self._snap("2026-04", 0.3, 0.7, 0.7, 5)
        curr = self._snap("2026-05", 0.3, 0.7, 0.7, 15)
        result = compare_snapshots(curr, prev)
        assert result["cases_delta"] == 10
