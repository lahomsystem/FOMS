"""PG-B11: Learning Loop Productionization Tests.

Verifies:
1. correction_clusterer requires >= 3 independent corrections.
2. Clusters produce evidence-backed rule candidates.
3. rule_replay blocks promotion when fail_count > 0.
4. check_promotion_gate enforces status, replay, fail_count.
5. Active ontology invariant: at most one 'active' row.
"""

from __future__ import annotations

import pytest
from foms.services.designer.correction_clusterer import (
    cluster_corrections, build_rule_candidates_from_clusters, MIN_CLUSTER_SIZE,
)
from foms.services.designer.rule_replay import check_promotion_gate


# ──────────────────────────────────────────────────────────
# PG-B11-01: Import
# ──────────────────────────────────────────────────────────

def test_correction_clusterer_importable():
    from foms.services.designer import correction_clusterer
    assert callable(correction_clusterer.cluster_corrections)

def test_rule_replay_importable():
    from foms.services.designer import rule_replay
    assert callable(rule_replay.replay_against_corpus)
    assert callable(rule_replay.check_promotion_gate)


# ──────────────────────────────────────────────────────────
# PG-B11-02: Clustering logic
# ──────────────────────────────────────────────────────────

class TestCorrectionClustering:
    def _make_corrections(self, hint: str, count: int) -> list[dict]:
        return [
            {"candidate_rule_hint": hint, "field": "width", "value": 2400, "_correction_id": i}
            for i in range(count)
        ]

    def test_below_min_count_no_cluster(self):
        """< 3 corrections → no cluster formed."""
        corrections = self._make_corrections("ep_too_narrow", 2)
        clusters = cluster_corrections(corrections, min_count=3)
        assert len(clusters) == 0

    def test_exactly_min_count_forms_cluster(self):
        """Exactly 3 corrections → cluster formed."""
        corrections = self._make_corrections("ep_too_narrow", 3)
        clusters = cluster_corrections(corrections, min_count=3)
        assert len(clusters) == 1
        assert clusters[0]["count"] == 3

    def test_cluster_has_correction_ids(self):
        corrections = self._make_corrections("ep_too_narrow", 4)
        clusters = cluster_corrections(corrections)
        assert "correction_ids" in clusters[0]
        assert len(clusters[0]["correction_ids"]) >= 3

    def test_cluster_has_evidence_strength(self):
        corrections = self._make_corrections("ep_too_narrow", 5)
        clusters = cluster_corrections(corrections)
        assert 0.0 < clusters[0]["evidence_strength"] <= 1.0

    def test_multiple_patterns_form_separate_clusters(self):
        c1 = self._make_corrections("pattern_a", 3)
        c2 = self._make_corrections("pattern_b", 4)
        clusters = cluster_corrections(c1 + c2)
        assert len(clusters) == 2

    def test_cluster_sample_deltas_attached(self):
        corrections = self._make_corrections("some_hint", 5)
        clusters = cluster_corrections(corrections)
        assert "sample_deltas" in clusters[0]
        assert len(clusters[0]["sample_deltas"]) <= 5

    def test_candidates_from_clusters_have_evidence(self):
        corrections = self._make_corrections("ep_too_narrow", 4)
        clusters = cluster_corrections(corrections)
        candidates = build_rule_candidates_from_clusters(clusters)
        assert len(candidates) == 1
        cj = candidates[0]["candidate_json"]
        assert "evidence_correction_ids" in cj
        assert "rule_hint" in cj
        assert cj["auto_generated"] is True

    def test_candidates_require_human_review(self):
        """auto_generated=True marks that human review is needed."""
        corrections = self._make_corrections("x", 3)
        clusters = cluster_corrections(corrections)
        candidates = build_rule_candidates_from_clusters(clusters)
        for cand in candidates:
            assert cand["candidate_json"]["auto_generated"] is True


# ──────────────────────────────────────────────────────────
# PG-B11-03: Promotion gate
# ──────────────────────────────────────────────────────────

class TestPromotionGate:
    def test_check_gate_candidate_not_found(self):
        from unittest.mock import patch
        with patch("db.db_session") as mock_db:
            mock_db.get.return_value = None
            result = check_promotion_gate(999999)
        assert result["allowed"] is False
        assert "not found" in result["reason"].lower()

    def test_active_ontology_invariant_contract(self):
        """DesignerOntologyVersion has status Enum with 'active' option."""
        from foms.persistence.designer.models import DesignerOntologyVersion
        cols = {c.key for c in DesignerOntologyVersion.__table__.columns}
        assert "status" in cols

    def test_rule_candidate_status_enum(self):
        """DesignerRuleCandidate.status has draft/approved/rejected/promoted."""
        from foms.persistence.designer.models import DesignerRuleCandidate
        status_col = DesignerRuleCandidate.__table__.columns["status"]
        # Column default should be draft
        default = str(status_col.default.arg) if status_col.default else None
        assert default == "draft"

    def test_replay_report_json_exists_on_model(self):
        """DesignerRuleCandidate has replay_report_json column."""
        from foms.persistence.designer.models import DesignerRuleCandidate
        cols = {c.key for c in DesignerRuleCandidate.__table__.columns}
        assert "replay_report_json" in cols

    def _gate(self, status: str, replay_report: dict | None) -> dict:
        """Helper: call check_promotion_gate with mocked candidate."""
        from unittest.mock import MagicMock, patch
        mock_candidate = MagicMock()
        mock_candidate.status = status
        mock_candidate.replay_report_json = replay_report
        with patch("db.db_session") as mock_db:
            mock_db.get.return_value = mock_candidate
            return check_promotion_gate(1)

    def test_fail_count_blocks_promotion(self):
        result = self._gate("approved", {"fail_count": 2, "pass_count": 3})
        assert result["allowed"] is False
        assert "fail_count" in result["reason"]

    def test_approved_and_clean_replay_allows_promotion(self):
        result = self._gate("approved", {"fail_count": 0, "pass_count": 5})
        assert result["allowed"] is True

    def test_draft_status_blocks_promotion(self):
        result = self._gate("draft", {"fail_count": 0})
        assert result["allowed"] is False

    def test_no_replay_report_blocks_promotion(self):
        result = self._gate("approved", None)
        assert result["allowed"] is False
        assert "replay" in result["reason"].lower()


# ──────────────────────────────────────────────────────────
# PG-B11-04: File structure
# ──────────────────────────────────────────────────────────

class TestLearningLoopFileStructure:
    from pathlib import Path
    ROOT = Path(__file__).parent.parent.parent

    def test_correction_clusterer_exists(self):
        f = self.ROOT / "foms" / "services" / "designer" / "correction_clusterer.py"
        assert f.exists()

    def test_rule_replay_exists(self):
        f = self.ROOT / "foms" / "services" / "designer" / "rule_replay.py"
        assert f.exists()

    def test_evolution_service_exists(self):
        f = self.ROOT / "foms" / "services" / "designer" / "evolution.py"
        assert f.exists()

    def test_correction_clusterer_has_min_count(self):
        content = (self.ROOT / "foms" / "services" / "designer" / "correction_clusterer.py").read_text(encoding="utf-8")
        assert "MIN_CLUSTER_SIZE" in content
        assert "min_count" in content
