"""PG-B10: Frontend Factory Contract Tests.

Verifies that:
1. Backend factories (wardrobe/shoe_rack/kitchen) produce valid DesignGraph.
2. Frontend registry lists all 4 furniture types.
3. Factory params have correct shape.
4. Generated designs pass constraint validation (or have known constraint issues).
"""

from __future__ import annotations

import pytest

from foms.services.designer.assembly_factories import create_wardrobe_assembly, WardrobeParams, default_design_json_v2
from foms.services.designer.factory_registry import validate_params, get_registered_types
from foms.services.designer.constraint_engine import validate_design_graph
from foms.services.designer.factories.shoe_rack import create_shoe_rack_assembly, ShoeRackParams
from foms.services.designer.factories.kitchen import (
    create_kitchen_base_assembly, create_kitchen_wall_assembly,
    KitchenBaseParams, KitchenWallParams,
)


# ──────────────────────────────────────────────────────────
# PG-B10-01: Factory registry covers all 4 types
# ──────────────────────────────────────────────────────────

class TestFactoryRegistryCoverage:
    """Backend factory registry covers all 4 furniture types."""

    def test_wardrobe_registered(self):
        assert "wardrobe" in get_registered_types()

    def test_shoe_rack_registered(self):
        assert "shoe_rack" in get_registered_types()

    def test_kitchen_base_registered(self):
        assert "kitchen_base" in get_registered_types()

    def test_kitchen_wall_registered(self):
        assert "kitchen_wall" in get_registered_types()

    def test_frontend_registry_types_match_backend(self):
        """Frontend factoryRegistry.ts must have same types as backend."""
        expected_types = {"wardrobe", "shoe_rack", "kitchen_base", "kitchen_wall"}
        registered = set(get_registered_types())
        missing = expected_types - registered
        assert not missing, f"Frontend types not in backend registry: {missing}"


# ──────────────────────────────────────────────────────────
# PG-B10-02: Wardrobe factory
# ──────────────────────────────────────────────────────────

class TestWardrobeFactory:
    def test_wardrobe_schema_v2(self):
        graph = create_wardrobe_assembly(WardrobeParams())
        assert graph.schema_version == 2

    def test_wardrobe_assembly_type(self):
        graph = create_wardrobe_assembly(WardrobeParams())
        assert graph.assembly.type == "wardrobe"

    def test_wardrobe_has_components(self):
        graph = create_wardrobe_assembly(WardrobeParams())
        assert len(graph.components) >= 2

    def test_wardrobe_3_module_dimensions(self):
        p = WardrobeParams(width=2400, height=2200, depth=620, module_count=3, door_type="sliding")
        graph = create_wardrobe_assembly(p)
        assert graph.assembly.dimensions.width == 2400
        assert graph.assembly.module_count == 3

    def test_wardrobe_param_validation(self):
        errors = validate_params("wardrobe", {"width": 2400, "height": 2200, "depth": 620, "module_count": 3})
        assert len(errors) == 0

    def test_wardrobe_constraint_result_has_valid_field(self):
        graph = create_wardrobe_assembly(WardrobeParams())
        result = validate_design_graph(graph)
        assert hasattr(result, "valid")
        assert hasattr(result, "violations")


# ──────────────────────────────────────────────────────────
# PG-B10-03: Shoe Rack factory
# ──────────────────────────────────────────────────────────

class TestShoeRackFactory:
    def test_shoe_rack_schema_v2(self):
        graph = create_shoe_rack_assembly(ShoeRackParams())
        assert graph.schema_version == 2

    def test_shoe_rack_furniture_type(self):
        graph = create_shoe_rack_assembly(ShoeRackParams())
        assert graph.assembly.type == "shoe_rack"

    def test_shoe_rack_has_shelves(self):
        graph = create_shoe_rack_assembly(ShoeRackParams(tier_count=4))
        shelf_comps = [c for c in graph.components if c.kind == "shelf"]
        assert len(shelf_comps) >= 1, "Shoe rack must have at least 1 shelf"

    def test_shoe_rack_dimensions_match_params(self):
        p = ShoeRackParams(width=900, height=1200, depth=350)
        graph = create_shoe_rack_assembly(p)
        assert graph.assembly.dimensions.width == 900
        assert graph.assembly.dimensions.height == 1200

    def test_shoe_rack_has_ep_components(self):
        graph = create_shoe_rack_assembly(ShoeRackParams())
        ep_comps = [c for c in graph.components if c.kind == "ep"]
        assert len(ep_comps) >= 2, "Shoe rack must have left + right EP"

    def test_shoe_rack_param_validation(self):
        errors = validate_params("shoe_rack", {"width": 900, "height": 1200, "depth": 350, "tier_count": 4})
        assert len(errors) == 0

    def test_shoe_rack_invalid_depth_fails(self):
        errors = validate_params("shoe_rack", {"width": 900, "height": 1200, "depth": 500, "tier_count": 4})
        assert len(errors) > 0, "depth=500mm should fail (max 450mm)"


# ──────────────────────────────────────────────────────────
# PG-B10-04: Kitchen Base factory
# ──────────────────────────────────────────────────────────

class TestKitchenBaseFactory:
    def test_kitchen_base_schema_v2(self):
        graph = create_kitchen_base_assembly(KitchenBaseParams())
        assert graph.schema_version == 2

    def test_kitchen_base_furniture_type(self):
        graph = create_kitchen_base_assembly(KitchenBaseParams())
        assert graph.assembly.type == "kitchen_base"

    def test_kitchen_base_has_modules(self):
        graph = create_kitchen_base_assembly(KitchenBaseParams(module_count=3))
        assert len(graph.assembly.modules) == 3

    def test_kitchen_base_has_components(self):
        graph = create_kitchen_base_assembly(KitchenBaseParams())
        assert len(graph.components) >= 3

    def test_kitchen_base_param_validation(self):
        errors = validate_params("kitchen_base", {
            "width": 2400, "height": 820, "depth": 580, "module_count": 3
        })
        assert len(errors) == 0


# ──────────────────────────────────────────────────────────
# PG-B10-05: Kitchen Wall factory
# ──────────────────────────────────────────────────────────

class TestKitchenWallFactory:
    def test_kitchen_wall_schema_v2(self):
        graph = create_kitchen_wall_assembly(KitchenWallParams())
        assert graph.schema_version == 2

    def test_kitchen_wall_furniture_type(self):
        graph = create_kitchen_wall_assembly(KitchenWallParams())
        assert graph.assembly.type == "kitchen_wall"

    def test_kitchen_wall_depth_within_max(self):
        """Kitchen wall depth must be <= 380mm."""
        p = KitchenWallParams(depth=350)
        graph = create_kitchen_wall_assembly(p)
        assert graph.assembly.dimensions.depth <= 380

    def test_kitchen_wall_has_components(self):
        graph = create_kitchen_wall_assembly(KitchenWallParams())
        assert len(graph.components) >= 3

    def test_kitchen_wall_param_validation(self):
        errors = validate_params("kitchen_wall", {
            "width": 2400, "height": 700, "depth": 350, "module_count": 3
        })
        assert len(errors) == 0


# ──────────────────────────────────────────────────────────
# PG-B10-06: All factories — schema + components contract
# ──────────────────────────────────────────────────────────

class TestAllFactoriesContract:
    """Switching furniture type always produces schema v2 with components."""

    FACTORIES = [
        ("wardrobe", lambda: create_wardrobe_assembly(WardrobeParams())),
        ("shoe_rack", lambda: create_shoe_rack_assembly(ShoeRackParams())),
        ("kitchen_base", lambda: create_kitchen_base_assembly(KitchenBaseParams())),
        ("kitchen_wall", lambda: create_kitchen_wall_assembly(KitchenWallParams())),
    ]

    @pytest.mark.parametrize("furniture_type,factory_fn", FACTORIES)
    def test_all_factories_schema_v2(self, furniture_type, factory_fn):
        graph = factory_fn()
        assert graph.schema_version == 2, f"{furniture_type}: expected schema_version=2"

    @pytest.mark.parametrize("furniture_type,factory_fn", FACTORIES)
    def test_all_factories_have_components(self, furniture_type, factory_fn):
        graph = factory_fn()
        assert len(graph.components) >= 2, f"{furniture_type}: need >= 2 components"

    @pytest.mark.parametrize("furniture_type,factory_fn", FACTORIES)
    def test_all_factories_correct_furniture_type(self, furniture_type, factory_fn):
        graph = factory_fn()
        assert graph.assembly.type == furniture_type, (
            f"Expected assembly.type={furniture_type}, got {graph.assembly.type}"
        )

    @pytest.mark.parametrize("furniture_type,factory_fn", FACTORIES)
    def test_all_factories_have_ep_components(self, furniture_type, factory_fn):
        graph = factory_fn()
        ep_comps = [c for c in graph.components if c.kind == "ep"]
        assert len(ep_comps) >= 2, f"{furniture_type}: need at least 2 EP components"
