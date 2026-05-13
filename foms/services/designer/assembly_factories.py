"""FOMS Brain Design Kernel V1 — Assembly Factories.

DK-B4: createWardrobeAssembly — built-in wardrobe generator.

Produces a schema v2 DesignGraph with:
- left/right/top EP
- base
- side panels, top/bottom panels, back panel
- module count-based inner boxes
- shelves and doors
- no duplicate UUIDs
- validator passes on output
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Optional

from foms.services.designer.ontology_types import (
    SCHEMA_VERSION,
    ONTOLOGY_VERSION,
    Assembly,
    Component,
    Constraint,
    DesignGraph,
    Dimensions,
    Module,
    Position3D,
    Relation,
)


def _uuid() -> str:
    return str(uuid.uuid4())


# ──────────────────────────────────────────────────────────
# WardrobeParams
# ──────────────────────────────────────────────────────────

@dataclass
class WardrobeParams:
    width: int = 2400           # mm (전체 폭)
    height: int = 2200          # mm (전체 높이)
    depth: int = 600            # mm (전체 깊이)
    module_count: int = 2       # 통 수
    door_type: str = "sliding"  # sliding / swing / open
    ep_left: int = 50           # 좌 EP 폭 mm
    ep_right: int = 50          # 우 EP 폭 mm
    ep_top: int = 50            # 상 EP 높이 mm (선택)
    base_height: int = 60       # 받침대 높이 mm
    top_sr: int = 50            # 상부 SR 높이 mm
    panel_thickness: int = 18   # 일반 판재 두께 mm
    back_thickness: int = 9     # 후판 두께 mm
    shelf_count_per_module: int = 2  # 모듈당 선반 수


def create_wardrobe_assembly(params: WardrobeParams) -> DesignGraph:
    """
    Generate a schema v2 DesignGraph for a built-in wardrobe.

    All UUIDs are unique. Validator passes on output.
    """
    p = params
    t = p.panel_thickness
    bt = p.back_thickness

    # ── assembly root ──────────────────────────────────────
    assembly_id = _uuid()
    asm_dims = Dimensions(width=p.width, height=p.height, depth=p.depth)

    # ── module width calculation ───────────────────────────
    # module_width = (outer_width - ep_left - ep_right) / module_count
    usable_width = p.width - p.ep_left - p.ep_right
    module_width = usable_width // p.module_count
    # distribute remainder to last module
    last_module_width = usable_width - module_width * (p.module_count - 1)

    # inner height per module (below top SR, above base)
    inner_height = p.height - p.top_sr - p.base_height
    # door height = inner_height - gap
    door_height = inner_height - 2

    components: list[Component] = []
    relations: list[Relation] = []
    modules: list[Module] = []

    # ── EP Left ───────────────────────────────────────────
    ep_left_id = _uuid()
    components.append(Component(
        id=ep_left_id,
        kind="ep",
        role="left_ep",
        name="좌측 EP",
        parent_id=assembly_id,
        material_id="PB_18T_WHITE",
        dimensions=Dimensions(width=p.ep_left, height=p.height, depth=p.depth - bt),
        position=Position3D(x=0, y=0, z=0),
        edge_banding={"front": True, "back": False, "left": False, "right": False},
        formula_refs=["side_panel_height"],
    ))

    # ── EP Right ──────────────────────────────────────────
    ep_right_id = _uuid()
    components.append(Component(
        id=ep_right_id,
        kind="ep",
        role="right_ep",
        name="우측 EP",
        parent_id=assembly_id,
        material_id="PB_18T_WHITE",
        dimensions=Dimensions(width=p.ep_right, height=p.height, depth=p.depth - bt),
        position=Position3D(x=p.width - p.ep_right, y=0, z=0),
        edge_banding={"front": True, "back": False, "left": False, "right": False},
        formula_refs=["side_panel_height"],
    ))

    # ── SR Top ────────────────────────────────────────────
    # SR is a spacer batten (not a standard PB sheet) — no material_id
    sr_top_id = _uuid()
    components.append(Component(
        id=sr_top_id,
        kind="sr",
        role="top_sr",
        name="상부 SR",
        parent_id=assembly_id,
        material_id=None,
        dimensions=Dimensions(width=p.width - p.ep_left - p.ep_right, height=p.top_sr, depth=p.depth - bt),
        position=Position3D(x=p.ep_left, y=p.height - p.top_sr, z=0),
        formula_refs=[],
    ))

    # ── Base ──────────────────────────────────────────────
    # Base is a spacer structure — no material_id for V1
    base_id = _uuid()
    components.append(Component(
        id=base_id,
        kind="base",
        role="base",
        name="받침대",
        parent_id=assembly_id,
        material_id=None,
        dimensions=Dimensions(width=p.width - p.ep_left - p.ep_right, height=p.base_height, depth=p.depth - bt - 50),
        position=Position3D(x=p.ep_left, y=0, z=50),
        formula_refs=[],
    ))

    # ── Back Panel ────────────────────────────────────────
    back_panel_id = _uuid()
    components.append(Component(
        id=back_panel_id,
        kind="panel",
        role="back_panel",
        name="후판",
        parent_id=assembly_id,
        material_id="PB_9T_BACK",
        dimensions=Dimensions(width=p.width, height=p.height, depth=bt),
        position=Position3D(x=0, y=0, z=p.depth - bt),
        formula_refs=["back_panel_width", "back_panel_height"],
    ))

    # ── Modules ───────────────────────────────────────────
    module_x = p.ep_left

    for mod_idx in range(p.module_count):
        mod_id = _uuid()
        is_last = mod_idx == p.module_count - 1
        mw = last_module_width if is_last else module_width

        mod_dims = Dimensions(width=mw, height=inner_height, depth=p.depth - bt)
        mod_pos = Position3D(x=module_x, y=p.base_height, z=0)
        module_component_ids: list[str] = []

        # Left side panel of module (shared right EP of previous module or assembly EP)
        left_side_id = _uuid()
        components.append(Component(
            id=left_side_id,
            kind="panel",
            role="left_side",
            name=f"측판L-{mod_idx + 1}",
            parent_id=mod_id,
            material_id="PB_18T_WHITE",
            dimensions=Dimensions(width=t, height=inner_height, depth=p.depth - bt),
            position=Position3D(x=module_x, y=p.base_height, z=0),
            edge_banding={"front": True, "back": False, "left": False, "right": False},
            formula_refs=["inner_height"],
        ))
        module_component_ids.append(left_side_id)

        # Right side panel (only for last module; intermediate modules share)
        if is_last:
            right_side_id = _uuid()
            components.append(Component(
                id=right_side_id,
                kind="panel",
                role="right_side",
                name=f"측판R-{mod_idx + 1}",
                parent_id=mod_id,
                material_id="PB_18T_WHITE",
                dimensions=Dimensions(width=t, height=inner_height, depth=p.depth - bt),
                position=Position3D(x=module_x + mw - t, y=p.base_height, z=0),
                edge_banding={"front": True, "back": False, "left": False, "right": False},
                formula_refs=["inner_height"],
            ))
            module_component_ids.append(right_side_id)

        # Top panel of module
        top_panel_id = _uuid()
        components.append(Component(
            id=top_panel_id,
            kind="panel",
            role="top_panel",
            name=f"상판-{mod_idx + 1}",
            parent_id=mod_id,
            material_id="PB_18T_WHITE",
            dimensions=Dimensions(width=mw - t * 2, height=t, depth=p.depth - bt),
            position=Position3D(x=module_x + t, y=p.base_height + inner_height - t, z=0),
            formula_refs=[],
        ))
        module_component_ids.append(top_panel_id)

        # Bottom panel of module
        bottom_panel_id = _uuid()
        components.append(Component(
            id=bottom_panel_id,
            kind="panel",
            role="bottom_panel",
            name=f"하판-{mod_idx + 1}",
            parent_id=mod_id,
            material_id="PB_18T_WHITE",
            dimensions=Dimensions(width=mw - t * 2, height=t, depth=p.depth - bt),
            position=Position3D(x=module_x + t, y=p.base_height, z=0),
            formula_refs=[],
        ))
        module_component_ids.append(bottom_panel_id)

        # Shelves
        inner_w = mw - t * 2
        inner_h = inner_height - t * 2
        shelf_spacing = inner_h // (p.shelf_count_per_module + 1)

        for s_idx in range(p.shelf_count_per_module):
            shelf_id = _uuid()
            shelf_y = p.base_height + t + shelf_spacing * (s_idx + 1)
            components.append(Component(
                id=shelf_id,
                kind="shelf",
                role="shelf",
                name=f"선반-{mod_idx + 1}-{s_idx + 1}",
                parent_id=mod_id,
                material_id="PB_18T_WHITE",
                dimensions=Dimensions(width=inner_w, height=t, depth=p.depth - bt - 20),
                position=Position3D(x=module_x + t, y=shelf_y, z=0),
                formula_refs=["shelf_width"],
            ))
            module_component_ids.append(shelf_id)

        # Door (if door_type != open)
        if p.door_type != "open" and door_height > 0:
            door_mat = "PET_DOOR_WHITE"
            MAX_SINGLE_DOOR_WIDTH = 900  # mm

            if p.door_type == "sliding":
                # 슬라이딩: 반폭 + overlap (항상 2짝)
                door_w = (mw - 4) // 2 + 2
                for d_idx in range(2):
                    door_id = _uuid()
                    components.append(Component(
                        id=door_id,
                        kind="door",
                        role="door",
                        name=f"도어-{mod_idx + 1}-{d_idx + 1}",
                        parent_id=mod_id,
                        material_id=door_mat,
                        dimensions=Dimensions(width=door_w, height=door_height, depth=t),
                        position=Position3D(x=module_x + 2 + d_idx * (door_w - 2), y=p.base_height + 1, z=-t * (d_idx + 1)),
                        formula_refs=["door_height"],
                    ))
                    module_component_ids.append(door_id)
                    relations.append(Relation(from_id=door_id, to_id=mod_id, type="covers_front"))
            elif p.door_type == "swing":
                # 여닫이: 폭 > MAX_SINGLE_DOOR_WIDTH이면 2짝으로 분할
                if mw > MAX_SINGLE_DOOR_WIDTH * 2:
                    n_doors = 2
                elif mw > MAX_SINGLE_DOOR_WIDTH:
                    n_doors = 2
                else:
                    n_doors = 1
                door_w = (mw - 4) // n_doors
                for d_idx in range(n_doors):
                    door_id = _uuid()
                    components.append(Component(
                        id=door_id,
                        kind="door",
                        role="door",
                        name=f"도어-{mod_idx + 1}-{d_idx + 1}",
                        parent_id=mod_id,
                        material_id=door_mat,
                        dimensions=Dimensions(width=door_w, height=door_height, depth=t),
                        position=Position3D(x=module_x + 2 + d_idx * door_w, y=p.base_height + 1, z=-t),
                        formula_refs=["door_height"],
                    ))
                    module_component_ids.append(door_id)
                    relations.append(Relation(from_id=door_id, to_id=mod_id, type="covers_front"))

        # Create module object
        mod = Module(
            id=mod_id,
            type="storage_box",
            name=f"모듈-{mod_idx + 1}",
            dimensions=mod_dims,
            position=mod_pos,
            component_ids=module_component_ids,
            door_type=p.door_type,
        )
        modules.append(mod)
        module_x += mw

    # ── Assembly ──────────────────────────────────────────
    assembly = Assembly(
        id=assembly_id,
        type="wardrobe",
        name="붙박이장",
        dimensions=asm_dims,
        modules=modules,
        ep_left=p.ep_left,
        ep_right=p.ep_right,
        ep_top=p.ep_top,
        base_height=p.base_height,
        top_sr=p.top_sr,
        module_count=p.module_count,
        door_type=p.door_type,
    )

    # ── Default constraints ────────────────────────────────
    constraints = [
        Constraint(id="outer_width_sum", type="sum_equals", severity="error"),
        Constraint(id="within_bounds", type="within_bounds", severity="error"),
        Constraint(id="max_size", type="max_size", severity="error"),
        Constraint(id="door_gap_rule", type="gap_rule", severity="error"),
        Constraint(id="thickness_rule", type="thickness_rule", severity="warning"),
        Constraint(id="no_duplicate_uuid", type="no_duplicate_uuid", severity="error"),
    ]

    import datetime
    graph = DesignGraph(
        schema_version=SCHEMA_VERSION,
        unit="mm",
        assembly=assembly,
        components=components,
        constraints=constraints,
        relations=relations,
        metadata={
            "source": "assembly_factory",
            "ontology_version": ONTOLOGY_VERSION,
            "created_at": datetime.datetime.utcnow().isoformat(),
        },
    )

    return graph


def default_design_json_v2(
    width: int = 2400,
    height: int = 2200,
    depth: int = 600,
    module_count: int = 2,
    door_type: str = "sliding",
) -> dict:
    """Return default wardrobe as schema v2 dict.

    DK-B4: replaces the old default_design_json() for new projects.
    """
    params = WardrobeParams(
        width=width,
        height=height,
        depth=depth,
        module_count=module_count,
        door_type=door_type,
    )
    graph = create_wardrobe_assembly(params)
    return graph.to_dict()
