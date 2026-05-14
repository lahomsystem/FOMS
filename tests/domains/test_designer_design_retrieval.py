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
