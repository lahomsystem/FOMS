"""PV2-B4 Kitchen Cabinet Factory tests."""

from __future__ import annotations

import pytest

from foms.services.designer.factories.kitchen import (
    KitchenBaseParams,
    KitchenWallParams,
    create_kitchen_base_assembly,
    create_kitchen_wall_assembly,
    _validate_base_params,
    _validate_wall_params,
    WALL_DEPTH_MAX,
    BASE_DEPTH_MIN,
    BASE_DEPTH_MAX,
    COUNTERTOP_OVERHANG_MAX,
    DRAWER_HEIGHT_STANDARD,
)
from foms.services.designer.factory_registry import (
    create_assembly,
    validate_params,
    get_registered_types,
)
from foms.services.designer.constraint_engine import validate_design_graph


class TestKitchenRegistration:
    def test_kitchen_base_registered(self):
        assert "kitchen_base" in get_registered_types()

    def test_kitchen_wall_registered(self):
        assert "kitchen_wall" in get_registered_types()


class TestKitchenBaseFixture:
    def _make(self, **kwargs) -> object:
        defaults = dict(width=2400, height=820, depth=580, module_count=3, door_type="swing")
        defaults.update(kwargs)
        return create_kitchen_base_assembly(KitchenBaseParams(**defaults))

    def test_schema_v2(self):
        graph = self._make()
        assert graph.schema_version == 2

    def test_assembly_type(self):
        graph = self._make()
        assert graph.assembly.type == "kitchen_base"

    def test_base_validator_passes(self):
        graph = self._make()
        result = validate_design_graph(graph)
        errors = [v for v in result.violations if v.severity == "error"]
        assert errors == [], f"Errors: {[v.message for v in errors]}"

    def test_no_duplicate_uuids(self):
        graph = self._make()
        ids = [c.id for c in graph.components]
        assert len(ids) == len(set(ids))

    def test_countertop_present(self):
        graph = self._make()
        ct = [c for c in graph.components if c.custom_props.get("is_countertop")]
        assert len(ct) == 1

    def test_sink_cutout_present_when_enabled(self):
        graph = self._make(sink_cutout=True)
        cutouts = [c for c in graph.components if c.kind == "cutout"]
        assert len(cutouts) >= 1

    def test_no_cutout_by_default(self):
        graph = self._make(sink_cutout=False)
        cutouts = [c for c in graph.components if c.kind == "cutout"]
        assert cutouts == []

    def test_drawers_present(self):
        graph = self._make(drawer_count=2)
        drawers = [c for c in graph.components if c.kind == "drawer"]
        assert len(drawers) == 2 * 3  # 2 drawers × 3 modules

    def test_doors_present_for_swing(self):
        graph = self._make(door_type="swing")
        doors = [c for c in graph.components if c.kind == "door"]
        assert len(doors) >= 1

    def test_module_count(self):
        graph = self._make(module_count=3)
        assert len(graph.assembly.modules) == 3

    def test_ep_present(self):
        graph = self._make()
        eps = [c for c in graph.components if c.kind == "ep"]
        assert len(eps) == 2


class TestKitchenWallFixture:
    def _make(self, **kwargs) -> object:
        defaults = dict(width=2400, height=700, depth=350, module_count=3, door_type="swing")
        defaults.update(kwargs)
        return create_kitchen_wall_assembly(KitchenWallParams(**defaults))

    def test_schema_v2(self):
        graph = self._make()
        assert graph.schema_version == 2

    def test_assembly_type_kitchen_wall(self):
        graph = self._make()
        assert graph.assembly.type == "kitchen_wall"

    def test_wall_validator_passes(self):
        graph = self._make()
        result = validate_design_graph(graph)
        errors = [v for v in result.violations if v.severity == "error"]
        assert errors == [], f"Errors: {[v.message for v in errors]}"

    def test_no_duplicate_uuids(self):
        graph = self._make()
        ids = [c.id for c in graph.components]
        assert len(ids) == len(set(ids))

    def test_shelves_present(self):
        graph = self._make()
        shelves = [c for c in graph.components if c.kind == "shelf"]
        assert len(shelves) >= 1

    def test_doors_present_for_swing(self):
        graph = self._make(door_type="swing")
        doors = [c for c in graph.components if c.kind == "door"]
        assert len(doors) >= 1


class TestKitchenSubtypeConstraints:
    def test_base_depth_too_shallow(self):
        errors = _validate_base_params({"width": 2400, "height": 820, "depth": 400,
                                        "module_count": 3, "door_type": "swing"})
        assert any("depth" in e for e in errors)

    def test_base_depth_too_deep(self):
        errors = _validate_base_params({"width": 2400, "height": 820, "depth": 800,
                                        "module_count": 3, "door_type": "swing"})
        assert any("depth" in e for e in errors)

    def test_wall_depth_exceeds_max(self):
        errors = _validate_wall_params({"width": 2400, "height": 700, "depth": 500,
                                        "module_count": 3, "door_type": "swing"})
        assert any("depth" in e for e in errors)

    def test_drawer_stack_exceeds_inner_height(self):
        # 5 drawers × 200mm = 1000mm, inner height = 820 - 36 = 784mm → overflow
        errors = _validate_base_params({"width": 2400, "height": 820, "depth": 580,
                                        "module_count": 3, "door_type": "swing",
                                        "drawer_count": 5})
        assert any("drawer_stack" in e for e in errors)

    def test_countertop_overhang_too_large(self):
        errors = _validate_base_params({"width": 2400, "height": 820, "depth": 580,
                                        "module_count": 3, "door_type": "swing",
                                        "countertop_overhang": 100})
        assert any("overhang" in e for e in errors)

    def test_sink_cutout_inside_boundary(self):
        # Should pass validator — sink cutout within width
        graph = create_kitchen_base_assembly(KitchenBaseParams(
            width=2400, height=820, depth=580, module_count=3, sink_cutout=True
        ))
        result = validate_design_graph(graph)
        errors = [v for v in result.violations if v.severity == "error"]
        assert errors == []

    def test_base_invalid_door_type(self):
        errors = _validate_base_params({"width": 2400, "height": 820, "depth": 580,
                                        "module_count": 3, "door_type": "sliding"})
        assert any("door_type" in e for e in errors)


class TestKitchenViaRegistry:
    def test_kitchen_base_via_registry(self):
        graph = create_assembly("kitchen_base", {
            "width": 2400, "height": 820, "depth": 580, "module_count": 3,
        })
        assert graph.assembly.type == "kitchen_base"

    def test_kitchen_wall_via_registry(self):
        graph = create_assembly("kitchen_wall", {
            "width": 2400, "height": 700, "depth": 350, "module_count": 3,
        })
        assert graph.assembly.type == "kitchen_wall"

    def test_base_registry_output_valid(self):
        graph = create_assembly("kitchen_base", {
            "width": 2400, "height": 820, "depth": 580, "module_count": 3,
        })
        result = validate_design_graph(graph)
        errors = [v for v in result.violations if v.severity == "error"]
        assert errors == []

    def test_wall_registry_output_valid(self):
        graph = create_assembly("kitchen_wall", {
            "width": 2400, "height": 700, "depth": 350, "module_count": 3,
        })
        result = validate_design_graph(graph)
        errors = [v for v in result.violations if v.severity == "error"]
        assert errors == []
