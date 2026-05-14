"""PG-L3: Product Archetype Learning Tests."""

from __future__ import annotations

import pytest
from foms.services.designer.product_archetype_types import (
    ProductArchetypeCandidate, KNOWN_EXTENDED_ARCHETYPES, ALL_ARCHETYPE_KEYS,
)
from foms.services.designer.product_archetype_learning import (
    extract_tags_from_case, discover_archetypes_from_cases,
    run_archetype_discovery_pipeline, get_archetype_summary, MIN_CASES,
)


class TestArchetypeTypes:
    def test_known_archetypes_not_empty(self):
        assert len(KNOWN_EXTENDED_ARCHETYPES) >= 8

    def test_known_archetypes_have_required_fields(self):
        for key, info in KNOWN_EXTENDED_ARCHETYPES.items():
            assert "label_ko" in info
            assert "base_type" in info
            assert "tags" in info

    def test_known_base_types_valid(self):
        valid = {"wardrobe", "shoe_rack", "kitchen_base", "kitchen_wall", "custom_storage"}
        for key, info in KNOWN_EXTENDED_ARCHETYPES.items():
            assert info["base_type"] in valid, f"{key} has invalid base_type"

    def test_candidate_approved_false_by_default(self):
        c = ProductArchetypeCandidate(
            key="test", label_ko="테스트", base_type="wardrobe",
            supporting_case_ids=[], tag_pattern=[], sample_options={},
        )
        assert c.approved is False
        assert c.auto_generated is True

    def test_can_promote_requires_approval(self):
        c = ProductArchetypeCandidate(
            key="test", label_ko="테스트", base_type="wardrobe",
            supporting_case_ids=[1, 2, 3], tag_pattern=[], sample_options={},
            evidence_count=3, approved=False,
        )
        assert c.can_promote() is False

    def test_can_promote_requires_3_evidence(self):
        c = ProductArchetypeCandidate(
            key="test", label_ko="테스트", base_type="wardrobe",
            supporting_case_ids=[1, 2], tag_pattern=[], sample_options={},
            evidence_count=2, approved=True, auto_generated=False,
        )
        assert c.can_promote() is False

    def test_to_dict_has_required_fields(self):
        c = ProductArchetypeCandidate(
            key="no_molding_wardrobe", label_ko="무몰딩장", base_type="wardrobe",
            supporting_case_ids=[1, 2, 3], tag_pattern=["no_molding"],
            sample_options={}, evidence_count=3, confidence=0.5,
        )
        d = c.to_dict()
        assert d["approved"] is False
        assert d["auto_generated"] is True
        assert "can_promote" in d


class TestTagExtraction:
    def test_extract_no_molding_tag(self):
        case = {"furniture_type": "wardrobe", "product_name": "무몰딩 붙박이장"}
        tags = extract_tags_from_case(case)
        assert "no_molding" in tags

    def test_extract_reform_tag(self):
        case = {"furniture_type": "wardrobe", "product_name": "리폼 붙박이장"}
        tags = extract_tags_from_case(case)
        assert "reform" in tags

    def test_extract_tv_tag(self):
        case = {"furniture_type": "custom_storage", "product_name": "TV 거실장"}
        tags = extract_tags_from_case(case)
        assert "tv" in tags

    def test_extract_from_options(self):
        case = {"furniture_type": "wardrobe", "options_json": {"type": "드레스룸"}}
        tags = extract_tags_from_case(case)
        assert "dressroom" in tags

    def test_existing_tags_preserved(self):
        case = {"furniture_type": "wardrobe", "tags": ["existing_tag"], "product_name": ""}
        tags = extract_tags_from_case(case)
        assert "existing_tag" in tags


class TestArchetypeDiscovery:
    def _make_cases(self, n: int, ft: str, product_name: str, tags: list) -> list[dict]:
        return [
            {"id": i, "furniture_type": ft, "product_name": product_name,
             "tags": tags, "options_json": {}, "width_mm": 2400}
            for i in range(n)
        ]

    def test_below_min_no_candidate(self):
        cases = self._make_cases(2, "wardrobe", "무몰딩 붙박이장", ["no_molding"])
        candidates = discover_archetypes_from_cases(cases, min_count=3)
        assert len(candidates) == 0

    def test_at_min_forms_candidate(self):
        cases = self._make_cases(3, "wardrobe", "무몰딩 붙박이장", ["no_molding"])
        candidates = discover_archetypes_from_cases(cases, min_count=3)
        assert len(candidates) == 1

    def test_candidate_matches_known_archetype(self):
        cases = self._make_cases(4, "wardrobe", "무몰딩장", ["no_molding"])
        candidates = discover_archetypes_from_cases(cases)
        assert candidates[0].key == "no_molding_wardrobe"

    def test_candidate_has_evidence_count(self):
        cases = self._make_cases(5, "wardrobe", "무몰딩 붙박이장", ["no_molding"])
        candidates = discover_archetypes_from_cases(cases)
        assert candidates[0].evidence_count == 5

    def test_candidate_auto_generated_true(self):
        cases = self._make_cases(3, "wardrobe", "무몰딩장", ["no_molding"])
        candidates = discover_archetypes_from_cases(cases)
        assert all(c.auto_generated is True for c in candidates)

    def test_candidate_approved_false(self):
        cases = self._make_cases(3, "wardrobe", "리폼장", ["reform"])
        candidates = discover_archetypes_from_cases(cases)
        assert all(c.approved is False for c in candidates)

    def test_pipeline_returns_empty_when_no_db_cases(self):
        result = run_archetype_discovery_pipeline()
        assert isinstance(result, list)

    def test_get_archetype_summary_has_known(self):
        summary = get_archetype_summary()
        assert "known_extended" in summary
        assert summary["total_known"] >= 8
        assert "no_molding_wardrobe" in summary["known_extended"]
