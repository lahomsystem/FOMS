"""PV2-B2 Factory Registry tests."""

from __future__ import annotations

import pytest

from foms.services.designer.factory_registry import (
    create_assembly,
    default_params,
    get_registered_types,
    validate_params,
    FURNITURE_TYPES,
)
from foms.services.designer.constraint_engine import validate_design_graph


class TestRegisteredTypes:
    def test_wardrobe_is_registered(self):
        assert "wardrobe" in get_registered_types()

    def test_all_furniture_types_known(self):
        assert FURNITURE_TYPES == {"wardrobe", "shoe_rack", "kitchen_base", "kitchen_wall", "custom_storage"}

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown furniture type"):
            create_assembly("flying_saucer", {})

    def test_validate_params_unknown_type(self):
        errors = validate_params("unknown_type", {})
        assert len(errors) > 0


class TestWardrobeViaRegistry:
    def test_create_wardrobe(self):
        graph = create_assembly("wardrobe", {
            "width": 2400, "height": 2200, "depth": 600,
            "module_count": 2, "door_type": "sliding",
        })
        assert graph.schema_version == 2
        assert graph.assembly.type == "wardrobe"

    def test_wardrobe_validator_passes(self):
        graph = create_assembly("wardrobe", {
            "width": 3000, "height": 2400, "depth": 620,
            "module_count": 3, "door_type": "sliding",
        })
        result = validate_design_graph(graph)
        errors = [v for v in result.violations if v.severity == "error"]
        assert errors == []

    def test_wardrobe_default_params(self):
        params = default_params("wardrobe")
        assert "width" in params
        assert "height" in params
        assert "module_count" in params

    def test_wardrobe_invalid_params(self):
        errors = validate_params("wardrobe", {"width": -1, "height": 2200, "depth": 600, "module_count": 2})
        assert any("width" in e for e in errors)

    def test_wardrobe_invalid_module_count(self):
        errors = validate_params("wardrobe", {
            "width": 2400, "height": 2200, "depth": 600,
            "module_count": 99, "door_type": "sliding"
        })
        assert any("module_count" in e for e in errors)

    def test_wardrobe_invalid_door_type(self):
        errors = validate_params("wardrobe", {
            "width": 2400, "height": 2200, "depth": 600,
            "module_count": 2, "door_type": "portal"
        })
        assert any("door_type" in e for e in errors)


class TestRegistryOutputContract:
    def test_output_is_schema_v2(self):
        graph = create_assembly("wardrobe", {"width": 2400, "height": 2200, "depth": 600, "module_count": 2})
        assert graph.schema_version == 2

    def test_output_passes_validator(self):
        graph = create_assembly("wardrobe", {"width": 2400, "height": 2200, "depth": 600, "module_count": 2})
        result = validate_design_graph(graph)
        assert result.valid

    def test_output_has_uuid_components(self):
        graph = create_assembly("wardrobe", {"width": 2400, "height": 2200, "depth": 600, "module_count": 2})
        for comp in graph.components:
            assert comp.id and len(comp.id) > 0

    def test_no_duplicate_uuids(self):
        graph = create_assembly("wardrobe", {"width": 2400, "height": 2200, "depth": 600, "module_count": 3})
        ids = [c.id for c in graph.components]
        assert len(ids) == len(set(ids))


class TestGenerateLayoutViaRegistry:
    def test_regenerate_layout(self):
        from foms.services.designer.assembly_factories import WardrobeParams, create_wardrobe_assembly
        from foms.services.designer.command_engine import regenerate_layout_via_registry

        graph = create_wardrobe_assembly(WardrobeParams(width=2400, height=2200, depth=600, module_count=2))
        new_graph = regenerate_layout_via_registry(graph, extra_params={"module_count": 3})
        assert new_graph.assembly.module_count == 3
        result = validate_design_graph(new_graph)
        assert result.valid

    def test_regenerate_door_type(self):
        from foms.services.designer.assembly_factories import WardrobeParams, create_wardrobe_assembly
        from foms.services.designer.command_engine import regenerate_layout_via_registry

        graph = create_wardrobe_assembly(WardrobeParams(width=2400, height=2200, depth=600, door_type="sliding"))
        new_graph = regenerate_layout_via_registry(graph, extra_params={"door_type": "open"})
        assert new_graph.assembly.door_type == "open"
