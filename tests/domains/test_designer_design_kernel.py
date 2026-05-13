"""DK-B1/B4 Design Kernel tests: Ontology types + Assembly factories."""

from __future__ import annotations

import pytest

from foms.services.designer.ontology_types import (
    SCHEMA_VERSION,
    ONTOLOGY_VERSION,
    COMPONENT_KINDS,
    DOOR_TYPES,
    Assembly,
    Component,
    DesignGraph,
    Dimensions,
    Module,
    Position3D,
)
from foms.services.designer.component_catalog import (
    MATERIAL_CATALOG,
    COMPONENT_KIND_META,
    ROLE_TO_KIND,
    get_material_for_role,
    get_material,
)
from foms.services.designer.assembly_factories import (
    WardrobeParams,
    create_wardrobe_assembly,
    default_design_json_v2,
)
from foms.services.designer.constraint_engine import validate_design_graph


# ──────────────────────────────────────────────────────────
# DK-B1: Ontology Type Freeze
# ──────────────────────────────────────────────────────────

class TestOntologyTypes:
    def test_schema_version_is_2(self):
        assert SCHEMA_VERSION == 2

    def test_ontology_version_string(self):
        assert ONTOLOGY_VERSION == "kernel-v1"

    def test_component_kinds_complete(self):
        required = {"box", "panel", "door", "shelf", "drawer", "ep", "sr", "base", "hardware", "cutout"}
        assert required == COMPONENT_KINDS

    def test_door_types_complete(self):
        assert DOOR_TYPES == {"sliding", "swing", "open"}

    def test_dimensions_round_trip(self):
        d = Dimensions(width=3000, height=2400, depth=620)
        d2 = Dimensions.from_dict(d.to_dict())
        assert d2.width == 3000
        assert d2.height == 2400
        assert d2.depth == 620

    def test_component_round_trip(self):
        comp = Component(
            id="test-uuid",
            kind="panel",
            role="left_side",
            name="좌측판",
            parent_id="module-001",
            material_id="PB_18T_WHITE",
            dimensions=Dimensions(width=18, height=2200, depth=600),
            position=Position3D(x=0, y=0, z=0),
        )
        d = comp.to_dict()
        comp2 = Component.from_dict(d)
        assert comp2.id == "test-uuid"
        assert comp2.kind == "panel"
        assert comp2.dimensions.width == 18

    def test_assembly_round_trip(self):
        asm = Assembly(
            id="asm-001",
            type="wardrobe",
            name="붙박이장",
            dimensions=Dimensions(width=3000, height=2400, depth=620),
            ep_left=50, ep_right=50, ep_top=50,
            base_height=60, top_sr=50,
            module_count=3, door_type="sliding",
        )
        d = asm.to_dict()
        asm2 = Assembly.from_dict(d)
        assert asm2.module_count == 3
        assert asm2.door_type == "sliding"

    def test_design_graph_serialization(self):
        graph = create_wardrobe_assembly(WardrobeParams(width=2400, height=2200, depth=600, module_count=2))
        d = graph.to_dict()
        assert d["schema_version"] == 2
        assert d["unit"] == "mm"
        assert "assembly" in d
        assert "components" in d


class TestMaterialCatalog:
    def test_required_materials_present(self):
        assert "PB_18T_WHITE" in MATERIAL_CATALOG
        assert "MDF_18T" in MATERIAL_CATALOG
        assert "PB_9T_BACK" in MATERIAL_CATALOG
        assert "PET_DOOR_WHITE" in MATERIAL_CATALOG
        assert "HARDWARE_RAIL" in MATERIAL_CATALOG

    def test_pb_18t_thickness(self):
        mat = MATERIAL_CATALOG["PB_18T_WHITE"]
        assert mat.thickness == 18
        assert mat.max_width == 2440
        assert mat.category == "board"

    def test_get_material(self):
        mat = get_material("PB_18T_WHITE")
        assert mat is not None
        assert mat.id == "PB_18T_WHITE"

    def test_get_material_for_role(self):
        assert get_material_for_role("left_ep") == "PB_18T_WHITE"
        assert get_material_for_role("door") == "PET_DOOR_WHITE"

    def test_all_component_kinds_in_meta(self):
        for kind in COMPONENT_KINDS:
            assert kind in COMPONENT_KIND_META, f"Kind '{kind}' not in COMPONENT_KIND_META"

    def test_role_to_kind_all_roles_valid(self):
        for role, kind in ROLE_TO_KIND.items():
            assert kind in COMPONENT_KINDS, f"Role '{role}' maps to invalid kind '{kind}'"


# ──────────────────────────────────────────────────────────
# DK-B4: Assembly Factory
# ──────────────────────────────────────────────────────────

class TestWardrobeFactory:
    def _make_3module(self) -> DesignGraph:
        return create_wardrobe_assembly(WardrobeParams(
            width=3000, height=2400, depth=620,
            module_count=3, door_type="sliding",
        ))

    def test_schema_version_2(self):
        graph = self._make_3module()
        assert graph.schema_version == 2

    def test_assembly_type_wardrobe(self):
        graph = self._make_3module()
        assert graph.assembly.type == "wardrobe"

    def test_module_count(self):
        graph = self._make_3module()
        assert len(graph.assembly.modules) == 3

    def test_no_duplicate_uuid(self):
        graph = self._make_3module()
        ids = [c.id for c in graph.components]
        assert len(ids) == len(set(ids)), "Duplicate component UUIDs found"

    def test_validator_passes(self):
        graph = self._make_3module()
        result = validate_design_graph(graph)
        errors_only = [v for v in result.violations if v.severity == "error"]
        assert errors_only == [], f"Validator errors: {[v.message for v in errors_only]}"

    def test_ep_components_present(self):
        graph = self._make_3module()
        kinds = {c.role for c in graph.components}
        assert "left_ep" in kinds
        assert "right_ep" in kinds

    def test_sr_component_present(self):
        graph = self._make_3module()
        sr_comps = [c for c in graph.components if c.kind == "sr"]
        assert len(sr_comps) >= 1

    def test_base_component_present(self):
        graph = self._make_3module()
        base_comps = [c for c in graph.components if c.kind == "base"]
        assert len(base_comps) >= 1

    def test_back_panel_present(self):
        graph = self._make_3module()
        back = [c for c in graph.components if c.role == "back_panel"]
        assert len(back) >= 1

    def test_shelves_present(self):
        graph = self._make_3module()
        shelves = [c for c in graph.components if c.kind == "shelf"]
        assert len(shelves) >= 3  # 3 modules × 2 shelves minimum

    def test_doors_present_for_sliding(self):
        graph = self._make_3module()
        doors = [c for c in graph.components if c.kind == "door"]
        assert len(doors) >= 1

    def test_no_doors_for_open_type(self):
        graph = create_wardrobe_assembly(WardrobeParams(
            width=2400, height=2200, depth=600,
            module_count=2, door_type="open",
        ))
        doors = [c for c in graph.components if c.kind == "door"]
        assert doors == []

    def test_all_components_have_uuid(self):
        graph = self._make_3module()
        for comp in graph.components:
            assert comp.id, f"Component missing UUID: {comp}"

    def test_default_design_json_v2_is_schema2(self):
        d = default_design_json_v2()
        assert d["schema_version"] == 2

    def test_2module_variant(self):
        graph = create_wardrobe_assembly(WardrobeParams(
            width=2400, height=2200, depth=600,
            module_count=2, door_type="swing",
        ))
        result = validate_design_graph(graph)
        errors = [v for v in result.violations if v.severity == "error"]
        assert errors == [], f"2-module validator errors: {[v.message for v in errors]}"

    def test_4module_variant(self):
        graph = create_wardrobe_assembly(WardrobeParams(
            width=4000, height=2400, depth=620,
            module_count=4, door_type="sliding",
        ))
        result = validate_design_graph(graph)
        errors = [v for v in result.violations if v.severity == "error"]
        assert errors == [], f"4-module validator errors: {[v.message for v in errors]}"
