"""PG-B0A: Gemini Provider + Extraction Scorecard Tests.

Scope:
- gemini_provider.py import and interface contract
- extraction_scorecard.py algorithm unit tests
- Connectivity test (requires GEMINI_API_KEY — skipped if not set)
- Fixture manifest loader tests
- vision_extractor Gemini routing test

All live API tests require GEMINI_API_KEY environment variable.
Offline tests run without any API key.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


# ──────────────────────────────────────────────────────────
# PG-B0A-01: gemini_provider module interface contract
# ──────────────────────────────────────────────────────────

class TestGeminiProviderInterface:
    """Gemini provider module exists and exposes required interface."""

    def test_gemini_provider_importable(self):
        """gemini_provider.py is importable (PG-B0A implemented)."""
        import foms.services.designer.gemini_provider as gp
        assert gp is not None

    def test_gemini_provider_exposes_required_functions(self):
        """gemini_provider exposes extract_from_image_bytes, check_connectivity, estimate_cost_usd."""
        import foms.services.designer.gemini_provider as gp
        assert callable(gp.extract_from_image_bytes)
        assert callable(gp.extract_from_image_path)
        assert callable(gp.extract_from_url)
        assert callable(gp.check_connectivity)
        assert callable(gp.estimate_cost_usd)

    def test_gemini_provider_raises_key_missing_without_env(self):
        """Without GEMINI_API_KEY set, raises GeminiAPIKeyMissing."""
        import foms.services.designer.gemini_provider as gp
        prev = os.environ.pop("GEMINI_API_KEY", None)
        try:
            with pytest.raises(gp.GeminiAPIKeyMissing):
                gp._get_client()
        finally:
            if prev is not None:
                os.environ["GEMINI_API_KEY"] = prev

    def test_gemini_timeout_default_and_env_override(self, monkeypatch):
        """Gemini provider uses an explicit bounded SDK timeout."""
        import foms.services.designer.gemini_provider as gp

        monkeypatch.delenv("DESIGNER_GEMINI_TIMEOUT_SECONDS", raising=False)
        assert gp._get_timeout_ms() == 90000

        monkeypatch.setenv("DESIGNER_GEMINI_TIMEOUT_SECONDS", "120")
        assert gp._get_timeout_ms() == 120000

    def test_gemini_timeout_env_validation(self, monkeypatch):
        """Invalid timeout env values must fail loudly, not leave requests unbounded."""
        import foms.services.designer.gemini_provider as gp

        monkeypatch.setenv("DESIGNER_GEMINI_TIMEOUT_SECONDS", "abc")
        with pytest.raises(gp.GeminiProviderError):
            gp._get_timeout_ms()

        monkeypatch.setenv("DESIGNER_GEMINI_TIMEOUT_SECONDS", "5")
        with pytest.raises(gp.GeminiProviderError):
            gp._get_timeout_ms()

    def test_gemini_31_pro_cost_estimation(self):
        """estimate_cost_usd uses Gemini 3.1 Pro standard pricing."""
        import foms.services.designer.gemini_provider as gp

        # 2k input at $2/1M + 500 output at $12/1M = $0.0100
        cost = gp.estimate_cost_usd(
            input_tokens=2000,
            output_tokens=500,
            model_name="gemini-3.1-pro-preview",
        )
        assert cost == pytest.approx(0.0100)

    def test_gemini_31_pro_long_context_cost_estimation(self):
        """Gemini 3.1 Pro switches pricing when input prompt exceeds 200k tokens."""
        import foms.services.designer.gemini_provider as gp

        cost = gp.estimate_cost_usd(
            input_tokens=200_001,
            output_tokens=1000,
            model_name="gemini-3.1-pro-preview",
        )
        assert cost == pytest.approx(0.818004)

    def test_gemini_flash_cost_estimation(self):
        """Flash estimates use Gemini 2.5 Flash standard pricing."""
        import foms.services.designer.gemini_provider as gp

        cost = gp.estimate_cost_usd(
            input_tokens=2000,
            output_tokens=500,
            model_name="gemini-2.5-flash",
        )
        assert cost == pytest.approx(0.00185)

    def test_gemini_cost_default_is_flash(self, monkeypatch):
        """Default estimates must use Gemini 2.5 Flash pricing."""
        import foms.services.designer.gemini_provider as gp

        monkeypatch.delenv("DESIGNER_GEMINI_MODEL", raising=False)
        cost = gp.estimate_cost_usd(input_tokens=2000, output_tokens=500)
        assert cost == pytest.approx(0.00185)

    def test_gemini_unknown_model_falls_back_to_flash(self):
        """Unknown model estimates must not fall back to Pro pricing."""
        import foms.services.designer.gemini_provider as gp

        cost = gp.estimate_cost_usd(
            input_tokens=2000,
            output_tokens=500,
            model_name="gemini-unknown-experimental",
        )
        assert cost == pytest.approx(0.00185)

    def test_extraction_prompt_requests_design_understanding(self):
        """Prompt must preserve design-learning fields, not only dimensions."""
        import foms.services.designer.gemini_provider as gp

        assert "design_understanding" in gp._EXTRACTION_PROMPT
        assert "layout_graph" in gp._EXTRACTION_PROMPT
        assert "block_candidates" in gp._EXTRACTION_PROMPT
        assert "materials_textures" in gp._EXTRACTION_PROMPT
        assert "construction_rules" in gp._EXTRACTION_PROMPT

    def test_gemini_parse_valid_json(self):
        """_parse_and_validate handles valid Gemini JSON response."""
        import foms.services.designer.gemini_provider as gp
        raw = json.dumps({
            "furniture_type": "wardrobe",
            "extracted_params": {"width": 2400, "depth": 620, "height": 2400},
            "parts_table": [{"code": "[SR]", "description": "선반", "quantity": 3}],
            "customer_info": {"customer_name": None, "phone": None, "address": None},
            "drawing_meta": {"page_number": 1, "view_type": "front", "drawing_style": "technical"},
            "unresolved_fields": [],
            "confidence": 0.92,
        })
        result = gp._parse_and_validate(raw, "gemini-2.0-flash", 1500, 2000, 400)
        assert result["furniture_type"] == "wardrobe"
        assert result["extracted_params"]["width"] == 2400
        assert result["design_understanding"] == {}
        assert result["confidence"] == 0.92
        assert result["_metrics"]["latency_ms"] == 1500
        assert result["_metrics"]["model"] == "gemini-2.0-flash"

    def test_gemini_parse_invalid_json_raises(self):
        """_parse_and_validate raises GeminiProviderError on non-JSON response."""
        import foms.services.designer.gemini_provider as gp
        with pytest.raises(gp.GeminiProviderError):
            gp._parse_and_validate("Sorry I cannot help.", "gemini-2.0-flash", 0, 0, 0)

    def test_gemini_parse_unknown_furniture_type_defaults(self):
        """Unknown furniture_type defaults to custom_storage."""
        import foms.services.designer.gemini_provider as gp
        raw = json.dumps({
            "furniture_type": "refrigerator",
            "extracted_params": {},
            "unresolved_fields": [],
            "confidence": 0.3,
        })
        result = gp._parse_and_validate(raw, "gemini-2.0-flash", 0, 0, 0)
        assert result["furniture_type"] == "custom_storage"

    def test_gemini_parse_strips_markdown_fences(self):
        """_parse_and_validate handles Gemini responses wrapped in ```json fences."""
        import foms.services.designer.gemini_provider as gp
        raw = '```json\n{"furniture_type": "wardrobe", "extracted_params": {}, "unresolved_fields": [], "confidence": 0.8}\n```'
        result = gp._parse_and_validate(raw, "gemini-2.0-flash", 0, 0, 0)
        assert result["furniture_type"] == "wardrobe"


# ──────────────────────────────────────────────────────────
# PG-B0A-02: Extraction scorecard algorithm unit tests
# ──────────────────────────────────────────────────────────

class TestExtractionScorecardAlgorithm:
    """Scorecard algorithm correctness tests (no API required)."""

    def test_scorecard_importable(self):
        """extraction_scorecard.py is importable."""
        import foms.services.designer.extraction_scorecard as sc
        assert sc is not None

    def test_wdh_score_exact_match(self):
        """score_wdh returns correct=True for exact dimension match."""
        from foms.services.designer.extraction_scorecard import score_wdh
        scores = score_wdh(
            {"width": 2400, "depth": 620, "height": 2400},
            {"width": 2400, "depth": 620, "height": 2400},
            "test_001",
        )
        assert all(s.correct for s in scores)
        assert len(scores) == 3

    def test_wdh_score_within_tolerance(self):
        """score_wdh returns correct=True for dimensions within ±5mm tolerance."""
        from foms.services.designer.extraction_scorecard import score_wdh, WDH_TOLERANCE_MM
        scores = score_wdh(
            {"width": 2402, "depth": 618, "height": 2403},
            {"width": 2400, "depth": 620, "height": 2400},
            "test_001",
        )
        assert all(s.correct for s in scores), f"Should all be within {WDH_TOLERANCE_MM}mm: {scores}"

    def test_wdh_score_outside_tolerance(self):
        """score_wdh returns correct=False for dimensions outside tolerance."""
        from foms.services.designer.extraction_scorecard import score_wdh
        scores = score_wdh(
            {"width": 2500, "depth": 620, "height": 2400},
            {"width": 2400, "depth": 620, "height": 2400},
            "test_001",
        )
        width_score = next(s for s in scores if s.field_name == "width")
        assert not width_score.correct

    def test_wdh_score_missing_extraction(self):
        """score_wdh returns correct=False when extraction has no dimension."""
        from foms.services.designer.extraction_scorecard import score_wdh
        scores = score_wdh(
            {"depth": 620, "height": 2400},  # no width
            {"width": 2400, "depth": 620, "height": 2400},
            "test_001",
        )
        width_score = next(s for s in scores if s.field_name == "width")
        assert not width_score.correct
        assert width_score.notes == "missing"

    def test_parts_table_perfect_recall(self):
        """score_parts_table returns all correct when extraction contains all expected codes."""
        from foms.services.designer.extraction_scorecard import score_parts_table
        extracted = [{"code": "[SR]"}, {"code": "[EP]"}, {"code": "[DOOR]"}]
        expected = [{"code": "[SR]"}, {"code": "[EP]"}, {"code": "[DOOR]"}]
        scores = score_parts_table(extracted, expected, "test_001")
        assert all(s.correct for s in scores)

    def test_parts_table_partial_recall(self):
        """score_parts_table correctly identifies missing parts."""
        from foms.services.designer.extraction_scorecard import score_parts_table
        extracted = [{"code": "[SR]"}]
        expected = [{"code": "[SR]"}, {"code": "[EP]"}, {"code": "[DOOR]"}]
        scores = score_parts_table(extracted, expected, "test_001")
        assert sum(1 for s in scores if s.correct) == 1
        assert sum(1 for s in scores if not s.correct) == 2

    def test_parts_table_empty_expected_not_penalized(self):
        """score_parts_table returns empty list when no parts expected."""
        from foms.services.designer.extraction_scorecard import score_parts_table
        scores = score_parts_table([], [], "test_001")
        assert scores == []

    def test_extraction_score_overall(self):
        """ExtractionScore.overall_score computes weighted 60/30/10 correctly."""
        from foms.services.designer.extraction_scorecard import (
            ExtractionScore, FieldScore, score_wdh, score_parts_table, score_single_extraction
        )
        extracted = {
            "furniture_type": "wardrobe",
            "extracted_params": {"width": 2400, "depth": 620, "height": 2400},
            "parts_table": [{"code": "[SR]"}, {"code": "[EP]"}],
            "_metrics": {"latency_ms": 1200, "cost_usd": 0.0002},
        }
        expected = {
            "furniture_type": "wardrobe",
            "extracted_params": {"width": 2400, "depth": 620, "height": 2400},
            "parts_table": [{"code": "[SR]"}, {"code": "[EP]"}],
        }
        score = score_single_extraction("test_001", extracted, expected)
        assert score.wdh_accuracy == 1.0
        assert score.parts_recall == 1.0
        assert abs(score.overall_score - 1.0) < 1e-9, f"Expected ~1.0, got {score.overall_score}"
        assert score.furniture_type_correct is True

    def test_scorecard_report_gates(self):
        """ScorecardReport gate checks work correctly."""
        from foms.services.designer.extraction_scorecard import (
            ScorecardReport, ExtractionScore, FieldScore,
            WDH_ACCURACY_TARGET, PARTS_RECALL_TARGET,
        )
        # Build a report that meets targets
        good_score = ExtractionScore(fixture_id="t1", furniture_type_correct=True)
        good_score.wdh_scores = [
            FieldScore("width", 2400, 2400, True),
            FieldScore("depth", 620, 620, True),
            FieldScore("height", 2400, 2400, True),
        ]
        report = ScorecardReport(scores=[good_score])
        assert report.wdh_gate_pass is True
        assert report.parts_gate_pass is True  # no parts → not penalized

    def test_scorecard_report_gate_fails_below_threshold(self):
        """ScorecardReport gate fails when accuracy is below target."""
        from foms.services.designer.extraction_scorecard import (
            ScorecardReport, ExtractionScore, FieldScore,
        )
        bad_score = ExtractionScore(fixture_id="t1", furniture_type_correct=True)
        bad_score.wdh_scores = [
            FieldScore("width", 3000, 2400, False),  # wrong
            FieldScore("depth", 620, 620, True),
            FieldScore("height", 2400, 2400, True),
        ]
        report = ScorecardReport(scores=[bad_score])
        assert report.wdh_gate_pass is False  # 2/3 = 0.667 < 0.95


# ──────────────────────────────────────────────────────────
# PG-B0A-03: Fixture manifest tests
# ──────────────────────────────────────────────────────────

class TestFixtureManifest:
    """Fixture manifest structure and loader tests."""

    MANIFEST_PATH = Path(__file__).parent.parent / "fixtures" / "drawings" / "manifest.json"

    def test_manifest_file_exists(self):
        """tests/fixtures/drawings/manifest.json now exists (PG-B0A created)."""
        assert self.MANIFEST_PATH.exists(), (
            f"manifest.json not found at {self.MANIFEST_PATH}. "
            "PG-B0A should have created this file."
        )

    def test_manifest_has_5_poc_fixtures(self):
        """Manifest contains 5 POC fixtures."""
        with open(self.MANIFEST_PATH, encoding="utf-8") as f:
            data = json.load(f)
        assert len(data["fixtures"]) == 5, (
            f"Expected 5 POC fixtures, got {len(data['fixtures'])}"
        )

    def test_manifest_fixtures_have_required_fields(self):
        """Each fixture has id, description, file_path, file_status, furniture_type_expected."""
        with open(self.MANIFEST_PATH, encoding="utf-8") as f:
            data = json.load(f)
        required = {"id", "description", "file_path", "file_status", "furniture_type_expected"}
        for fix in data["fixtures"]:
            missing = required - set(fix.keys())
            assert not missing, f"Fixture {fix.get('id')} missing fields: {missing}"

    def test_manifest_poc_fixtures_are_pending(self):
        """All 5 POC fixtures start as 'pending' (files not yet uploaded)."""
        with open(self.MANIFEST_PATH, encoding="utf-8") as f:
            data = json.load(f)
        for fix in data["fixtures"]:
            assert fix["file_status"] == "pending", (
                f"Fixture {fix['id']} expected status='pending', got {fix['file_status']!r}"
            )

    def test_manifest_furniture_types_valid(self):
        """All fixtures have valid furniture_type_expected."""
        valid = {"wardrobe", "shoe_rack", "kitchen_base", "kitchen_wall", "custom_storage"}
        with open(self.MANIFEST_PATH, encoding="utf-8") as f:
            data = json.load(f)
        for fix in data["fixtures"]:
            ft = fix.get("furniture_type_expected")
            assert ft in valid, f"Fixture {fix['id']} has invalid furniture_type: {ft!r}"

    def test_scorecard_manifest_loader(self):
        """load_fixture_manifest loads the manifest correctly."""
        from foms.services.designer.extraction_scorecard import (
            load_fixture_manifest, get_available_fixtures,
        )
        manifest = load_fixture_manifest(self.MANIFEST_PATH)
        assert "fixtures" in manifest
        assert len(manifest["fixtures"]) == 5
        # All pending → no available fixtures yet
        available = get_available_fixtures(manifest)
        assert len(available) == 0, (
            f"Expected 0 available fixtures (all pending), got {len(available)}"
        )

    def test_scorecard_run_on_empty_corpus_returns_empty_report(self):
        """run_scorecard_from_manifest on all-pending manifest returns empty report."""
        from foms.services.designer.extraction_scorecard import (
            run_scorecard_from_manifest,
        )
        def dummy_extractor(path):
            return {}

        report = run_scorecard_from_manifest(self.MANIFEST_PATH, dummy_extractor)
        assert report.total_fixtures == 0
        assert report.error_count == 0


# ──────────────────────────────────────────────────────────
# PG-B0A-04: vision_extractor Gemini routing
# ──────────────────────────────────────────────────────────

class TestVisionExtractorGeminiRouting:
    """vision_extractor correctly routes DESIGNER_VISION_PROVIDER=gemini."""

    def test_gemini_routing_raises_without_key(self):
        """DESIGNER_VISION_PROVIDER=gemini without GEMINI_API_KEY raises VisionProviderUnavailable."""
        import importlib
        import foms.services.designer.vision_extractor as vx
        from foms.services.designer.vision_types import VisionInput

        prev_provider = os.environ.get("DESIGNER_VISION_PROVIDER", "")
        prev_key = os.environ.pop("GEMINI_API_KEY", None)
        prev_fake = os.environ.get("DESIGNER_FAKE_VISION", "0")
        os.environ["DESIGNER_VISION_PROVIDER"] = "gemini"
        os.environ["DESIGNER_FAKE_VISION"] = "0"
        try:
            importlib.reload(vx)
            vi = VisionInput(image_url="test.jpg", source="manual_upload")
            with pytest.raises(vx.VisionProviderUnavailable):
                vx.extract_candidate(vi)
        finally:
            os.environ["DESIGNER_VISION_PROVIDER"] = prev_provider
            os.environ["DESIGNER_FAKE_VISION"] = prev_fake
            if prev_key is not None:
                os.environ["GEMINI_API_KEY"] = prev_key
            importlib.reload(vx)

    def test_unknown_provider_raises(self):
        """DESIGNER_VISION_PROVIDER=unknown_xyz raises VisionProviderUnavailable."""
        import importlib
        import foms.services.designer.vision_extractor as vx
        from foms.services.designer.vision_types import VisionInput

        prev_provider = os.environ.get("DESIGNER_VISION_PROVIDER", "")
        prev_fake = os.environ.get("DESIGNER_FAKE_VISION", "0")
        os.environ["DESIGNER_VISION_PROVIDER"] = "unknown_xyz"
        os.environ["DESIGNER_FAKE_VISION"] = "0"
        try:
            importlib.reload(vx)
            vi = VisionInput(image_url="test.jpg", source="manual_upload")
            with pytest.raises(vx.VisionProviderUnavailable):
                vx.extract_candidate(vi)
        finally:
            os.environ["DESIGNER_VISION_PROVIDER"] = prev_provider
            os.environ["DESIGNER_FAKE_VISION"] = prev_fake
            importlib.reload(vx)


# ──────────────────────────────────────────────────────────
# PG-B0A-05: Live connectivity test (requires GEMINI_API_KEY)
# ──────────────────────────────────────────────────────────

GEMINI_KEY_AVAILABLE = bool(os.environ.get("GEMINI_API_KEY", ""))


def _skip_if_quota_issue(e: Exception) -> None:
    """Skip test gracefully on 429 rate limit or quota=0 (billing not enabled).

    'limit: 0' means the Google Cloud project has not enabled billing for
    the Gemini API. This is a project configuration issue, not a code bug.
    Action required: enable billing at console.cloud.google.com.
    """
    msg = str(e)
    if "429" in msg or "RESOURCE_EXHAUSTED" in msg or "quota" in msg.lower() or "NOT_FOUND" in msg:
        pytest.skip(
            f"Gemini API quota/billing issue (live test skipped): {msg[:300]}\n"
            "ACTION: Enable billing at console.cloud.google.com for Gemini API."
        )


@pytest.mark.skipif(not GEMINI_KEY_AVAILABLE, reason="GEMINI_API_KEY not set — skipping live API test")
class TestGeminiConnectivityLive:
    """Live Gemini API tests. Only run when GEMINI_API_KEY is set.

    Uses configured default model (gemini-3.1-pro-preview when DESIGNER_GEMINI_MODEL unset).
    Tests are skipped gracefully on 429 rate limit.
    """

    DEFAULT_MODEL = "gemini-3.1-pro-preview"

    def test_connectivity_ping(self):
        """Gemini API connectivity ping succeeds (requires billing enabled)."""
        import foms.services.designer.gemini_provider as gp
        try:
            result = gp.check_connectivity(model=self.DEFAULT_MODEL)
        except Exception as exc:
            _skip_if_quota_issue(exc)
            raise
        if not result["ok"] and result["error"]:
            _skip_if_quota_issue(Exception(result["error"]))
        assert result["ok"] is True, f"Connectivity failed: {result}"
        assert result["latency_ms"] > 0
        assert result["error"] is None

    def test_text_extraction_wardrobe_description(self):
        """Gemini can extract furniture data from a text description (POC — no image file needed)."""
        import foms.services.designer.gemini_provider as gp
        from google.genai import types

        client = gp._get_client()
        prompt = (
            "아래는 가구 도면에서 추출한 정보입니다.\n"
            "현장명: 홍길동 고객\n"
            "제품: 붙박이장 W2400 H2400 D620\n"
            "구성: 3칸, [SR] 선반 6개, [EP] 경첩 12개\n"
            "\n"
            + gp._EXTRACTION_PROMPT
        )
        t0 = __import__("time").monotonic()
        try:
            response = client.models.generate_content(
                model=self.DEFAULT_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    response_mime_type="application/json",
                ),
            )
        except Exception as exc:
            _skip_if_quota_issue(exc)
            raise

        latency_ms = int((__import__("time").monotonic() - t0) * 1000)
        raw = response.text or "{}"

        import json
        data = json.loads(raw)
        assert data.get("furniture_type") == "wardrobe", (
            f"Expected furniture_type=wardrobe, got {data.get('furniture_type')!r}"
        )
        params = data.get("extracted_params", {})
        width = params.get("width")
        assert width is not None, f"Width not extracted. extracted_params={params}"
        assert abs(int(width) - 2400) <= 100, f"Width {width} not near 2400mm"
        assert latency_ms < 20000, f"Too slow: {latency_ms}ms"

        input_tokens = getattr(getattr(response, "usage_metadata", None), "prompt_token_count", 0) or 0
        output_tokens = getattr(getattr(response, "usage_metadata", None), "candidates_token_count", 0) or 0
        cost = gp.estimate_cost_usd(input_tokens, output_tokens, model_name=self.DEFAULT_MODEL)
        # POC report (visible with pytest -s)
        print(
            f"\n[POC REPORT] model={self.DEFAULT_MODEL} "
            f"latency={latency_ms}ms "
            f"in_tok={input_tokens} out_tok={output_tokens} "
            f"cost_usd=${cost:.5f} "
            f"furniture_type={data.get('furniture_type')} "
            f"width={width} confidence={data.get('confidence')}"
        )
