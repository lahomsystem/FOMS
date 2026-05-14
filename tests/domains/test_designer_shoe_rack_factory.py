"""PV2-B3 Shoe Rack Factory tests."""

from __future__ import annotations

import pytest

from foms.services.designer.factories.shoe_rack import (
    ShoeRackParams,
    create_shoe_rack_assembly,
    MIN_SHELF_PITCH,
    MAX_SHELF_PITCH,
    MAX_DEPTH,
)
from foms.services.designer.factory_registry import (
    create_assembly,
    validate_params,
    get_registered_types,
)
from foms.services.designer.constraint_engine import validate_design_graph


class TestShoeRackRegistration:
    def test_shoe_rack_registered(self):
        assert "shoe_rack" in get_registered_types()


class TestShoeRackFixture:
    def _make(self, **kwargs) -> object:
        defaults = dict(width=800, height=1200, depth=350, tier_count=4, door_type="open")
        defaults.update(kwargs)
        return create_shoe_rack_assembly(ShoeRackParams(**defaults))

    def test_schema_v2(self):
        graph = self._make()
        assert graph.schema_version == 2

    def test_assembly_type(self):
        graph = self._make()
        assert graph.assembly.type == "shoe_rack"

    def test_800w_1200h_350d_4tier_fixture(self):
        graph = create_shoe_rack_assembly(ShoeRackParams(
            width=800, height=1200, depth=350, tier_count=4,
        ))
        result = validate_design_graph(graph)
        errors = [v for v in result.violations if v.severity == "error"]
        assert errors == [], f"Errors: {[v.message for v in errors]}"

    def test_no_duplicate_uuids(self):
        graph = self._make()
        ids = [c.id for c in graph.components]
        assert len(ids) == len(set(ids))

    def test_tiers_present(self):
        graph = self._make(tier_count=4)
        shelves = [c for c in graph.components if c.kind == "shelf" and "선반" in c.name]
        assert len(shelves) == 4

    def test_validator_passes(self):
        graph = self._make()
        result = validate_design_graph(graph)
        errors = [v for v in result.violations if v.severity == "error"]
        assert errors == []

    def test_bench_present_when_enabled(self):
        graph = self._make(has_bench=True)
        bench = [c for c in graph.components if "벤치" in c.name]
        assert len(bench) == 1

    def test_no_bench_by_default(self):
        graph = self._make(has_bench=False)
        bench = [c for c in graph.components if "벤치" in c.name]
        assert bench == []

    def test_door_present_for_swing(self):
        graph = self._make(door_type="swing")
        doors = [c for c in graph.components if c.kind == "door"]
        assert len(doors) >= 1

    def test_no_door_for_open(self):
        graph = self._make(door_type="open")
        doors = [c for c in graph.components if c.kind == "door"]
        assert doors == []

    def test_ep_present(self):
        graph = self._make()
        ep_kinds = {c.kind for c in graph.components}
        assert "ep" in ep_kinds

    def test_back_panel_present(self):
        graph = self._make()
        backs = [c for c in graph.components if c.role == "back_panel"]
        assert len(backs) >= 1


class TestShoeRackSubtypeConstraints:
    def test_invalid_depth_exceeds_max(self):
        errors = validate_params("shoe_rack", {"width": 800, "height": 1200, "depth": 600, "tier_count": 4})
        assert any("depth" in e for e in errors)

    def test_invalid_shelf_pitch_too_small(self):
        errors = validate_params("shoe_rack", {
            "width": 800, "height": 1200, "depth": 350,
            "tier_count": 4, "shelf_pitch": 30,
        })
        assert any("pitch" in e for e in errors)

    def test_invalid_shelf_pitch_too_large(self):
        errors = validate_params("shoe_rack", {
            "width": 800, "height": 1200, "depth": 350,
            "tier_count": 4, "shelf_pitch": 500,
        })
        assert any("pitch" in e for e in errors)

    def test_invalid_tier_count(self):
        errors = validate_params("shoe_rack", {
            "width": 800, "height": 1200, "depth": 350, "tier_count": 20,
        })
        assert any("tier_count" in e for e in errors)

    def test_invalid_door_type_for_shoe_rack(self):
        errors = validate_params("shoe_rack", {
            "width": 800, "height": 1200, "depth": 350,
            "tier_count": 4, "door_type": "sliding",
        })
        assert any("door_type" in e for e in errors)

    def test_zero_width_invalid(self):
        errors = validate_params("shoe_rack", {"width": 0, "height": 1200, "depth": 350, "tier_count": 4})
        assert any("width" in e for e in errors)


class TestShoeRackViaRegistry:
    def test_create_via_registry(self):
        graph = create_assembly("shoe_rack", {
            "width": 800, "height": 1200, "depth": 350, "tier_count": 4,
        })
        assert graph.assembly.type == "shoe_rack"

    def test_registry_output_passes_validator(self):
        graph = create_assembly("shoe_rack", {
            "width": 800, "height": 1200, "depth": 350, "tier_count": 4,
        })
        result = validate_design_graph(graph)
        errors = [v for v in result.violations if v.severity == "error"]
        assert errors == []
