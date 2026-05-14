"""PG-B4: Template Classifier + Model Router Tests."""

from __future__ import annotations

import os
import pytest


# ──────────────────────────────────────────────────────────
# PG-B4-01: Template Classifier
# ──────────────────────────────────────────────────────────

class TestTemplateClassifier:
    def test_classifier_importable(self):
        from foms.services.designer.drawing_template_classifier import (
            classify_from_filename, classify_from_metadata, TEMPLATE_KEYS
        )
        assert len(TEMPLATE_KEYS) == 5

    def test_lahom_filename_hint(self):
        from foms.services.designer.drawing_template_classifier import classify_from_filename
        result = classify_from_filename("라홈_붙박이장_홍길동.jpg")
        assert result.template_key == "lahom_standard"
        assert result.confidence >= 0.5

    def test_benissimo_filename_hint(self):
        from foms.services.designer.drawing_template_classifier import classify_from_filename
        result = classify_from_filename("benissimo_wardrobe_001.jpg")
        assert result.template_key == "benissimo_standard"

    def test_ehf_filename_hint(self):
        from foms.services.designer.drawing_template_classifier import classify_from_filename
        result = classify_from_filename("ehf_standard_drawing.jpg")
        assert result.template_key == "ehf_standard"

    def test_unknown_filename(self):
        from foms.services.designer.drawing_template_classifier import classify_from_filename
        result = classify_from_filename("drawing_001.jpg")
        assert result.template_key == "unknown"

    def test_pdf_detected_as_multi_page(self):
        from foms.services.designer.drawing_template_classifier import classify_from_filename
        result = classify_from_filename("wardrobe_drawing.pdf")
        assert result.template_key == "multi_page_detail" or result.is_multi_page

    def test_page_count_triggers_multi_page(self):
        from foms.services.designer.drawing_template_classifier import classify_from_metadata
        result = classify_from_metadata("drawing.jpg", page_count=3)
        assert result.is_multi_page is True
        assert result.page_count == 3

    def test_classification_result_has_template_key(self):
        from foms.services.designer.drawing_template_classifier import (
            classify_from_filename, TEMPLATE_KEYS
        )
        result = classify_from_filename("any_drawing.jpg")
        assert result.template_key in TEMPLATE_KEYS

    def test_all_template_keys_valid(self):
        from foms.services.designer.drawing_template_classifier import TEMPLATE_KEYS
        expected = {"lahom_standard", "benissimo_standard", "ehf_standard",
                    "multi_page_detail", "unknown"}
        assert expected == TEMPLATE_KEYS

    def test_result_to_dict(self):
        from foms.services.designer.drawing_template_classifier import classify_from_filename
        result = classify_from_filename("test.jpg")
        d = result.to_dict()
        assert "template_key" in d
        assert "confidence" in d
        assert "method" in d


# ──────────────────────────────────────────────────────────
# PG-B4-02: Model Router (fake mode)
# ──────────────────────────────────────────────────────────

class TestModelRouterFake:
    """Model router tests using fake mode (no API key needed)."""

    def test_router_importable(self):
        from foms.services.designer.model_router import route, ModelRouteResult
        assert callable(route)

    def test_fake_mode_routes_to_fake(self):
        """DESIGNER_FAKE_VISION=1 always routes to fake provider."""
        prev = os.environ.get("DESIGNER_FAKE_VISION", "0")
        os.environ["DESIGNER_FAKE_VISION"] = "1"
        try:
            from foms.services.designer.model_router import route
            result = route("wardrobe")
            assert result.provider == "fake"
            assert result.estimated_cost_usd == 0.0
        finally:
            os.environ["DESIGNER_FAKE_VISION"] = prev

    def test_no_key_raises_without_fake_mode(self):
        """Without GEMINI_API_KEY and fake mode off, route raises RuntimeError."""
        prev_key = os.environ.pop("GEMINI_API_KEY", None)
        prev_fake = os.environ.get("DESIGNER_FAKE_VISION", "0")
        os.environ["DESIGNER_FAKE_VISION"] = "0"
        try:
            from foms.services.designer.model_router import route
            with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
                route("lahom_standard")
        finally:
            os.environ["DESIGNER_FAKE_VISION"] = prev_fake
            if prev_key is not None:
                os.environ["GEMINI_API_KEY"] = prev_key

    def test_multi_page_routes_to_pro(self):
        """Multi-page documents get pro model (higher accuracy)."""
        prev_key = os.environ.get("GEMINI_API_KEY", "")
        prev_fake = os.environ.get("DESIGNER_FAKE_VISION", "0")
        os.environ["DESIGNER_FAKE_VISION"] = "0"
        os.environ["GEMINI_API_KEY"] = "test_key_for_routing_logic"
        try:
            from foms.services.designer import model_router
            import importlib
            importlib.reload(model_router)
            result = model_router.route("multi_page_detail", page_count=3)
            assert result.model_name == "gemini-2.5-pro"
        finally:
            os.environ["DESIGNER_FAKE_VISION"] = prev_fake
            if prev_key:
                os.environ["GEMINI_API_KEY"] = prev_key
            else:
                os.environ.pop("GEMINI_API_KEY", None)
            importlib.reload(model_router)

    def test_force_model_override(self):
        """force_model parameter overrides routing selection."""
        prev_key = os.environ.get("GEMINI_API_KEY", "")
        prev_fake = os.environ.get("DESIGNER_FAKE_VISION", "0")
        os.environ["DESIGNER_FAKE_VISION"] = "0"
        os.environ["GEMINI_API_KEY"] = "test_key_for_routing"
        try:
            from foms.services.designer.model_router import route
            result = route("lahom_standard", force_model="gemini-2.5-flash")
            assert result.model_name == "gemini-2.5-flash"
        finally:
            os.environ["DESIGNER_FAKE_VISION"] = prev_fake
            if prev_key:
                os.environ["GEMINI_API_KEY"] = prev_key
            else:
                os.environ.pop("GEMINI_API_KEY", None)

    def test_route_result_has_required_fields(self):
        """ModelRouteResult has provider, model_name, template_key, reasoning."""
        prev = os.environ.get("DESIGNER_FAKE_VISION", "0")
        os.environ["DESIGNER_FAKE_VISION"] = "1"
        try:
            from foms.services.designer.model_router import route
            result = route("lahom_standard")
            d = result.to_dict()
            assert "provider" in d
            assert "model_name" in d
            assert "template_key" in d
            assert "reasoning" in d
            assert "estimated_cost_usd" in d
        finally:
            os.environ["DESIGNER_FAKE_VISION"] = prev
