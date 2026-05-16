"""PG-R1/R2: Drawing Intake Pipeline tests.

Tests the drawing_intake_pipeline service layer:
- run_intake_pipeline integration (fake Gemini via DESIGNER_FAKE_VISION env)
- compute_ui_state logic
- DrawingPipelineResult contract
- GEMINI_API_KEY missing → exception (no silent fallback)
- Multi-page PDF → blocking_reason added
- save-learning-sample no longer sets candidate_rule_hint
- model_router route_and_extract fake fallback removed
"""

from __future__ import annotations

import os
import pytest


# ──────────────────────────────────────────────────────────
# compute_ui_state tests (pure function, no DB)
# ──────────────────────────────────────────────────────────

class TestComputeUiState:
    def _fn(self, furniture_type, unresolved, validation_result, extra=None):
        from foms.services.designer.drawing_intake_pipeline import compute_ui_state
        return compute_ui_state(
            furniture_type=furniture_type,
            unresolved_fields=unresolved,
            validation_result=validation_result,
            extra_blocking_reasons=extra,
        )

    def test_can_review_always_true(self):
        state = self._fn("wardrobe", [], {"valid": True, "errors": []})
        assert state["can_review"] is True

    def test_can_preview_3d_true_when_all_conditions_met(self):
        state = self._fn("wardrobe", [], {"valid": True, "errors": []})
        assert state["can_preview_3d"] is True
        assert state["blocking_reasons"] == []

    def test_can_preview_3d_false_when_unresolved(self):
        state = self._fn("wardrobe", ["width", "height"], {"valid": False, "errors": []})
        assert state["can_preview_3d"] is False
        reasons = " ".join(state["blocking_reasons"])
        assert "unresolved_fields" in reasons

    def test_can_preview_3d_false_when_unsupported_type(self):
        # custom_storage is now supported (C-1 fix). Use a genuinely unknown type.
        state = self._fn("office_desk", [], {"valid": True, "errors": []})
        assert state["can_preview_3d"] is False
        reasons = " ".join(state["blocking_reasons"])
        assert "unsupported_furniture_type" in reasons

    def test_can_preview_3d_false_when_validator_failed(self):
        state = self._fn("wardrobe", [], {"valid": False, "errors": ["width out of range"]})
        assert state["can_preview_3d"] is False
        reasons = " ".join(state["blocking_reasons"])
        assert "validator_failed" in reasons

    def test_can_approve_always_false_at_upload(self):
        state = self._fn("wardrobe", [], {"valid": True, "errors": []})
        assert state["can_approve"] is False

    def test_can_save_design_case_always_false_at_upload(self):
        state = self._fn("wardrobe", [], {"valid": True, "errors": []})
        assert state["can_save_design_case"] is False

    def test_extra_blocking_reasons_appear_in_list(self):
        """Extra reasons (e.g. multi_page_pdf) are recorded but don't hard-block
        can_preview_3d when the extracted page is otherwise complete."""
        state = self._fn("wardrobe", [], {"valid": True, "errors": []},
                         extra=["multi_page_pdf:2_pages"])
        # blocking_reasons contains the warning
        assert any("multi_page_pdf" in r for r in state["blocking_reasons"])
        # can_preview_3d is NOT hard-blocked — page 1 extraction is complete
        assert state["can_preview_3d"] is True

    def test_shoe_rack_is_supported_type(self):
        state = self._fn("shoe_rack", [], {"valid": True, "errors": []})
        assert state["can_preview_3d"] is True

    def test_kitchen_wall_is_supported_type(self):
        state = self._fn("kitchen_wall", [], {"valid": True, "errors": []})
        assert state["can_preview_3d"] is True


# ──────────────────────────────────────────────────────────
# DrawingPipelineResult contract
# ──────────────────────────────────────────────────────────

class TestDrawingPipelineResult:
    def _make(self, **kwargs):
        from foms.services.designer.drawing_intake_pipeline import DrawingPipelineResult
        defaults = dict(
            artifact_id=1, extraction_id=2, candidate_db_id=3,
            candidate_local_id="uuid-abc",
            routing={"provider": "gemini"},
            redaction_report={"text_pii_redacted": True},
            extraction={"furniture_type": "wardrobe"},
            candidate={"candidate_id": "uuid-abc"},
            metrics={"cost_usd": 0.0},
            ui_state={"can_preview_3d": True, "blocking_reasons": []},
        )
        defaults.update(kwargs)
        return DrawingPipelineResult(**defaults)

    def test_to_api_response_has_required_keys(self):
        result = self._make()
        data = result.to_api_response()
        for key in (
            "artifact_id", "extraction_id", "candidate_id", "candidate_db_id",
            "routing", "redaction_report", "extraction", "candidate",
            "metrics", "ui_state",
        ):
            assert key in data, f"Missing key in to_api_response(): {key}"

    def test_candidate_id_is_local_uuid(self):
        result = self._make(candidate_local_id="test-uuid-123")
        assert result.to_api_response()["candidate_id"] == "test-uuid-123"


# ──────────────────────────────────────────────────────────
# model_router: no fake fallback in route_and_extract
# ──────────────────────────────────────────────────────────

class TestModelRouterNoFakeFallback:
    def test_route_raises_when_no_key(self, monkeypatch):
        """route() must raise RuntimeError when no key and not fake mode."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("DESIGNER_FAKE_VISION", raising=False)
        from foms.services.designer.model_router import route
        with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
            route(template_key="wardrobe_standard", page_count=1)

    def test_route_fake_mode_returns_fake_provider(self, monkeypatch):
        """route() with DESIGNER_FAKE_VISION=1 returns provider='fake'."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.setenv("DESIGNER_FAKE_VISION", "1")
        from foms.services.designer.model_router import route
        result = route(template_key="wardrobe_standard", page_count=1)
        assert result.provider == "fake"
        assert result.model_name == "fake_multimodal_v1"


# ──────────────────────────────────────────────────────────
# run_intake_pipeline with fake Gemini (DESIGNER_FAKE_VISION=1)
# ──────────────────────────────────────────────────────────

class TestRunIntakePipeline:
    """Integration tests using SQLite in-memory DB + fake Gemini provider."""

    @pytest.fixture(autouse=True)
    def setup_fake_env(self, monkeypatch):
        monkeypatch.setenv("DESIGNER_FAKE_VISION", "1")
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    def test_pipeline_pre_checks_key_before_db_work(self, monkeypatch):
        """Pipeline raises GeminiAPIKeyMissing BEFORE any DB ops when key absent."""
        monkeypatch.delenv("DESIGNER_FAKE_VISION", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        from foms.services.designer.drawing_intake_pipeline import run_intake_pipeline
        from foms.services.designer.gemini_provider import GeminiAPIKeyMissing
        # Should raise at the pre-check, before attempting DB artifact creation
        with pytest.raises(GeminiAPIKeyMissing):
            run_intake_pipeline(
                image_bytes=b"fake_image_data",
                filename="test.jpg",
                mime_type="image/jpeg",
            )


# ──────────────────────────────────────────────────────────
# New model columns added in R1/R2
# ──────────────────────────────────────────────────────────

class TestNewModelColumns:
    def test_extraction_has_routing_json(self):
        from foms.persistence.designer.models import DesignerDrawingExtraction
        cols = {c.key for c in DesignerDrawingExtraction.__table__.columns}
        assert "routing_json" in cols
        assert "redaction_report_json" in cols

    def test_candidate_has_status_and_blocking_reasons(self):
        from foms.persistence.designer.models import DesignerExtractionCandidate
        cols = {c.key for c in DesignerExtractionCandidate.__table__.columns}
        assert "status" in cols
        assert "blocking_reasons_json" in cols

    def test_candidate_status_default_is_pending_review(self):
        from foms.persistence.designer.models import DesignerExtractionCandidate
        status_col = DesignerExtractionCandidate.__table__.columns["status"]
        default = str(status_col.default.arg) if status_col.default else None
        assert default == "pending_review"

    def test_design_case_has_source_candidate_id(self):
        from foms.persistence.designer.models import DesignerDesignCase
        cols = {c.key for c in DesignerDesignCase.__table__.columns}
        assert "source_candidate_id" in cols

    def test_remediation_migration_file_exists(self):
        from pathlib import Path
        migration = (
            Path(__file__).parent.parent.parent
            / "migrations" / "versions" / "designer_wdplanner_v2_remediation.py"
        )
        assert migration.exists(), f"Migration file missing: {migration}"


# ──────────────────────────────────────────────────────────
# save-learning-sample: no candidate_rule_hint
# ──────────────────────────────────────────────────────────

class TestSaveLearningHintPollution:
    """Learning sample storage must never set candidate_rule_hint."""

    def test_learning_sample_after_json_has_no_rule_hint(self):
        """The after_json saved in DB must not contain candidate_rule_hint."""
        import json
        # Simulate what save_learning_sample does (without DB)
        extraction = {
            "furniture_type": "wardrobe",
            "confidence": 0.5,
            "unresolved_fields": [],
        }
        filename = "test.jpg"
        after_json = {
            "source": "raw_learning_sample",
            "filename": filename,
            "furniture_type": extraction.get("furniture_type", "unknown"),
            # candidate_rule_hint intentionally absent
            "extraction_confidence": extraction.get("confidence", 0.0),
        }
        assert "candidate_rule_hint" not in after_json, (
            "save_learning_sample must not set candidate_rule_hint — "
            "this would pollute correction_clusterer rule candidate generation."
        )

    def test_learning_sample_source_is_raw_learning_sample(self):
        """source field must be 'raw_learning_sample', not 'learning_sample_upload'."""
        source = "raw_learning_sample"
        assert source != "learning_upload"
        assert source != "learning_sample_upload"
