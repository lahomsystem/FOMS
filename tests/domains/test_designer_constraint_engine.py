"""DK-B3 Constraint Engine tests."""

from __future__ import annotations

import copy
import pytest

from foms.services.designer.assembly_factories import WardrobeParams, create_wardrobe_assembly
from foms.services.designer.constraint_engine import validate_design_graph, validate_design_graph_from_dict
from foms.services.designer.ontology_types import (
    Component, Dimensions, Position3D, DesignGraph,
)
from foms.services.designer.validator import validate_design


def _make_graph(**kwargs) -> DesignGraph:
    return create_wardrobe_assembly(WardrobeParams(**kwargs))


class TestOuterWidthSum:
    def test_valid_graph_passes(self):
        graph = _make_graph(width=3000, module_count=3)
        result = validate_design_graph(graph)
        outer_width_errors = [
            v for v in result.violations
            if v.constraint_id == "outer_width_sum" and v.severity == "error"
        ]
        assert outer_width_errors == []

    def test_width_mismatch_fails(self):
        graph = _make_graph(width=3000, module_count=3)
        # Force assembly width mismatch
        graph.assembly.dimensions.width = 9999
        result = validate_design_graph(graph)
        outer_errors = [v for v in result.violations if v.code == "OUTER_WIDTH_MISMATCH"]
        assert len(outer_errors) > 0
        assert result.valid is False


class TestComponentWithinParent:
    def test_component_within_parent_passes(self):
        graph = _make_graph(width=2400, height=2200, depth=600, module_count=2)
        result = validate_design_graph(graph)
        boundary_errors = [v for v in result.violations if v.code == "COMPONENT_EXCEEDS_PARENT_WIDTH"]
        assert boundary_errors == []

    def test_component_outside_parent_fails(self):
        graph = _make_graph(width=2400, height=2200, depth=600, module_count=2)
        # Force a component outside bounds
        panel = graph.components[0]
        panel.position.x = 5000  # way outside
        panel.parent_id = None  # parent is assembly (width=2400)
        result = validate_design_graph(graph)
        boundary_errors = [v for v in result.violations if "EXCEEDS_PARENT_WIDTH" in v.code]
        assert len(boundary_errors) > 0


class TestMaterialMaxSize:
    def test_normal_size_passes(self):
        graph = _make_graph(width=2400, height=2200, depth=600, module_count=2)
        result = validate_design_graph(graph)
        mat_errors = [v for v in result.violations if v.constraint_id == "max_size" and v.severity == "error"]
        assert mat_errors == []

    def test_oversized_component_fails(self):
        graph = _make_graph(width=2400, height=2200, depth=600, module_count=2)
        # Force a non-back-panel board to exceed max_width (2440mm)
        # Find a shelf or side panel (not back_panel)
        panel = next(
            (c for c in graph.components if c.kind in ("shelf", "panel") and c.role != "back_panel"),
            None,
        )
        assert panel is not None, "No suitable panel found in factory output"
        panel.dimensions.width = 5000
        panel.material_id = "PB_18T_WHITE"
        result = validate_design_graph(graph)
        mat_errors = [v for v in result.violations if v.code == "MATERIAL_MAX_SIZE_EXCEEDED"]
        assert len(mat_errors) > 0


class TestDoorGap:
    def test_door_height_valid(self):
        graph = _make_graph(width=2400, height=2200, depth=600, module_count=2, door_type="sliding")
        result = validate_design_graph(graph)
        door_errors = [v for v in result.violations if v.code == "DOOR_HEIGHT_EXCEEDS_INNER"]
        assert door_errors == []

    def test_door_too_tall_fails(self):
        graph = _make_graph(width=2400, height=2200, depth=600, module_count=2, door_type="sliding")
        doors = [c for c in graph.components if c.kind == "door"]
        if doors:
            doors[0].dimensions.height = 99999
            result = validate_design_graph(graph)
            door_errors = [v for v in result.violations if v.code == "DOOR_HEIGHT_EXCEEDS_INNER"]
            assert len(door_errors) > 0


class TestPanelThickness:
    def test_normal_thickness_no_warning(self):
        graph = _make_graph(width=2400, height=2200, depth=600, module_count=2)
        result = validate_design_graph(graph)
        # Warnings are ok, but there should be no thickness ERROR
        thickness_errors = [v for v in result.violations if v.code.startswith("PANEL_THICKNESS") and v.severity == "error"]
        assert thickness_errors == []


class TestDuplicateUUID:
    def test_no_duplicates_in_factory(self):
        graph = _make_graph(width=3000, height=2400, depth=620, module_count=3)
        result = validate_design_graph(graph)
        dup_errors = [v for v in result.violations if v.code == "DUPLICATE_COMPONENT_UUID"]
        assert dup_errors == []

    def test_duplicate_uuid_fails(self):
        graph = _make_graph(width=2400, height=2200, depth=600, module_count=2)
        # Inject duplicate
        if len(graph.components) >= 2:
            graph.components[1].id = graph.components[0].id
        result = validate_design_graph(graph)
        dup_errors = [v for v in result.violations if v.code == "DUPLICATE_COMPONENT_UUID"]
        assert len(dup_errors) > 0
        assert result.valid is False


class TestSeverityLevels:
    def test_error_violations_make_invalid(self):
        graph = _make_graph(width=2400, height=2200, depth=600, module_count=2)
        # Force an error
        graph.assembly.dimensions.width = -1
        result = validate_design_graph(graph)
        assert result.valid is False

    def test_warning_violations_do_not_block(self):
        # A design with only warnings should still be valid
        graph = _make_graph(width=2400, height=2200, depth=600, module_count=2, door_type="open")
        result = validate_design_graph(graph)
        errors = result.errors
        # It might have warnings but should pass if no errors
        if not errors:
            assert result.valid is True


class TestValidateDesignDispatch:
    def test_v1_design_dispatches_to_legacy(self):
        v1_design = {
            "schema_version": 1,
            "unit": "mm",
            "cabinet": {"width": 2400, "height": 2200, "depth": 600},
            "components": [],
            "relations": [],
        }
        result = validate_design(v1_design)
        assert result.valid is True

    def test_v2_design_dispatches_to_constraint_engine(self):
        graph = _make_graph(width=2400, height=2200, depth=600, module_count=2)
        d = graph.to_dict()
        result = validate_design(d)
        errors = result.errors
        assert errors == [] or result.valid is True

    def test_v2_invalid_design_fails(self):
        graph = _make_graph(width=2400, height=2200, depth=600, module_count=2)
        d = graph.to_dict()
        # Inject duplicate UUID
        if d["components"]:
            d["components"].append(dict(d["components"][0]))
        result = validate_design(d)
        assert result.valid is False
