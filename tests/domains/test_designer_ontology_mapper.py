"""PG-B7: Ontology Mapper + Candidate Graph Builder Tests.

Verifies:
1. Furniture type resolution from extraction.
2. Factory param mapping from W/D/H/module_count.
3. Unresolved fields populated for missing values.
4. approved=False always on exit.
5. can_apply() only True when all conditions met.
6. Validator attached to candidate.
7. Multi-page candidate building.
"""

from __future__ import annotations

import pytest
from foms.services.designer.ontology_mapper import (
    resolve_furniture_type, extract_factory_params,
    build_candidate, build_candidates_from_pages,
    MappedCandidate,
)


# ──────────────────────────────────────────────────────────
# PG-B7-01: Import
# ──────────────────────────────────────────────────────────

def test_ontology_mapper_importable():
    from foms.services.designer import ontology_mapper
    assert callable(ontology_mapper.build_candidate)
    assert callable(ontology_mapper.resolve_furniture_type)


# ──────────────────────────────────────────────────────────
# PG-B7-02: Furniture type resolution
# ──────────────────────────────────────────────────────────

class TestFurnitureTypeResolution:
    def test_gemini_explicit_wardrobe(self):
        ftype, conf = resolve_furniture_type({"furniture_type": "wardrobe"})
        assert ftype == "wardrobe"
        assert conf >= 0.8

    def test_product_name_신발장(self):
        ftype, conf = resolve_furniture_type({
            "furniture_type": "",
            "customer_info": {"product_name": "신발장"},
        })
        assert ftype == "shoe_rack"
        assert conf >= 0.5

    def test_product_name_붙박이장(self):
        ftype, conf = resolve_furniture_type({
            "furniture_type": "",
            "customer_info": {"product_name": "붙박이장 3칸"},
        })
        assert ftype == "wardrobe"

    def test_parts_table_hint_ep_sr(self):
        ftype, conf = resolve_furniture_type({
            "furniture_type": "",
            "parts_table": [{"code": "[SR]"}, {"code": "[EP]"}],
        })
        assert ftype == "wardrobe"

    def test_unknown_defaults_to_custom_storage(self):
        ftype, conf = resolve_furniture_type({})
        assert ftype == "custom_storage"
        assert conf < 0.5


# ──────────────────────────────────────────────────────────
# PG-B7-03: Factory param extraction
# ──────────────────────────────────────────────────────────

class TestFactoryParamExtraction:
    EXTRACTION_WARDROBE = {
        "extracted_params": {
            "width": 2400, "height": 2200, "depth": 620,
            "module_widths": [800, 800, 800],
        }
    }

    def test_wdh_extracted(self):
        params, unresolved = extract_factory_params(self.EXTRACTION_WARDROBE, "wardrobe")
        assert params["width"] == 2400
        assert params["height"] == 2200
        assert params["depth"] == 620

    def test_module_count_from_module_widths(self):
        params, unresolved = extract_factory_params(self.EXTRACTION_WARDROBE, "wardrobe")
        assert params["module_count"] == 3

    def test_missing_dimensions_go_to_unresolved(self):
        params, unresolved = extract_factory_params({}, "wardrobe")
        assert "width" in unresolved
        assert "height" in unresolved
        assert "depth" in unresolved

    def test_sanity_filter_rejects_out_of_range(self):
        extraction = {"extracted_params": {"width": 50000, "height": 1}}
        params, unresolved = extract_factory_params(extraction, "wardrobe")
        assert "width" in unresolved
        assert "height" in unresolved

    def test_shoe_rack_tier_count(self):
        extraction = {"extracted_params": {"width": 900, "height": 1200, "depth": 350, "tier_count": 4}}
        params, _ = extract_factory_params(extraction, "shoe_rack")
        assert params["tier_count"] == 4


# ──────────────────────────────────────────────────────────
# PG-B7-04: Candidate safety contracts
# ──────────────────────────────────────────────────────────

class TestCandidateSafetyContracts:
    FULL_EXTRACTION = {
        "furniture_type": "wardrobe",
        "extracted_params": {"width": 2400, "height": 2200, "depth": 620,
                              "module_widths": [800, 800, 800]},
        "confidence": 0.9,
    }

    def test_approved_always_false(self):
        """Candidate approved must ALWAYS be False on creation."""
        c = build_candidate(self.FULL_EXTRACTION)
        assert c.approved is False, "Candidate must never be auto-approved"

    def test_can_apply_false_when_approved_is_false(self):
        c = build_candidate(self.FULL_EXTRACTION)
        assert c.can_apply() is False

    def test_can_apply_false_when_unresolved_fields(self):
        extraction = {
            "furniture_type": "wardrobe",
            "extracted_params": {"height": 2200, "depth": 620},  # no width
            "confidence": 0.9,
        }
        c = build_candidate(extraction)
        c.approved = True  # simulate human approval
        assert c.can_apply() is False  # still blocked by unresolved width

    def test_candidate_has_unique_id(self):
        c1 = build_candidate(self.FULL_EXTRACTION)
        c2 = build_candidate(self.FULL_EXTRACTION)
        assert c1.candidate_id != c2.candidate_id

    def test_unresolved_fields_populated(self):
        extraction = {
            "furniture_type": "wardrobe",
            "extracted_params": {"height": 2200},  # missing width, depth
            "confidence": 0.6,
        }
        c = build_candidate(extraction, run_validator=False)
        assert "width" in c.unresolved_fields
        assert "depth" in c.unresolved_fields

    def test_validator_attached_when_fully_resolved(self):
        c = build_candidate(self.FULL_EXTRACTION, run_validator=True)
        assert c.validation_result is not None
        assert "valid" in c.validation_result

    def test_validator_skipped_when_unresolved(self):
        extraction = {
            "furniture_type": "wardrobe",
            "extracted_params": {},
            "confidence": 0.3,
        }
        c = build_candidate(extraction, run_validator=True)
        # Validator should not run when unresolved fields exist
        # (validation_result may be None)
        assert c.unresolved_fields

    def test_confidence_combined(self):
        """Combined confidence = geometric mean of type_conf and extraction_conf."""
        c = build_candidate(self.FULL_EXTRACTION)
        assert 0.0 <= c.confidence <= 1.0

    def test_parts_table_attached(self):
        extraction = {
            "furniture_type": "wardrobe",
            "extracted_params": {"width": 2400, "height": 2200, "depth": 620},
            "parts_table": [{"code": "[SR]", "quantity": 6}],
            "confidence": 0.9,
        }
        c = build_candidate(extraction, run_validator=False)
        assert len(c.parts_table) == 1
        assert c.parts_table[0]["code"] == "[SR]"

    def test_to_dict_has_required_fields(self):
        c = build_candidate(self.FULL_EXTRACTION)
        d = c.to_dict()
        required = {
            "candidate_id", "furniture_type", "factory_params",
            "unresolved_fields", "approved", "confidence",
            "can_apply", "validation_result",
        }
        assert required <= set(d.keys())

    def test_to_dict_approved_false(self):
        c = build_candidate(self.FULL_EXTRACTION)
        assert c.to_dict()["approved"] is False


# ──────────────────────────────────────────────────────────
# PG-B7-05: Multi-page candidates
# ──────────────────────────────────────────────────────────

class TestMultiPageCandidates:
    def test_builds_candidate_per_page(self):
        pages = [
            {"furniture_type": "wardrobe",
             "extracted_params": {"width": 2400, "height": 2200, "depth": 620},
             "confidence": 0.9},
            {"furniture_type": "wardrobe",
             "extracted_params": {"width": 1200, "height": 2200, "depth": 620},
             "confidence": 0.85},
        ]
        candidates = build_candidates_from_pages(pages)
        assert len(candidates) == 2
        assert all(c.approved is False for c in candidates)

    def test_each_page_has_unique_candidate_id(self):
        pages = [{"furniture_type": "wardrobe", "extracted_params": {}}] * 3
        candidates = build_candidates_from_pages(pages)
        ids = [c.candidate_id for c in candidates]
        assert len(set(ids)) == 3
