"""PG-B6: Dimension/View Geometry Parser Tests.

Verifies:
- W/D/H parsing from OCR text variants
- Site footer parsing
- Stacked height parsing
- Gemini JSON dimension parsing
- View type detection
- Scorecard (recall >= 90%, meets_95_target)
"""

from __future__ import annotations

import pytest
from foms.services.designer.dimension_parser import (
    parse_ocr_text, parse_gemini_dimensions,
    score_dimension_recall, DimensionCandidate,
)
from foms.services.designer.view_detector import (
    detect_view_from_text, detect_view_from_gemini,
    classify_page_views, score_view_accuracy,
)


# ──────────────────────────────────────────────────────────
# PG-B6-01: Dimension parser importable
# ──────────────────────────────────────────────────────────

def test_dimension_parser_importable():
    from foms.services.designer import dimension_parser
    assert callable(dimension_parser.parse_ocr_text)
    assert callable(dimension_parser.parse_gemini_dimensions)
    assert callable(dimension_parser.score_dimension_recall)


def test_view_detector_importable():
    from foms.services.designer import view_detector
    assert callable(view_detector.detect_view_from_text)


# ──────────────────────────────────────────────────────────
# PG-B6-02: OCR text parsing
# ──────────────────────────────────────────────────────────

class TestOcrTextParsing:
    def test_explicit_w_h_d(self):
        result = parse_ocr_text("W 2400\nH 2200\nD 620")
        wdh = result.get_wdh()
        assert wdh["width"] == 2400
        assert wdh["height"] == 2200
        assert wdh["depth"] == 620

    def test_colon_format(self):
        result = parse_ocr_text("폭:2400\n높이:2200\n깊이:620")
        wdh = result.get_wdh()
        assert wdh["width"] == 2400
        assert wdh["height"] == 2200

    def test_wxhxd_star_format(self):
        result = parse_ocr_text("2400*2200*620")
        wdh = result.get_wdh()
        assert wdh["width"] == 2400
        assert wdh["height"] == 2200
        assert wdh["depth"] == 620

    def test_wxhxd_cross_format(self):
        result = parse_ocr_text("2400×2200×620")
        wdh = result.get_wdh()
        assert wdh["width"] == 2400

    def test_site_footer(self):
        result = parse_ocr_text("현장규격 1620*500*2306")
        assert result.site_size.get("width") == 1620
        assert result.site_size.get("height") == 500
        assert result.site_size.get("depth") == 2306

    def test_depth_label(self):
        result = parse_ocr_text("D:445")
        depth_candidates = [c for c in result.candidates if c.axis == "depth"]
        assert len(depth_candidates) >= 1
        assert depth_candidates[0].value_mm == 445

    def test_depth_label_d_equals(self):
        result = parse_ocr_text("D=550")
        depth_candidates = [c for c in result.candidates if c.axis == "depth"]
        assert any(c.value_mm == 550 for c in depth_candidates)

    def test_stacked_heights(self):
        result = parse_ocr_text("250 / 300 / 250 / 300")
        assert len(result.stacked_heights_mm) >= 3
        assert 250 in result.stacked_heights_mm
        assert 300 in result.stacked_heights_mm

    def test_sanity_filter_rejects_tiny_values(self):
        """Values < 50mm should not be parsed as dimensions."""
        result = parse_ocr_text("W 5\nH 10\nD 2")
        assert not result.candidates

    def test_sanity_filter_rejects_huge_values(self):
        """Values > 12000mm should not be parsed."""
        result = parse_ocr_text("W 99999\nH 50000")
        assert not result.candidates

    def test_multi_line_drawing(self):
        # Explicit W/H/D labels override site footer
        text = """W 2400
H 2200
D:620
250 / 300 / 250 / 300"""
        result = parse_ocr_text(text)
        wdh = result.get_wdh()
        assert wdh["width"] == 2400
        assert wdh["height"] == 2200
        assert wdh["depth"] is not None


# ──────────────────────────────────────────────────────────
# PG-B6-03: Gemini JSON parsing
# ──────────────────────────────────────────────────────────

class TestGeminiDimensionParsing:
    GEMINI_EXTRACTION = {
        "furniture_type": "wardrobe",
        "extracted_params": {
            "width": 2400, "height": 2200, "depth": 620,
            "module_widths": [800, 800, 800],
        },
        "drawing_meta": {"view_type": "front", "drawing_style": "technical"},
        "confidence": 0.92,
    }

    def test_basic_wdh_from_gemini(self):
        result = parse_gemini_dimensions(self.GEMINI_EXTRACTION)
        wdh = result.get_wdh()
        assert wdh["width"] == 2400
        assert wdh["height"] == 2200
        assert wdh["depth"] == 620

    def test_module_widths_extracted(self):
        result = parse_gemini_dimensions(self.GEMINI_EXTRACTION)
        assert result.module_widths_mm == [800, 800, 800]

    def test_confidence_positive(self):
        result = parse_gemini_dimensions(self.GEMINI_EXTRACTION)
        assert result.confidence > 0

    def test_gemini_dimension_candidates_list(self):
        extraction = {
            "extracted_params": {"width": 2400, "height": 2200, "depth": 620},
            "dimension_candidates": [
                {"value_mm": 800, "axis": "module_width", "view": "front", "source": "drawing"},
                {"value_mm": 400, "axis": "shelf_height", "view": "front", "source": "drawing"},
            ],
        }
        result = parse_gemini_dimensions(extraction)
        axes = {c.axis for c in result.candidates}
        assert "width" in axes
        assert "module_width" in axes

    def test_invalid_values_skip(self):
        extraction = {"extracted_params": {"width": "??", "height": None}}
        result = parse_gemini_dimensions(extraction)
        width_candidates = [c for c in result.candidates if c.axis == "width"]
        assert not width_candidates


# ──────────────────────────────────────────────────────────
# PG-B6-04: Scorecard
# ──────────────────────────────────────────────────────────

class TestDimensionScorecard:
    def test_perfect_recall(self):
        result = parse_ocr_text("W 2400\nH 2200\nD 620")
        score = score_dimension_recall(result, {"width": 2400, "height": 2200, "depth": 620})
        assert score["recall"] == 1.0
        assert score["meets_95_target"] is True

    def test_within_tolerance(self):
        result = parse_ocr_text("W 2402\nH 2198\nD 622")
        score = score_dimension_recall(
            result,
            {"width": 2400, "height": 2200, "depth": 620},
            tolerance_mm=5,
        )
        assert score["recall"] == 1.0

    def test_outside_tolerance_fails(self):
        result = parse_ocr_text("W 3000\nH 2200\nD 620")
        score = score_dimension_recall(result, {"width": 2400, "height": 2200, "depth": 620})
        assert score["per_axis"]["width"]["correct"] is False
        assert score["recall"] < 1.0

    def test_missing_dimension_not_counted(self):
        """Expected has only W/H — missing D in expected is not penalised."""
        result = parse_ocr_text("W 2400\nH 2200")
        score = score_dimension_recall(result, {"width": 2400, "height": 2200})
        assert score["recall"] == 1.0

    def test_meets_90_target_field(self):
        result = parse_ocr_text("W 2400\nH 2200\nD 620")
        score = score_dimension_recall(result, {"width": 2400, "height": 2200, "depth": 620})
        assert "meets_target" in score  # >= 90%
        assert "meets_95_target" in score  # >= 95%

    def test_gemini_achieves_95_target(self):
        """Gemini extraction with correct W/D/H should meet 95% target."""
        extraction = {
            "extracted_params": {"width": 2400, "height": 2200, "depth": 620},
        }
        result = parse_gemini_dimensions(extraction)
        score = score_dimension_recall(
            result,
            {"width": 2400, "height": 2200, "depth": 620},
        )
        assert score["meets_95_target"] is True


# ──────────────────────────────────────────────────────────
# PG-B6-05: View detector
# ──────────────────────────────────────────────────────────

class TestViewDetector:
    @pytest.mark.parametrize("text,expected", [
        ("정면도", "front"),
        ("측면도", "side"),
        ("평면도", "top"),
        ("투상도", "isometric"),
        ("front view", "front"),
        ("side view", "side"),
        ("현장사진 포함", "photo"),
        ("치수선만 있음", "unknown"),
    ])
    def test_detect_from_text(self, text, expected):
        assert detect_view_from_text(text) == expected

    def test_detect_from_gemini_meta(self):
        meta = {"view_type": "front", "drawing_style": "technical"}
        assert detect_view_from_gemini(meta) == "front"

    def test_detect_from_gemini_isometric(self):
        meta = {"view_type": "isometric"}
        assert detect_view_from_gemini(meta) == "isometric"

    def test_detect_unknown_returns_unknown(self):
        assert detect_view_from_gemini({}) == "unknown"

    def test_classify_page_views(self):
        pages = [
            {"drawing_meta": {"view_type": "front"}},
            {"drawing_meta": {"view_type": "side"}},
            {"notes": "투상도"},
        ]
        views = classify_page_views(pages)
        assert views[0] == "front"
        assert views[1] == "side"
        assert views[2] == "isometric"

    def test_score_view_accuracy_perfect(self):
        score = score_view_accuracy(["front", "side"], ["front", "side"])
        assert score["accuracy"] == 1.0
        assert score["meets_target"] is True

    def test_score_view_accuracy_partial(self):
        score = score_view_accuracy(["front", "top"], ["front", "side"])
        assert score["accuracy"] == 0.5
        assert score["meets_target"] is False
