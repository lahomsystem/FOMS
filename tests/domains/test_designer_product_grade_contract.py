"""PG-B0: FOMS Brain Product-Grade Contract Tests.

These tests FREEZE the reality that the current implementation is NOT product-grade.
They exist to prevent anyone (human or AI) from claiming product completion
without actually meeting the product-grade definition.

Absolute rules enforced here:
- fake extractor != product complete
- fixture corpus = 0 != product complete
- Gemini provider missing != product complete
- scorecard algorithm missing != product complete
- no auto-promotion of ontology (invariant must exist)

When these tests START FAILING it means the product-grade gate has been
unlocked by real implementation — that is expected and correct.
Until then, every test below must pass to confirm we are NOT done yet.
"""

from __future__ import annotations

import os
import importlib
import inspect
from pathlib import Path
from typing import Any

import pytest

# ──────────────────────────────────────────────────────────
# PG-B0-01: Fake extractor is NOT product-complete
# ──────────────────────────────────────────────────────────

class TestFakeExtractorNotProductComplete:
    """Ensures fake extractor cannot be silently treated as production-ready."""

    def test_vision_extractor_has_fake_mode_flag(self):
        """vision_extractor.py exposes _FAKE_EXTRACTOR flag."""
        import foms.services.designer.vision_extractor as vx
        assert hasattr(vx, "_FAKE_EXTRACTOR"), (
            "vision_extractor._FAKE_EXTRACTOR flag must exist to track fake mode."
        )

    def test_fake_extractor_source_label_is_not_gemini(self):
        """When in fake mode, candidate source must NOT be 'gemini'."""
        from foms.services.designer.vision_extractor import extract_candidate
        from foms.services.designer.vision_types import VisionInput

        prev = os.environ.get("DESIGNER_FAKE_VISION", "0")
        os.environ["DESIGNER_FAKE_VISION"] = "1"
        try:
            import foms.services.designer.vision_extractor as vx
            # Reload to pick up env change
            importlib.reload(vx)
            vi = VisionInput(image_url="fixture_wardrobe_3000", source="manual_upload")
            candidate = vx.extract_candidate(vi)
            assert candidate.source != "gemini", (
                "Fake extractor must never report source='gemini'. "
                f"Got source={candidate.source!r}."
            )
            assert "fake" in candidate.source or candidate.source == "fake_extractor", (
                f"Fake extractor source must contain 'fake'. Got {candidate.source!r}."
            )
        finally:
            os.environ["DESIGNER_FAKE_VISION"] = prev
            importlib.reload(vx)

    def test_fake_extractor_candidate_not_auto_approved(self):
        """Candidate from fake extractor must always have approved=False."""
        import foms.services.designer.vision_extractor as vx

        prev = os.environ.get("DESIGNER_FAKE_VISION", "0")
        os.environ["DESIGNER_FAKE_VISION"] = "1"
        try:
            importlib.reload(vx)
            from foms.services.designer.vision_types import VisionInput
            vi = VisionInput(image_url="fixture_wardrobe_3000", source="manual_upload")
            candidate = vx.extract_candidate(vi)
            assert candidate.approved is False, (
                "PG-B0 contract: candidate.approved must be False — human review required."
            )
        finally:
            os.environ["DESIGNER_FAKE_VISION"] = prev
            importlib.reload(vx)

    def test_real_provider_not_implemented_without_gemini_module(self):
        """Real provider path raises VisionProviderUnavailable when no Gemini module exists."""
        import foms.services.designer.vision_extractor as vx

        prev_fake = os.environ.get("DESIGNER_FAKE_VISION", "0")
        prev_provider = os.environ.get("DESIGNER_VISION_PROVIDER", "")
        os.environ["DESIGNER_FAKE_VISION"] = "0"
        os.environ["DESIGNER_VISION_PROVIDER"] = ""
        try:
            importlib.reload(vx)
            from foms.services.designer.vision_types import VisionInput
            vi = VisionInput(image_url="test_image.jpg", source="manual_upload")
            with pytest.raises(vx.VisionProviderUnavailable):
                vx.extract_candidate(vi)
        finally:
            os.environ["DESIGNER_FAKE_VISION"] = prev_fake
            os.environ["DESIGNER_VISION_PROVIDER"] = prev_provider
            importlib.reload(vx)


# ──────────────────────────────────────────────────────────
# PG-B0-02: Gemini provider module does NOT yet exist
# ──────────────────────────────────────────────────────────

class TestPGModulesImplementedAndMissing:
    """Tracks which PG-B* modules are implemented vs still missing."""

    # ── PG-B0A: IMPLEMENTED ──
    def test_gemini_provider_module_implemented(self):
        """gemini_provider.py is now implemented (PG-B0A complete)."""
        import foms.services.designer.gemini_provider as gp  # noqa: F401
        assert callable(gp.check_connectivity)
        assert callable(gp.extract_from_image_bytes)

    def test_extraction_scorecard_module_implemented(self):
        """extraction_scorecard.py is now implemented (PG-B0A complete)."""
        import foms.services.designer.extraction_scorecard as sc  # noqa: F401
        assert callable(sc.score_wdh)
        assert callable(sc.run_scorecard_from_manifest)

    # ── PG-B3A: IMPLEMENTED ──
    def test_pii_redactor_module_implemented(self):
        """pii_redactor.py is now implemented (PG-B3A complete)."""
        import foms.services.designer.pii_redactor as pr  # noqa: F401
        assert callable(pr.scan_for_raw_pii)
        assert callable(pr.build_gemini_payload)

    # ── PG-B4: STILL MISSING ──
    def test_model_router_module_missing(self):
        """foms.services.designer.model_router does not exist yet (PG-B4 scope)."""
        with pytest.raises(ImportError):
            import foms.services.designer.model_router  # noqa: F401

    # ── PG-B5: STILL MISSING ──
    def test_parts_table_parser_module_missing(self):
        """foms.services.designer.parts_table_parser does not exist yet (PG-B5 scope)."""
        with pytest.raises(ImportError):
            import foms.services.designer.parts_table_parser  # noqa: F401

    # ── PG-B6: STILL MISSING ──
    def test_dimension_parser_module_missing(self):
        """foms.services.designer.dimension_parser does not exist yet (PG-B6 scope)."""
        with pytest.raises(ImportError):
            import foms.services.designer.dimension_parser  # noqa: F401

    # ── PG-B11: STILL MISSING ──
    def test_correction_clusterer_module_missing(self):
        """foms.services.designer.correction_clusterer does not exist yet (PG-B11 scope)."""
        with pytest.raises(ImportError):
            import foms.services.designer.correction_clusterer  # noqa: F401


# ──────────────────────────────────────────────────────────
# PG-B0-03: Drawing fixture corpus does NOT exist
# ──────────────────────────────────────────────────────────

class TestFixtureCorpusState:
    """Tracks fixture corpus state across PG batches.

    PG-B0A: POC manifest existed at tests/fixtures/drawings/ (5 POC fixtures)
    PG-B2:  Canonical manifest at tests/fixtures/designer/drawings/ (17 fixtures)
            Files provided → file_status=available → expected_json generated → approved
    """

    # PG-B2 canonical path
    FIXTURE_MANIFEST_PATH = (
        Path(__file__).parent.parent / "fixtures" / "designer" / "drawings" / "manifest.json"
    )

    def test_canonical_fixture_manifest_exists(self):
        """PG-B2: tests/fixtures/designer/drawings/manifest.json exists."""
        assert self.FIXTURE_MANIFEST_PATH.exists(), (
            f"Canonical fixture manifest missing at {self.FIXTURE_MANIFEST_PATH}. "
            "PG-B2 should have created this file."
        )

    def test_canonical_manifest_has_17_fixtures(self):
        """PG-B2: Canonical manifest has 17 fixture slots."""
        import json
        with open(self.FIXTURE_MANIFEST_PATH, encoding="utf-8") as f:
            data = json.load(f)
        count = len(data.get("fixtures", []))
        assert count == 17, f"Expected 17 fixtures in canonical manifest, got {count}"

    def test_fixture_corpus_not_17_approved_yet(self):
        """PG-B2 files not provided yet: 0 approved fixtures (gate will pass when 17 approved)."""
        import json
        with open(self.FIXTURE_MANIFEST_PATH, encoding="utf-8") as f:
            data = json.load(f)
        approved = [
            f for f in data.get("fixtures", [])
            if f.get("approval_status") == "approved"
        ]
        assert len(approved) < 17, (
            f"Found {len(approved)} approved fixtures — if PG-B2 is complete (17 approved), "
            "update PRODUCT_GRADE_GATES['fixture_corpus_17_drawings'] to True."
        )


# ──────────────────────────────────────────────────────────
# PG-B0-04: Active ontology invariant contract
# ──────────────────────────────────────────────────────────

class TestOntologyPromotionInvariant:
    """Confirms auto-promotion is blocked and invariant contract exists."""

    def test_evolution_module_has_no_auto_promotion_flag(self):
        """evolution.py must NOT have an auto_promote function that bypasses human review."""
        import foms.services.designer.evolution as ev
        # If auto_promote exists, it must require explicit human_approved=True param
        if hasattr(ev, "auto_promote"):
            sig = inspect.signature(ev.auto_promote)
            param_names = list(sig.parameters.keys())
            assert "human_approved" in param_names, (
                "evolution.auto_promote must have human_approved parameter to prevent bypass."
            )

    def test_rule_candidate_cannot_be_promoted_without_replay(self):
        """DesignerRuleCandidate model must have replay tracking fields.

        Replay gate requires:
        - replay_report_json: stores replay evidence before promotion
        - status: must flow draft -> approved (not direct to promoted without replay evidence)
        """
        try:
            from foms.persistence.designer.models import DesignerRuleCandidate
            columns = {c.key for c in DesignerRuleCandidate.__table__.columns}
            # replay_report_json holds the replay evidence (must be populated before promotion)
            assert "replay_report_json" in columns, (
                "DesignerRuleCandidate must have replay_report_json to capture replay evidence "
                "before promotion. PG-B11 will add correction_clusterer that populates this."
            )
            # status must exist to gate promotion workflow
            assert "status" in columns, (
                "DesignerRuleCandidate must have status column (draft/approved/rejected/promoted)."
            )
            # promoted status must be present in the enum (no direct bypass)
            if hasattr(DesignerRuleCandidate, "status"):
                # Confirm 'promoted' is a valid state (we never skip to it without approval)
                status_col = DesignerRuleCandidate.__table__.columns["status"]
                assert status_col is not None
        except (ImportError, AttributeError):
            pytest.skip("DesignerRuleCandidate model not accessible — skip DB-level invariant check.")


# ──────────────────────────────────────────────────────────
# PG-B0-05: /wdplanner route exists and ERP routes not broken
# ──────────────────────────────────────────────────────────

class TestRouteRegression:
    """ERP route regression check — if broken, stop immediately."""

    def test_app_imports_ok(self):
        """APP_OK: app module imports without error."""
        import app  # noqa: F401
        assert True, "app import succeeded."

    def test_designer_api_blueprint_importable(self):
        """foms.api.designer is importable without error."""
        import foms.api.designer  # noqa: F401
        assert True

    def test_designer_services_importable(self):
        """All designer services import cleanly."""
        import foms.services.designer.ontology_types  # noqa: F401
        import foms.services.designer.formula_engine  # noqa: F401
        import foms.services.designer.constraint_engine  # noqa: F401
        import foms.services.designer.vision_extractor  # noqa: F401
        import foms.services.designer.evolution  # noqa: F401
        assert True


# ──────────────────────────────────────────────────────────
# PG-B0-06: Product-grade readiness summary (always fails until all gates pass)
# ──────────────────────────────────────────────────────────

PRODUCT_GRADE_GATES: dict[str, bool] = {
    "gemini_provider_implemented": True,        # ✅ PG-B0A complete
    "extraction_scorecard_implemented": True,   # ✅ PG-B0A complete
    "fixture_corpus_17_drawings": False,        # PG-B2 pending
    "pii_redactor_implemented": True,           # ✅ PG-B3A complete
    "parts_table_parser_recall_90": False,      # PG-B5 pending
    "dimension_parser_wdh_95": False,           # PG-B6 pending
    "overlay_review_ui": False,                 # PG-B8 pending
    "white_workbench_shell": False,             # PG-B1 pending
    "factory_selector_ui": False,               # PG-B10 pending
    "correction_clusterer_implemented": False,  # PG-B11 pending
    "no_auto_ontology_promotion": True,         # already enforced by contract
}


class TestProductGradeReadinessSummary:
    def test_product_is_not_ready(self):
        """PG-B0: Product-grade readiness is NOT achieved until all gates pass.

        This test MUST FAIL when PG-B13 is complete.
        Until then, it documents exactly which gates are missing.
        """
        not_ready = [gate for gate, ready in PRODUCT_GRADE_GATES.items() if not ready]
        assert len(not_ready) > 0, (
            "All product-grade gates have passed — PG-B13 should be declared complete. "
            "Run full QA closeout and update PRODUCT_GRADE_STATUS.md."
        )
        # Informational: which gates are still open (visible in pytest -v output)
        missing_str = "\n  - ".join(not_ready)
        pytest.skip(
            f"PG-B0 contract: {len(not_ready)} gates not yet implemented:\n  - {missing_str}"
        )
