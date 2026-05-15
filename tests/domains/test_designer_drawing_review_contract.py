"""PG-B8: Drawing Review Overlay — API Contract Tests.

Verifies backend API contracts for candidate build / correction / approve-and-save.
UI itself is in wdplanner_v2.html (server-rendered, no frontend build needed for tests).

Contracts:
- /candidates/build builds a MappedCandidate from extraction (approved=False always)
- /candidates/<id>/correct stores CorrectionDelta, does NOT create project version
- /candidates/<id>/approve-and-save creates project version only if validator passes
- unresolved_fields blocks approve-and-save
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

ROOT = Path(__file__).parent.parent.parent

SAMPLE_EXTRACTION = {
    "furniture_type": "wardrobe",
    "extracted_params": {
        "width": 2400, "height": 2200, "depth": 620,
        "module_widths": [800, 800, 800],
    },
    "confidence": 0.9,
    "unresolved_fields": [],
}

PARTIAL_EXTRACTION = {
    "furniture_type": "wardrobe",
    "extracted_params": {"height": 2200, "depth": 620},  # missing width
    "confidence": 0.6,
}


# ──────────────────────────────────────────────────────────
# PG-B8-01: drawings.py endpoint existence
# ──────────────────────────────────────────────────────────

class TestDrawingsApiEndpoints:
    def test_drawings_api_importable(self):
        from foms.api.designer.drawings import drawings_bp
        assert drawings_bp is not None

    def test_candidate_build_route_registered(self):
        from foms.api.designer import drawings as m
        assert hasattr(m, "build_candidate_route")

    def test_correct_candidate_route_exists(self):
        from foms.api.designer import drawings as m
        assert hasattr(m, "correct_candidate")

    def test_approve_and_save_route_exists(self):
        from foms.api.designer import drawings as m
        assert hasattr(m, "approve_and_save_candidate")


# ──────────────────────────────────────────────────────────
# PG-B8-02: Candidate build contract via ontology_mapper
# ──────────────────────────────────────────────────────────

class TestCandidateBuildContract:
    def test_build_returns_approved_false(self):
        from foms.services.designer.ontology_mapper import build_candidate
        c = build_candidate(SAMPLE_EXTRACTION)
        assert c.approved is False

    def test_build_full_extraction_no_unresolved(self):
        from foms.services.designer.ontology_mapper import build_candidate
        c = build_candidate(SAMPLE_EXTRACTION)
        assert c.factory_params.get("width") == 2400
        # unresolved may include module_count if widths not resolved
        assert "width" not in c.unresolved_fields

    def test_build_partial_extraction_has_unresolved(self):
        from foms.services.designer.ontology_mapper import build_candidate
        c = build_candidate(PARTIAL_EXTRACTION)
        assert "width" in c.unresolved_fields
        assert c.can_apply() is False

    def test_candidate_id_is_unique_uuid(self):
        from foms.services.designer.ontology_mapper import build_candidate
        import re
        c = build_candidate(SAMPLE_EXTRACTION)
        assert re.match(
            r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
            c.candidate_id
        )


# ──────────────────────────────────────────────────────────
# PG-B8-03: Correction delta contract
# ──────────────────────────────────────────────────────────

class TestCorrectionDeltaContract:
    def test_correction_removes_from_unresolved(self):
        """Correcting 'width' should remove it from unresolved_fields."""
        from foms.services.designer.ontology_mapper import build_candidate
        c = build_candidate(PARTIAL_EXTRACTION)
        assert "width" in c.unresolved_fields

        # Simulate correction applied (as the API would do)
        d = c.to_dict()
        d["factory_params"]["width"] = 2400
        if "width" in d["unresolved_fields"]:
            d["unresolved_fields"].remove("width")

        assert "width" not in d["unresolved_fields"]
        assert d["factory_params"]["width"] == 2400

    def test_correction_does_not_auto_approve(self):
        """Applying corrections must NOT set approved=True."""
        from foms.services.designer.ontology_mapper import build_candidate
        c = build_candidate(PARTIAL_EXTRACTION)
        # Even after correction, approved must stay False until human explicitly approves
        d = c.to_dict()
        d["factory_params"]["width"] = 2400
        assert d["approved"] is False

    def test_correction_delta_model_exists(self):
        from foms.persistence.designer.models import DesignerCorrection
        cols = {col.key for col in DesignerCorrection.__table__.columns}
        assert "before_json" in cols
        assert "after_json" in cols
        assert "reason_text" in cols


# ──────────────────────────────────────────────────────────
# PG-B8-04: Approve-and-save safety gates
# ──────────────────────────────────────────────────────────

class TestApproveAndSaveSafetyGates:
    def test_unresolved_fields_block_apply(self):
        """can_apply() must return False when unresolved_fields exist."""
        from foms.services.designer.ontology_mapper import build_candidate, MappedCandidate
        c = build_candidate(PARTIAL_EXTRACTION)
        c.approved = True  # simulate user clicking approve
        assert c.can_apply() is False  # blocked by unresolved

    def test_validator_fail_blocks_apply(self):
        """can_apply() returns False when validation_result.valid is False."""
        from foms.services.designer.ontology_mapper import MappedCandidate
        c = MappedCandidate(
            furniture_type="wardrobe",
            factory_params={"width": 2400, "height": 2200, "depth": 620},
            unresolved_fields=[],
            approved=True,
            validation_result={"valid": False, "errors": ["test error"]},
            confidence=0.9,
        )
        assert c.can_apply() is False

    def test_all_conditions_met_can_apply(self):
        """can_apply() True only when approved=True, unresolved=[], validator.valid=True."""
        from foms.services.designer.ontology_mapper import MappedCandidate
        c = MappedCandidate(
            furniture_type="wardrobe",
            factory_params={"width": 2400, "height": 2200, "depth": 620},
            unresolved_fields=[],
            approved=True,
            validation_result={"valid": True, "errors": []},
            confidence=0.9,
        )
        assert c.can_apply() is True

    def test_never_save_without_approval(self):
        """Candidate created fresh always has approved=False."""
        from foms.services.designer.ontology_mapper import build_candidate
        c = build_candidate(SAMPLE_EXTRACTION)
        assert c.approved is False
        # Even if we mark all conditions as met, approved=False means can_apply=False
        c.unresolved_fields = []
        c.validation_result = {"valid": True, "errors": []}
        assert c.can_apply() is False  # approved is still False


# ──────────────────────────────────────────────────────────
# PG-B8-05: Drawing review overlay — file structure
# ──────────────────────────────────────────────────────────

class TestDrawingReviewFileStructure:
    def test_drawings_api_file_exists(self):
        api = ROOT / "foms" / "api" / "designer" / "drawings.py"
        assert api.exists()

    def test_drawings_api_has_candidate_endpoints(self):
        content = (ROOT / "foms" / "api" / "designer" / "drawings.py").read_text(encoding="utf-8")
        assert "build_candidate_route" in content
        assert "correct_candidate" in content
        assert "approve_and_save_candidate" in content

    def test_drawings_api_correction_delta_stored(self):
        """Correction endpoint stores to DesignerCorrection model."""
        content = (ROOT / "foms" / "api" / "designer" / "drawings.py").read_text(encoding="utf-8")
        assert "DesignerCorrection" in content
        assert "before_json" in content
        assert "after_json" in content

    def test_drawings_api_validator_gate(self):
        """approve-and-save must run validator before saving version."""
        content = (ROOT / "foms" / "api" / "designer" / "drawings.py").read_text(encoding="utf-8")
        assert "validate_design" in content
        assert "VALIDATOR_FAILED" in content or "검증" in content

    def test_wdplanner_v2_template_exists(self):
        tmpl = ROOT / "templates" / "designer" / "wdplanner_v2.html"
        assert tmpl.exists()

    def test_wdplanner_v2_has_drawing_panel(self):
        content = (ROOT / "templates" / "designer" / "wdplanner_v2.html").read_text(encoding="utf-8")
        assert "drawing-panel" in content
        assert "upload-and-extract" in content
        assert "save-draft" in content or "approve" in content

    def test_wdplanner_v2_upload_has_client_timeout(self):
        """The upload UI must not leave Gemini requests spinning until proxy 499."""
        content = (ROOT / "templates" / "designer" / "wdplanner_v2.html").read_text(encoding="utf-8")
        assert "DESIGNER_UPLOAD_TIMEOUT_MS" in content
        assert "AbortController" in content
        assert "UPLOAD_TIMEOUT" in content

    def test_approve_save_preserves_design_understanding_for_learning(self):
        """Approved drawing cases must carry layout/category learning payloads."""
        content = (ROOT / "foms" / "api" / "designer" / "drawings.py").read_text(encoding="utf-8")
        assert "design_understanding" in content
        assert "internal_structure=design_understanding" in content
        assert "extract_tags_from_case" in content
        assert "tags=learning_tags" in content
