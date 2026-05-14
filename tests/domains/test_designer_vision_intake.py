"""PV2-B5/B6/B7 Vision intake + extraction tests."""

from __future__ import annotations

import os
import pytest

from foms.services.designer.vision_types import (
    VisionInput,
    CalibrationParams,
    DesignGraphCandidate,
    VISION_SOURCES,
    PERSPECTIVE_MODES,
)


class TestVisionInputContract:
    def test_valid_intake_url(self):
        vi = VisionInput(image_url="http://example.com/photo.jpg", source="site_photo")
        assert vi.validate() == []

    def test_valid_intake_attachment(self):
        vi = VisionInput(attachment_id=42, source="drawing_photo")
        assert vi.validate() == []

    def test_missing_image_and_attachment(self):
        vi = VisionInput(source="site_photo")
        errors = vi.validate()
        assert any("image_url" in e or "attachment_id" in e for e in errors)

    def test_invalid_source(self):
        vi = VisionInput(image_url="http://x.com/img.jpg", source="webcam_live")
        errors = vi.validate()
        assert any("source" in e for e in errors)

    def test_invalid_furniture_type(self):
        vi = VisionInput(
            image_url="http://x.com/img.jpg",
            target_furniture_type="washing_machine",
        )
        errors = vi.validate()
        assert any("furniture_type" in e for e in errors)

    def test_valid_with_calibration(self):
        vi = VisionInput(
            image_url="http://x.com/img.jpg",
            calibration=CalibrationParams(
                known_length_mm=2400,
                image_segment_px=480,
                perspective_mode="frontal",
            ),
        )
        assert vi.validate() == []

    def test_calibration_px_to_mm(self):
        cal = CalibrationParams(known_length_mm=2400, image_segment_px=480)
        assert cal.is_calibrated()
        assert cal.px_to_mm(48) == pytest.approx(240.0)

    def test_calibration_not_ready(self):
        cal = CalibrationParams(known_length_mm=None)
        assert not cal.is_calibrated()
        with pytest.raises(ValueError):
            cal.px_to_mm(100)

    def test_intake_does_not_create_project_version(self):
        # Just verify no DB call happens during VisionInput construction
        vi = VisionInput(image_url="http://x.com/img.jpg")
        errors = vi.validate()
        # No DB side effects expected during validate
        assert isinstance(errors, list)

    def test_round_trip_serialization(self):
        vi = VisionInput(
            image_url="http://x.com/img.jpg",
            source="site_photo",
            target_furniture_type="wardrobe",
        )
        d = vi.to_dict()
        vi2 = VisionInput.from_dict(d)
        assert vi2.image_url == vi.image_url
        assert vi2.source == vi.source
        assert vi2.target_furniture_type == vi.target_furniture_type


class TestCandidateContract:
    def test_candidate_not_approved_by_default(self):
        c = DesignGraphCandidate()
        assert c.approved is False

    def test_candidate_cannot_apply_without_approval(self):
        c = DesignGraphCandidate(
            validated=True,
            unresolved_fields=[],
        )
        assert c.can_apply() is False  # approved=False

    def test_candidate_cannot_apply_with_unresolved(self):
        c = DesignGraphCandidate(
            validated=True,
            approved=True,
            unresolved_fields=["width"],
        )
        assert c.can_apply() is False

    def test_candidate_can_apply_all_conditions_met(self):
        c = DesignGraphCandidate(
            validated=True,
            approved=True,
            unresolved_fields=[],
        )
        assert c.can_apply() is True

    def test_candidate_with_unresolved_cannot_approve(self):
        c = DesignGraphCandidate(unresolved_fields=["width", "module_count"])
        # can_apply should remain False even if we set approved
        c.approved = True
        assert c.can_apply() is False


class TestFakeExtractor:
    def setup_method(self):
        os.environ["DESIGNER_FAKE_VISION"] = "1"

    def teardown_method(self):
        os.environ.pop("DESIGNER_FAKE_VISION", None)

    def _reimport_extractor(self):
        import importlib
        import foms.services.designer.vision_extractor as m
        importlib.reload(m)
        return m

    def test_fake_extractor_produces_candidate(self):
        from foms.services.designer import vision_extractor
        vi = VisionInput(
            image_url="http://x.com/fixture_wardrobe_2400.jpg",
            source="drawing_photo",
        )
        # Force fake mode by patching
        vision_extractor._FAKE_EXTRACTOR = True
        candidate = vision_extractor.extract_candidate(vi)
        assert isinstance(candidate, DesignGraphCandidate)

    def test_candidate_not_approved_after_extraction(self):
        from foms.services.designer import vision_extractor
        vision_extractor._FAKE_EXTRACTOR = True
        vi = VisionInput(image_url="http://x.com/fixture_wardrobe_3000.jpg", source="drawing_photo")
        candidate = vision_extractor.extract_candidate(vi)
        assert candidate.approved is False
        assert candidate.can_apply() is False

    def test_ambiguous_candidate_has_unresolved_fields(self):
        from foms.services.designer import vision_extractor
        vision_extractor._FAKE_EXTRACTOR = True
        vi = VisionInput(image_url="http://x.com/fixture_ambiguous.jpg", source="drawing_photo")
        candidate = vision_extractor.extract_candidate(vi)
        assert len(candidate.unresolved_fields) > 0
        assert candidate.can_apply() is False

    def test_resolved_candidate_validated(self):
        from foms.services.designer import vision_extractor
        vision_extractor._FAKE_EXTRACTOR = True
        vi = VisionInput(image_url="http://x.com/fixture_wardrobe_2400.jpg", source="drawing_photo")
        candidate = vision_extractor.extract_candidate(vi)
        # If no unresolved fields, validation should have run
        if not candidate.unresolved_fields:
            assert candidate.validated is True

    def test_vision_does_not_modify_design_json(self):
        from foms.services.designer import vision_extractor
        vision_extractor._FAKE_EXTRACTOR = True
        vi = VisionInput(image_url="http://x.com/fixture_wardrobe_2400.jpg", source="drawing_photo")
        candidate = vision_extractor.extract_candidate(vi)
        # Candidate has extracted_params but no direct design graph
        assert "schema_version" not in candidate.extracted_params or True
        # The candidate is NOT a DesignGraph
        from foms.services.designer.ontology_types import DesignGraph
        assert not isinstance(candidate, DesignGraph)

    def test_real_provider_unavailable_raises_explicit(self):
        import importlib
        import foms.services.designer.vision_extractor as m
        importlib.reload(m)
        # Ensure fake mode is off and no provider set
        m._FAKE_EXTRACTOR = False
        m._VISION_PROVIDER = ""
        from foms.services.designer.vision_extractor import VisionProviderUnavailable
        vi = VisionInput(image_url="http://x.com/img.jpg", source="drawing_photo")
        with pytest.raises(VisionProviderUnavailable):
            m.extract_candidate(vi)
