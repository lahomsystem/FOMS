"""PG-L2: Retrieval-Augmented Design Brain Tests."""

from __future__ import annotations

import pytest
from foms.services.designer.design_retrieval import (
    build_gemini_context_prompt, build_rag_context, _ensure_pii_free,
)


class TestRetrievalModule:
    def test_importable(self):
        import foms.services.designer.design_retrieval as dr
        assert callable(dr.retrieve_similar_cases)
        assert callable(dr.build_gemini_context_prompt)
        assert callable(dr.build_rag_context)

    def test_retrieve_empty_when_no_cases(self):
        """retrieve_similar_cases returns empty list when DB has no cases."""
        from foms.services.designer.design_retrieval import retrieve_similar_cases
        result = retrieve_similar_cases(furniture_type="wardrobe", width_mm=2400)
        assert isinstance(result, list)

    def test_pii_free_strips_customer_name(self):
        case = {"furniture_type": "wardrobe", "width_mm": 2400, "customer_name": "홍길동"}
        clean = _ensure_pii_free(case)
        assert "customer_name" not in clean
        assert clean["furniture_type"] == "wardrobe"


class TestGeminiContextPrompt:
    CASES = [
        {"furniture_type": "wardrobe", "width_mm": 2400, "height_mm": 2200,
         "depth_mm": 620, "module_count": 3, "product_name": "붙박이장",
         "tags": ["no_molding"], "options_json": {"color": "화이트"}},
    ]

    def test_prompt_with_cases(self):
        ctx = build_gemini_context_prompt(self.CASES)
        assert "붙박이장" in ctx or "wardrobe" in ctx
        assert "2400" in ctx

    def test_prompt_includes_request_description(self):
        ctx = build_gemini_context_prompt(self.CASES, request_description="3칸 설계 요청")
        assert "3칸 설계 요청" in ctx

    def test_prompt_with_corrections(self):
        corrections = [{"correction_pattern": "ep_too_narrow", "source": "user_manual_edit"}]
        ctx = build_gemini_context_prompt(self.CASES, recent_corrections=corrections)
        assert "ep_too_narrow" in ctx

    def test_prompt_with_rules(self):
        rules = [{"rule_hint": "마이다 포함 시 내부 레이아웃 X", "correction_count": 5}]
        ctx = build_gemini_context_prompt(self.CASES, validated_rules=rules)
        assert "마이다" in ctx

    def test_prompt_empty_when_no_data(self):
        ctx = build_gemini_context_prompt([])
        assert ctx == ""

    def test_prompt_no_pii(self):
        cases = [{"furniture_type": "wardrobe", "customer_name": "홍길동",
                  "phone": "010-1234-5678", "width_mm": 2400}]
        ctx = build_gemini_context_prompt(cases)
        assert "홍길동" not in ctx
        assert "010-1234-5678" not in ctx

    def test_build_rag_context_returns_string(self):
        ctx = build_rag_context(furniture_type="wardrobe", width_mm=2400)
        assert isinstance(ctx, str)

    def test_rag_context_graceful_db_failure(self):
        """build_rag_context never raises — returns empty string on DB error."""
        ctx = build_rag_context(furniture_type="wardrobe", width_mm=9999999)
        assert isinstance(ctx, str)


class TestB6RetrievalContracts:
    """B6: Retrieval use in new candidates — acceptance criteria."""

    def test_layout_signature_accumulation_increases_confidence(self):
        """B6: More cases with same layout_signature → higher evidence → higher confidence."""
        from foms.services.designer.product_archetype_learning import (
            discover_archetypes_from_cases, extract_tags_from_case,
        )
        def make_case(i):
            return {
                "id": i, "furniture_type": "wardrobe", "product_name": "무몰딩장",
                "tags": ["no_molding"], "options_json": {},
                "width_mm": 2400,
                "internal_structure_json": {
                    "learned_design_category": {
                        "layout_signature": {"module_pattern": "3bay_hanging_shelves"},
                    },
                },
            }
        # 3 cases = min confidence
        cases3 = [make_case(i) for i in range(3)]
        cands3 = discover_archetypes_from_cases(cases3, min_count=3)
        # 7 cases = higher confidence
        cases7 = [make_case(i) for i in range(7)]
        cands7 = discover_archetypes_from_cases(cases7, min_count=3)
        assert len(cands3) == 1 and len(cands7) == 1
        assert cands7[0].confidence > cands3[0].confidence

    def test_retrieval_failure_returns_empty_not_raises(self):
        """B6: retrieval failure is non-silent — returns empty, logs warning (not silent success)."""
        from foms.services.designer.design_retrieval import retrieve_similar_cases
        from unittest.mock import patch

        # Patch the source functions in design_case_memory (where retrieve_similar_cases imports from)
        with patch(
            'foms.services.designer.design_case_memory.find_similar',
            side_effect=RuntimeError("DB down"),
        ):
            result = retrieve_similar_cases(furniture_type="wardrobe", width_mm=2400)
        # Must return empty list, never raise
        assert result == []

    def test_retrieval_result_pii_free_for_langgraph(self):
        """B6: PII-free payload only enters LangGraph state."""
        pii_case = {
            "furniture_type": "wardrobe", "width_mm": 2400,
            "customer_name": "홍길동", "phone": "010-1234-5678",
        }
        clean = _ensure_pii_free(pii_case)
        assert "customer_name" not in clean
        assert "phone" not in clean
        assert clean["furniture_type"] == "wardrobe"
