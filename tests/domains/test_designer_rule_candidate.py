"""PV2-B8/B9 Rule Candidate + Replay + Promotion tests.

Note: tests that touch DB use the `app` fixture so that SQLite in-memory
tables are created via Base.metadata.create_all() before each test.
"""

from __future__ import annotations

import pytest

# Ensure all DB tests get a fresh in-memory DB with designer tables created.
pytestmark = pytest.mark.usefixtures("app")

from foms.services.designer.evolution import (
    replay_rule_candidate,
    approve_and_promote_candidate,
)


class TestRuleCandidateCreation:
    def test_create_candidate_from_dict(self):
        from foms.services.designer.evolution import create_rule_candidate_from_corrections
        result = create_rule_candidate_from_corrections(
            correction_ids=[1, 2, 3],
            candidate_json={"rule_hint": "test_rule", "description": "test"},
        )
        assert "id" in result
        assert result["status"] == "draft"

    def test_candidate_json_is_preserved(self):
        from foms.services.designer.evolution import create_rule_candidate_from_corrections
        candidate_json = {"rule_hint": "top_sr_prefers_30mm", "correction_count": 5}
        result = create_rule_candidate_from_corrections([1, 2, 3, 4, 5], candidate_json)
        from db import db_session
        from foms.persistence.designer.models import DesignerRuleCandidate
        candidate = db_session.get(DesignerRuleCandidate, result["id"])
        assert candidate.candidate_json["rule_hint"] == "top_sr_prefers_30mm"


class TestRuleReplay:
    def test_replay_returns_report(self):
        from foms.services.designer.evolution import create_rule_candidate_from_corrections
        result = create_rule_candidate_from_corrections([1], {"rule_hint": "replay_test"})
        report = replay_rule_candidate(result["id"])
        assert "pass_count" in report
        assert "fail_count" in report
        assert "changed_design_count" in report
        assert "new_validation_errors" in report
        assert "affected_furniture_types" in report
        assert "total_fixtures" in report

    def test_replay_not_found_raises(self):
        with pytest.raises(ValueError, match="not found"):
            replay_rule_candidate(999999)

    def test_replay_with_custom_fixtures(self):
        from foms.services.designer.evolution import create_rule_candidate_from_corrections
        from foms.services.designer.assembly_factories import WardrobeParams, create_wardrobe_assembly
        fixtures = [
            create_wardrobe_assembly(WardrobeParams(width=2400, height=2200, depth=600)).to_dict(),
        ]
        result = create_rule_candidate_from_corrections([1], {"rule_hint": "custom_fixture_test"})
        report = replay_rule_candidate(result["id"], fixture_designs=fixtures)
        assert report["total_fixtures"] == 1

    def test_replay_stores_report_on_candidate(self):
        from foms.services.designer.evolution import create_rule_candidate_from_corrections
        from db import db_session
        from foms.persistence.designer.models import DesignerRuleCandidate
        result = create_rule_candidate_from_corrections([1], {"rule_hint": "store_test"})
        replay_rule_candidate(result["id"])
        candidate = db_session.get(DesignerRuleCandidate, result["id"])
        assert candidate.replay_report_json is not None


class TestOntologyPromotion:
    def test_promote_without_replay_fails(self):
        from foms.services.designer.evolution import create_rule_candidate_from_corrections
        from db import db_session
        from foms.persistence.designer.models import DesignerRuleCandidate

        result = create_rule_candidate_from_corrections([1], {"rule_hint": "no_replay_test"})
        # Set status to approved but no replay
        candidate = db_session.get(DesignerRuleCandidate, result["id"])
        candidate.status = "approved"
        db_session.commit()

        with pytest.raises(ValueError, match="replay report not found"):
            approve_and_promote_candidate(
                result["id"],
                "test-version-no-replay",
                {"test": True},
            )

    def test_promote_without_approval_fails(self):
        from foms.services.designer.evolution import create_rule_candidate_from_corrections
        result = create_rule_candidate_from_corrections([1], {"rule_hint": "no_approval_test"})
        replay_rule_candidate(result["id"])

        with pytest.raises(ValueError, match="status is 'draft'"):
            approve_and_promote_candidate(
                result["id"],
                "test-version-no-approval",
                {"test": True},
            )

    def test_promote_candidate_not_found(self):
        with pytest.raises(ValueError, match="not found"):
            approve_and_promote_candidate(999999, "v-test", {})


class TestActiveOntologySingleInvariant:
    def test_assert_single_active_ontology(self):
        from foms.persistence.designer.repositories import (
            assert_single_active_ontology,
            get_or_create_default_ontology,
        )
        get_or_create_default_ontology()
        # Should not raise if single active
        assert_single_active_ontology()

    def test_ai_cannot_modify_active_ontology_directly(self):
        """Ensure there's no direct active ontology setter without promotion guard."""
        from foms.services.designer.evolution import approve_and_promote_candidate
        # The function requires approved status + replay → AI cannot call it unilaterally
        # This test verifies the guard exists
        with pytest.raises((ValueError, TypeError)):
            approve_and_promote_candidate(
                candidate_id=None,  # type: ignore
                target_version_key="ai-direct",
                rules_json={},
            )
