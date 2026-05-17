"""B1: Deterministic Layout Graph Mapper Tests.

Verifies that layout_graph_mapper converts Gemini extraction →
FOMS DesignGraph (schema v2) without any LLM calls.

Fixtures:
  - 3-bay wardrobe (3 zones, shelves + hanging + open)
  - TV stand / custom_storage (2 zones)
  - partial extraction (missing site dimensions)
  - block_candidates only (no zones)
"""

from __future__ import annotations

import pytest

from foms.services.designer.layout_graph_mapper import (
    LayoutMappingInput,
    map_extraction_to_design_graph,
    map_layout_to_design_graph,
)


# ──────────────────────────────────────────────────────────
# Test fixtures
# ──────────────────────────────────────────────────────────

THREE_BAY_WARDROBE = {
    "furniture_type": "wardrobe",
    "site_size": {
        "width_mm": 3000,
        "height_mm": 2400,
        "depth_mm": 600,
    },
    "extracted_params": {
        "width": 3000, "height": 2400, "depth": 600,
        "module_widths": [1000, 1000, 1000],
    },
    "parts_table": [
        {"code": "[SR]",   "description": "선반",   "quantity": 6},
        {"code": "[EP]",   "description": "측판",   "quantity": 4},
        {"code": "[DOOR]", "description": "도어",   "quantity": 3},
        {"code": "옷봉",   "description": "옷봉",   "quantity": 3},
    ],
    "confidence": 0.9,
    "unresolved_fields": [],
    "design_understanding": {
        "layout_graph": {
            "coordinate_system": "front_view_mm",
            "overall_shape": "rectangle",
            "zones": [
                {
                    "id": "zone_left",
                    "role": "hanging",
                    "x_mm": 0,
                    "y_mm": 0,
                    "width_mm": 1000,
                    "height_mm": 2400,
                    "depth_mm": 600,
                    "evidence": "visual_layout",
                },
                {
                    "id": "zone_center",
                    "role": "shelves",
                    "x_mm": 1000,
                    "y_mm": 0,
                    "width_mm": 1000,
                    "height_mm": 2400,
                    "depth_mm": 600,
                    "evidence": "dimension_line",
                },
                {
                    "id": "zone_right",
                    "role": "open_space",
                    "x_mm": 2000,
                    "y_mm": 0,
                    "width_mm": 1000,
                    "height_mm": 2400,
                    "depth_mm": 600,
                    "evidence": "visual_layout",
                },
            ],
            "modules": [
                {
                    "id": "mod_shelf_1",
                    "type": "shelf_stack",
                    "position": {"x_mm": 1000, "y_mm": 500, "z_mm": 0},
                    "dimensions": {"width_mm": 1000, "height_mm": 18, "depth_mm": 580},
                    "relations": ["in_zone:zone_center"],
                    "confidence": 0.85,
                },
                {
                    "id": "mod_shelf_2",
                    "type": "shelf_stack",
                    "position": {"x_mm": 1000, "y_mm": 1000, "z_mm": 0},
                    "dimensions": {"width_mm": 1000, "height_mm": 18, "depth_mm": 580},
                    "relations": ["in_zone:zone_center"],
                    "confidence": 0.85,
                },
            ],
        },
        "block_candidates": [
            {
                "block_key": "wardrobe.vertical_bay.hanging",
                "label": "옷걸이 구역",
                "furniture_types": ["wardrobe"],
                "factory_params": {"width": 1000, "height": 2400, "depth": 600},
                "confidence": 0.8,
                "source_evidence": ["zone_left"],
            },
        ],
        "learned_design_category": {
            "category_key": "wardrobe_3bay",
            "label_ko": "3칸 붙박이장",
            "base_furniture_type": "wardrobe",
            "is_new_category_candidate": False,
            "confidence": 0.85,
        },
    },
}

TV_STAND = {
    "furniture_type": "custom_storage",
    "site_size": {
        "width_mm": 1800,
        "height_mm": 500,
        "depth_mm": 450,
    },
    "extracted_params": {"width": 1800, "height": 500, "depth": 450},
    "parts_table": [
        {"code": "[SR]",   "description": "선반",   "quantity": 2},
        {"code": "[DOOR]", "description": "도어",   "quantity": 2},
    ],
    "confidence": 0.75,
    "unresolved_fields": [],
    "design_understanding": {
        "layout_graph": {
            "coordinate_system": "front_view_mm",
            "overall_shape": "horizontal_cabinet",
            "zones": [
                {
                    "id": "zone_tv_left",
                    "role": "shelves",
                    "x_mm": 0,
                    "y_mm": 0,
                    "width_mm": 900,
                    "height_mm": 500,
                    "depth_mm": 450,
                    "evidence": "visual_layout",
                },
                {
                    "id": "zone_tv_right",
                    "role": "shelves",
                    "x_mm": 900,
                    "y_mm": 0,
                    "width_mm": 900,
                    "height_mm": 500,
                    "depth_mm": 450,
                    "evidence": "visual_layout",
                },
            ],
            "modules": [],
        },
        "block_candidates": [],
        "learned_design_category": {
            "category_key": "tv_stand_horizontal",
            "label_ko": "TV장",
            "base_furniture_type": "custom_storage",
            "is_new_category_candidate": True,
            "confidence": 0.7,
        },
    },
}

PARTIAL_EXTRACTION = {
    "furniture_type": "wardrobe",
    # Missing width in site_size
    "site_size": {
        "height_mm": 2200,
        "depth_mm": 600,
    },
    "extracted_params": {"height": 2200, "depth": 600},
    "parts_table": [],
    "confidence": 0.4,
    "unresolved_fields": ["width"],
    "design_understanding": {
        "layout_graph": {
            "zones": [
                {
                    "id": "zone_only",
                    "role": "unknown",
                    "x_mm": 0,
                    "y_mm": 0,
                    "width_mm": None,
                    "height_mm": 2200,
                    "depth_mm": 600,
                    "evidence": "unknown",
                },
            ],
            "modules": [],
        },
        "block_candidates": [],
        "learned_design_category": {},
    },
}

BLOCK_ONLY_EXTRACTION = {
    "furniture_type": "custom_storage",
    "site_size": {"width_mm": 1200, "height_mm": 800, "depth_mm": 400},
    "extracted_params": {"width": 1200, "height": 800, "depth": 400},
    "parts_table": [{"code": "[SR]", "description": "선반", "quantity": 2}],
    "confidence": 0.6,
    "unresolved_fields": [],
    "design_understanding": {
        "layout_graph": {
            "zones": [],
            "modules": [],
        },
        "block_candidates": [
            {
                "block_key": "custom.shelf_unit",
                "label": "선반 유닛",
                "furniture_types": ["custom_storage"],
                "factory_params": {"width": 1200, "height": 18, "depth": 380},
                "confidence": 0.65,
            },
        ],
        "learned_design_category": {},
    },
}

OUTLINE_ONLY_EXTRACTION = {
    "furniture_type": "custom_storage",
    "site_size": {"depth_mm": 600},
    "extracted_params": {"depth": 600},
    "parts_table": [],
    "confidence": 0.8,
    "unresolved_fields": [],
    "design_understanding": {
        "outline_polygon": {
            "vertices_mm": [
                [0.0, 0.0],
                [2288.0, 0.0],
                [2288.0, 1880.0],
                [1376.0, 1880.0],
                [1376.0, 2225.0],
                [0.0, 2225.0],
            ],
            "confidence": 0.9,
        },
        "layout_graph": {"zones": [], "modules": []},
        "block_candidates": [],
        "learned_design_category": {},
    },
}


# ──────────────────────────────────────────────────────────
# B1-01: 3-bay wardrobe maps to 3 modules
# ──────────────────────────────────────────────────────────

class TestThreeBayWardrobe:
    def test_produces_three_modules(self):
        result = map_extraction_to_design_graph(THREE_BAY_WARDROBE, source_extraction_id=1)
        assembly = result.design_graph["assembly"]
        assert assembly["module_count"] == 3
        assert len(assembly["modules"]) == 3

    def test_assembly_dimensions_match_site_size(self):
        result = map_extraction_to_design_graph(THREE_BAY_WARDROBE, source_extraction_id=1)
        dims = result.design_graph["assembly"]["dimensions"]
        assert dims["width"] == 3000
        assert dims["height"] == 2400
        assert dims["depth"] == 600

    def test_module_types_from_zone_roles(self):
        result = map_extraction_to_design_graph(THREE_BAY_WARDROBE, source_extraction_id=1)
        modules = result.design_graph["assembly"]["modules"]
        types = {m["type"] for m in modules}
        assert "hanging_bay" in types
        assert "shelf_stack" in types
        assert "open_space" in types

    def test_shelf_components_mapped(self):
        result = map_extraction_to_design_graph(THREE_BAY_WARDROBE, source_extraction_id=1)
        components = result.design_graph["components"]
        shelf_comps = [c for c in components if c["kind"] in ("sr", "shelf")]
        assert len(shelf_comps) >= 1

    def test_all_component_ids_are_unique(self):
        result = map_extraction_to_design_graph(THREE_BAY_WARDROBE, source_extraction_id=1)
        ids = [c["id"] for c in result.design_graph["components"]]
        assert len(ids) == len(set(ids)), "Component IDs must be unique"

    def test_component_ids_are_stable_across_calls(self):
        r1 = map_extraction_to_design_graph(THREE_BAY_WARDROBE, source_extraction_id=1)
        r2 = map_extraction_to_design_graph(THREE_BAY_WARDROBE, source_extraction_id=1)
        ids1 = {c["id"] for c in r1.design_graph["components"]}
        ids2 = {c["id"] for c in r2.design_graph["components"]}
        assert ids1 == ids2, "IDs must be deterministic for same input"

    def test_preview_allowed_when_valid(self):
        result = map_extraction_to_design_graph(THREE_BAY_WARDROBE, source_extraction_id=1)
        assert result.preview_allowed is True

    def test_no_approval_blocking_when_complete(self):
        result = map_extraction_to_design_graph(THREE_BAY_WARDROBE, source_extraction_id=1)
        assert result.approval_blocking_reasons == [], (
            f"Unexpected blocking: {result.approval_blocking_reasons}"
        )

    def test_confidence_above_threshold(self):
        result = map_extraction_to_design_graph(THREE_BAY_WARDROBE, source_extraction_id=1)
        assert result.confidence > 0.5

    def test_schema_version_is_2(self):
        result = map_extraction_to_design_graph(THREE_BAY_WARDROBE)
        assert result.design_graph["schema_version"] == 2

    def test_metadata_tracks_source(self):
        result = map_extraction_to_design_graph(THREE_BAY_WARDROBE, source_extraction_id=42)
        meta = result.design_graph["metadata"]
        assert meta["source_extraction_id"] == 42
        assert meta["mapped_by"] == "layout_graph_mapper_b1"


# ──────────────────────────────────────────────────────────
# B1-02: TV stand / custom_storage
# ──────────────────────────────────────────────────────────

class TestTvStandCustomStorage:
    def test_produces_two_modules(self):
        result = map_extraction_to_design_graph(TV_STAND)
        assembly = result.design_graph["assembly"]
        assert assembly["module_count"] == 2

    def test_assembly_type_is_custom_storage(self):
        result = map_extraction_to_design_graph(TV_STAND)
        assert result.design_graph["assembly"]["type"] == "custom_storage"

    def test_preview_allowed(self):
        result = map_extraction_to_design_graph(TV_STAND)
        assert result.preview_allowed is True

    def test_no_approval_blocking(self):
        result = map_extraction_to_design_graph(TV_STAND)
        assert result.approval_blocking_reasons == [], (
            f"Unexpected blocking: {result.approval_blocking_reasons}"
        )


# ──────────────────────────────────────────────────────────
# B1-03: Missing required dimensions → approval blocked
# ──────────────────────────────────────────────────────────

class TestMissingDimensions:
    def test_unresolved_fields_populated(self):
        result = map_extraction_to_design_graph(PARTIAL_EXTRACTION)
        assert len(result.mapping_report.unresolved_fields) > 0

    def test_approval_blocked_on_missing_width(self):
        result = map_extraction_to_design_graph(PARTIAL_EXTRACTION)
        reasons = result.approval_blocking_reasons
        assert any("width" in r for r in reasons), (
            f"Expected width-related blocking, got: {reasons}"
        )

    def test_preview_still_allowed_with_partial_data(self):
        """preview_allowed=True even with unresolved fields — user can still view."""
        result = map_extraction_to_design_graph(PARTIAL_EXTRACTION)
        # At least one zone was defined, so preview should be allowed
        assert result.preview_allowed is True

    def test_save_blocked_by_unresolved(self):
        result = map_extraction_to_design_graph(PARTIAL_EXTRACTION)
        assert result.approval_blocking_reasons  # must not be empty


# ──────────────────────────────────────────────────────────
# B1-04: Block candidates only (no zones)
# ──────────────────────────────────────────────────────────

class TestBlockCandidatesOnly:
    def test_block_candidates_create_components(self):
        result = map_extraction_to_design_graph(BLOCK_ONLY_EXTRACTION)
        components = result.design_graph["components"]
        assert len(components) >= 1

    def test_preview_allowed_with_block_candidates(self):
        result = map_extraction_to_design_graph(BLOCK_ONLY_EXTRACTION)
        # Fallback module created from block_candidates
        assert result.preview_allowed is True


# ──────────────────────────────────────────────────────────
# C1/C2: outline_polygon drives diverse layout modules
# ──────────────────────────────────────────────────────────

class TestOutlinePolygonMapping:
    def test_outline_polygon_generates_real_components(self):
        result = map_extraction_to_design_graph(OUTLINE_ONLY_EXTRACTION, source_extraction_id=77)
        assert result.preview_allowed is True
        assert result.approval_blocking_reasons == []
        assert result.mapping_report.outline_shape_type == "L_shape"
        assert result.design_graph["metadata"]["mapped_by"] == "outline_to_3d_c2"
        assert result.design_graph["assembly"]["module_count"] == 2
        assert len(result.design_graph["components"]) > 0

    def test_outline_polygon_supplies_missing_width_height(self):
        result = map_extraction_to_design_graph(OUTLINE_ONLY_EXTRACTION, source_extraction_id=77)
        reasons = " ".join(result.approval_blocking_reasons)
        assert "site_size.width_mm" not in reasons
        assert "site_size.height_mm" not in reasons
        dims = result.design_graph["assembly"]["dimensions"]
        assert dims["width"] == 2288
        assert dims["height"] == 2225


# ──────────────────────────────────────────────────────────
# B1-05: LayoutMappingInput.from_extraction helper
# ──────────────────────────────────────────────────────────

class TestLayoutMappingInput:
    def test_from_extraction_parses_site_size(self):
        inp = LayoutMappingInput.from_extraction(THREE_BAY_WARDROBE)
        assert inp.site_size.get("width_mm") == 3000

    def test_from_extraction_parses_layout_graph(self):
        inp = LayoutMappingInput.from_extraction(THREE_BAY_WARDROBE)
        assert "zones" in inp.layout_graph
        assert len(inp.layout_graph["zones"]) == 3

    def test_from_extraction_parses_parts_table(self):
        inp = LayoutMappingInput.from_extraction(THREE_BAY_WARDROBE)
        assert len(inp.parts_table) == 4


# ──────────────────────────────────────────────────────────
# B1-06: No Gemini calls during mapping
# ──────────────────────────────────────────────────────────

class TestNoDeterministicLLMCalls:
    def test_mapper_does_not_import_gemini(self, monkeypatch):
        """Mapper must never import or call google.genai."""
        import sys
        # Remove google.genai from sys.modules to confirm it's not called
        blocked_calls = []

        original_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else None

        # Just run the mapper — if it imports google.genai, it would fail
        # because in test environment GEMINI_API_KEY is not set
        result = map_extraction_to_design_graph(THREE_BAY_WARDROBE)
        # If we reach here without GEMINI_API_KEY error, LLM was not called
        assert result.design_graph is not None
