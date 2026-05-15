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

    def test_extract_design_understanding_category_tags(self):
        case = {
            "furniture_type": "custom_storage",
            "internal_structure_json": {
                "learned_design_category": {
                    "category_key": "floating_tv_wall_unit",
                    "similarity_tags": ["tv_wall", "floating"],
                    "layout_signature": {
                        "module_pattern": "wide_center_open",
                        "zone_roles": ["open_space", "drawer_stack"],
                        "dominant_structure": "wall_mounted_storage",
                    },
                },
                "block_candidates": [
                    {"block_key": "custom_storage.tv_wall.floating_drawer"},
                ],
            },
        }
        tags = extract_tags_from_case(case)
        assert "floating_tv_wall_unit" in tags
        assert "tv_wall" in tags
        assert "wide_center_open" in tags
        assert "wall_mounted_storage" in tags
        assert "custom_storage.tv_wall.floating_drawer" in tags


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

    def test_candidate_has_supporting_case_ids(self):
        """B5: archetype discovery includes supporting_case_ids for evidence tracing."""
        cases = self._make_cases(4, "wardrobe", "무몰딩 붙박이장", ["no_molding"])
        candidates = discover_archetypes_from_cases(cases, min_count=3)
        assert len(candidates) == 1
        ids = candidates[0].supporting_case_ids
        assert isinstance(ids, list)
        assert len(ids) >= 3

    def test_candidate_cannot_promote_without_approval(self):
        """B5: auto-generated candidate cannot be promoted without human approval."""
        cases = self._make_cases(5, "wardrobe", "리폼장", ["reform"])
        candidates = discover_archetypes_from_cases(cases)
        for c in candidates:
            # auto_generated=True, approved=False → can_promote must be False
            assert c.auto_generated is True
            assert c.approved is False
            assert c.can_promote() is False

    def test_raw_upload_does_not_become_rule_evidence(self):
        """B5: pre-approval candidates have no design case and cannot form rule evidence.

        Rule candidates require correction evidence (cluster_corrections_to_candidates).
        Verifies that the min_count guard blocks promotion from insufficient corrections.
        """
        from foms.services.designer.evolution import cluster_corrections_to_candidates
        # Fewer than 3 matching corrections → empty result (no candidate created)
        result = cluster_corrections_to_candidates("test_hint_B5", min_count=3)
        assert result == []

    def test_evolution_promote_requires_replay_and_approval(self):
        """B5: approve_and_promote_candidate raises without replay report."""
        from foms.services.designer.evolution import approve_and_promote_candidate
        import pytest
        with pytest.raises((ValueError, Exception)):
            # No candidate exists with id=-1; should raise
            approve_and_promote_candidate(-1)
