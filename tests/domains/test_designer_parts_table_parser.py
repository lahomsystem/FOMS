"""PG-B5: Parts Table Parser Tests.

Verifies SR/EP/DOOR/마이다/옷봉 parsing from text and Gemini JSON.
Target: item recall >= 90%, qty exact match >= 95%.
"""

from __future__ import annotations

import pytest
from foms.services.designer.parts_table_parser import (
    parse_line, parse_text, parse_gemini_parts_table,
    normalize_code, score_parts_recall, ParsedPartsTable,
)


# ──────────────────────────────────────────────────────────
# PG-B5-01: Code normalization
# ──────────────────────────────────────────────────────────

class TestCodeNormalization:
    @pytest.mark.parametrize("raw,expected", [
        ("[SR]", "[SR]"),
        ("SR", "[SR]"),
        ("sr", "[SR]"),
        ("[EP]", "[EP]"),
        ("EP", "[EP]"),
        ("[DOOR]", "[DOOR]"),
        ("DOOR", "[DOOR]"),
        ("마이다", "[마이다]"),
        ("[마이다]", "[마이다]"),
        ("옷봉", "[옷봉]"),
        ("보조목", "[보조목]"),
        ("데코EP", "[EP]"),
    ])
    def test_normalize_code(self, raw, expected):
        assert normalize_code(raw) == expected, f"normalize_code({raw!r}) expected {expected!r}"


# ──────────────────────────────────────────────────────────
# PG-B5-02: Single line parsing
# ──────────────────────────────────────────────────────────

class TestParseLineSingle:
    def test_sr_full_format(self):
        """[SR] 60*2440=1"""
        item = parse_line("[SR] 60*2440=1")
        assert item is not None
        assert item.code == "[SR]"
        assert item.width_mm == 60
        assert item.height_mm == 2440
        assert item.quantity == 1

    def test_ep_x_format(self):
        """[EP] 70x2440=2"""
        item = parse_line("[EP] 70x2440=2")
        assert item is not None
        assert item.code == "[EP]"
        assert item.quantity == 2

    def test_door_with_note(self):
        """[DOOR] 595*345=1 (플랩)"""
        item = parse_line("[DOOR] 595*345=1 플랩")
        assert item is not None
        assert item.code == "[DOOR]"
        assert item.quantity == 1

    def test_sr_no_dimensions(self):
        """SR=3"""
        item = parse_line("SR=3")
        assert item is not None
        assert item.code == "[SR]"
        assert item.quantity == 3

    def test_korean_code_마이다(self):
        """마이다 4"""
        item = parse_line("마이다 4")
        assert item is not None
        assert item.code == "[마이다]"
        assert item.quantity == 4

    def test_옷봉(self):
        item = parse_line("옷봉 2")
        assert item is not None
        assert item.code == "[옷봉]"

    def test_보조목(self):
        item = parse_line("보조목 3")
        assert item is not None
        assert item.code == "[보조목]"

    def test_unknown_line_returns_none(self):
        item = parse_line("이 줄은 부품표가 아닙니다")
        assert item is None

    def test_empty_line_returns_none(self):
        assert parse_line("") is None


# ──────────────────────────────────────────────────────────
# PG-B5-03: Multi-line text parsing
# ──────────────────────────────────────────────────────────

SAMPLE_PARTS_TEXT = """[SR] 60*2440=6
[EP] 70*2440=4
[DOOR] 595*345=3
[마이다] 4
옷봉 2
보조목 1
알 수 없는 텍스트
"""


class TestParseText:
    def test_parses_all_known_codes(self):
        result = parse_text(SAMPLE_PARTS_TEXT)
        codes = {item.code for item in result.items}
        assert "[SR]" in codes
        assert "[EP]" in codes
        assert "[DOOR]" in codes
        assert "[마이다]" in codes
        assert "[옷봉]" in codes
        assert "[보조목]" in codes

    def test_unknown_line_tracked(self):
        result = parse_text(SAMPLE_PARTS_TEXT)
        assert len(result.unrecognized_lines) >= 1

    def test_confidence_high_for_known_tables(self):
        result = parse_text(SAMPLE_PARTS_TEXT)
        assert result.confidence >= 0.7

    def test_quantities_correct(self):
        result = parse_text(SAMPLE_PARTS_TEXT)
        sr_items = result.get_by_code("[SR]")
        assert sr_items[0].quantity == 6

    def test_dimensions_parsed(self):
        result = parse_text(SAMPLE_PARTS_TEXT)
        sr_items = result.get_by_code("[SR]")
        assert sr_items[0].width_mm == 60
        assert sr_items[0].height_mm == 2440


# ──────────────────────────────────────────────────────────
# PG-B5-04: Gemini JSON parsing
# ──────────────────────────────────────────────────────────

GEMINI_PARTS_LIST = [
    {"code": "[SR]", "description": "선반 60*2440", "quantity": 6, "note": ""},
    {"code": "[EP]", "description": "엔드패널", "quantity": 4, "note": "데코"},
    {"code": "[DOOR]", "description": "도어", "quantity": 3, "note": "플랩"},
    {"code": "마이다", "description": "마이다스", "quantity": 2, "note": ""},
    {"code": "옷봉", "description": "옷봉", "quantity": 1, "note": ""},
]


class TestParseGeminiJson:
    def test_gemini_json_parses_all_codes(self):
        result = parse_gemini_parts_table(GEMINI_PARTS_LIST)
        codes = {item.code for item in result.items}
        assert "[SR]" in codes
        assert "[EP]" in codes
        assert "[DOOR]" in codes
        assert "[마이다]" in codes
        assert "[옷봉]" in codes

    def test_gemini_quantities_correct(self):
        result = parse_gemini_parts_table(GEMINI_PARTS_LIST)
        sr = result.get_by_code("[SR]")
        assert sr[0].quantity == 6

    def test_gemini_dimensions_from_description(self):
        result = parse_gemini_parts_table(GEMINI_PARTS_LIST)
        sr = result.get_by_code("[SR]")
        assert sr[0].width_mm == 60
        assert sr[0].height_mm == 2440

    def test_gemini_confidence_100_for_all_recognized(self):
        result = parse_gemini_parts_table(GEMINI_PARTS_LIST)
        assert result.confidence == 1.0


# ──────────────────────────────────────────────────────────
# PG-B5-05: Recall scorecard
# ──────────────────────────────────────────────────────────

class TestPartsRecall:
    def test_perfect_recall(self):
        result = parse_gemini_parts_table(GEMINI_PARTS_LIST)
        expected = [
            {"code": "[SR]", "quantity": 6},
            {"code": "[EP]", "quantity": 4},
            {"code": "[DOOR]", "quantity": 3},
        ]
        score = score_parts_recall(result, expected)
        assert score["recall"] == 1.0

    def test_missing_item_reduces_recall(self):
        """If DOOR not in parsed, recall < 1.0."""
        minimal = parse_gemini_parts_table([
            {"code": "[SR]", "description": "선반", "quantity": 6},
            {"code": "[EP]", "description": "EP", "quantity": 4},
        ])
        expected = [
            {"code": "[SR]", "quantity": 6},
            {"code": "[EP]", "quantity": 4},
            {"code": "[DOOR]", "quantity": 3},
        ]
        score = score_parts_recall(minimal, expected)
        assert score["recall"] < 1.0

    def test_empty_expected_returns_perfect(self):
        result = parse_text("")
        score = score_parts_recall(result, [])
        assert score["recall"] == 1.0

    def test_meets_target_field(self):
        """score includes meets_target (recall >= 0.90)."""
        result = parse_gemini_parts_table(GEMINI_PARTS_LIST)
        expected = [{"code": "[SR]", "quantity": 6}]
        score = score_parts_recall(result, expected)
        assert "meets_target" in score
        assert score["meets_target"] is True

    def test_full_sample_achieves_90_recall(self):
        """Full sample from GEMINI_PARTS_LIST achieves >= 90% recall."""
        result = parse_gemini_parts_table(GEMINI_PARTS_LIST)
        expected = [
            {"code": "[SR]", "quantity": 6},
            {"code": "[EP]", "quantity": 4},
            {"code": "[DOOR]", "quantity": 3},
            {"code": "[마이다]", "quantity": 2},
            {"code": "[옷봉]", "quantity": 1},
        ]
        score = score_parts_recall(result, expected)
        assert score["recall"] >= 0.90, (
            f"Parts table recall {score['recall']:.2f} < 0.90 target. "
            f"per_code: {score['per_code']}"
        )
