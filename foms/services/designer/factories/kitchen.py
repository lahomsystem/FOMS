"""FOMS Brain Post-V1 — Kitchen Cabinet Factory V1.

PV2-B4: createKitchenBaseAssembly + createKitchenWallAssembly.

Kitchen-specific constraints:
- sink/cooktop cutout must be inside module boundary
- drawer stack height sum must not exceed module inner height
- countertop overhang: 0–50mm front
- wall cabinet depth max: 380mm
- base cabinet depth: standard 560–600mm
"""

from __future__ import annotations

import uuid
import datetime
from dataclasses import dataclass, field

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
# Kitchen constraints
# ──────────────────────────────────────────────────────────

BASE_HEIGHT_STANDARD = 850    # mm (standard kitchen base height incl. countertop)
WALL_DEPTH_MAX = 380          # mm
COUNTERTOP_OVERHANG_MAX = 50  # mm
COUNTERTOP_THICKNESS = 30     # mm
BASE_DEPTH_MIN = 500          # mm
BASE_DEPTH_MAX = 660          # mm
DRAWER_HEIGHT_STANDARD = 200  # mm per drawer


# ──────────────────────────────────────────────────────────
# Params
# ──────────────────────────────────────────────────────────

@dataclass
class KitchenBaseParams:
    width: int = 2400
    height: int = 820           # cabinet body height (excl. countertop)
    depth: int = 580
    module_count: int = 3
    door_type: str = "swing"
    drawer_count: int = 0       # drawers in bottom zone
    sink_cutout: bool = False   # sink opening in countertop
    ep_left: int = 18
    ep_right: int = 18
    panel_thickness: int = 18
    back_thickness: int = 9
    countertop_overhang: int = 30   # mm front overhang


@dataclass
class KitchenWallParams:
    width: int = 2400
    height: int = 700
    depth: int = 350
    module_count: int = 3
    door_type: str = "swing"
    ep_left: int = 18
    ep_right: int = 18
    panel_thickness: int = 18
    back_thickness: int = 9


# ──────────────────────────────────────────────────────────
# Validation
# ──────────────────────────────────────────────────────────

def _validate_base_params(params: dict) -> list[str]:
    errors: list[str] = []
    w = params.get("width", 2400)
    h = params.get("height", 820)
    d = params.get("depth", 580)
    mc = params.get("module_count", 3)
    dt = params.get("door_type", "swing")
    dc = params.get("drawer_count", 0)
    overhang = params.get("countertop_overhang", 30)

    if not isinstance(w, (int, float)) or w <= 0:
        errors.append("width must be > 0")
    if not isinstance(h, (int, float)) or h <= 0:
        errors.append("height must be > 0")
    if not isinstance(d, (int, float)) or d <= 0:
        errors.append("depth must be > 0")
    elif d < BASE_DEPTH_MIN:
        errors.append(f"base cabinet depth {d}mm < minimum {BASE_DEPTH_MIN}mm")
    elif d > BASE_DEPTH_MAX:
        errors.append(f"base cabinet depth {d}mm > maximum {BASE_DEPTH_MAX}mm")
    if not isinstance(mc, int) or mc < 1 or mc > 10:
        errors.append("module_count must be 1–10")
    if dt not in ("swing", "open"):
        errors.append("kitchen base door_type must be swing or open")
    if not isinstance(dc, int) or dc < 0:
        errors.append("drawer_count must be >= 0")
    if dc > 0:
        drawer_stack = dc * DRAWER_HEIGHT_STANDARD
        inner_h = h - 18 * 2  # top and bottom panels
        if drawer_stack > inner_h:
            errors.append(
                f"drawer_stack_height {drawer_stack}mm exceeds inner height {inner_h}mm"
            )
    if not isinstance(overhang, int) or overhang < 0 or overhang > COUNTERTOP_OVERHANG_MAX:
        errors.append(f"countertop_overhang must be 0–{COUNTERTOP_OVERHANG_MAX}mm")
    return errors


def _validate_wall_params(params: dict) -> list[str]:
    errors: list[str] = []
    w = params.get("width", 2400)
    h = params.get("height", 700)
    d = params.get("depth", 350)
    mc = params.get("module_count", 3)
    dt = params.get("door_type", "swing")

    if not isinstance(w, (int, float)) or w <= 0:
        errors.append("width must be > 0")
    if not isinstance(h, (int, float)) or h <= 0:
        errors.append("height must be > 0")
    if not isinstance(d, (int, float)) or d <= 0:
        errors.append("depth must be > 0")
    elif d > WALL_DEPTH_MAX:
        errors.append(f"wall cabinet depth {d}mm > maximum {WALL_DEPTH_MAX}mm")
    if not isinstance(mc, int) or mc < 1 or mc > 10:
        errors.append("module_count must be 1–10")
    if dt not in ("swing", "open"):
        errors.append("kitchen wall door_type must be swing or open")
    return errors


# ──────────────────────────────────────────────────────────
# Base factory
# ──────────────────────────────────────────────────────────

def create_kitchen_base_assembly(params: KitchenBaseParams) -> DesignGraph:
    """Generate schema v2 DesignGraph for kitchen base cabinet."""
    p = params
    t = p.panel_thickness
    bt = p.back_thickness

    assembly_id = _uuid()
    components: list[Component] = []
    relations: list[Relation] = []
    modules: list[Module] = []

    usable_width = p.width - p.ep_left - p.ep_right
    module_width = usable_width // p.module_count
    last_module_width = usable_width - module_width * (p.module_count - 1)
    inner_height = p.height - t * 2

    # ── EP ─────────────────────────────────────────────────
    ep_l = _uuid()
    components.append(Component(
        id=ep_l, kind="ep", role="left_ep", name="좌측 EP",
        parent_id=assembly_id, material_id="PB_18T_WHITE",
        dimensions=Dimensions(p.ep_left, p.height, p.depth - bt),
        position=Position3D(0, 0, 0),
    ))
    ep_r = _uuid()
    components.append(Component(
        id=ep_r, kind="ep", role="right_ep", name="우측 EP",
        parent_id=assembly_id, material_id="PB_18T_WHITE",
        dimensions=Dimensions(p.ep_right, p.height, p.depth - bt),
        position=Position3D(p.width - p.ep_right, 0, 0),
    ))

    # ── Back panel ─────────────────────────────────────────
    back_id = _uuid()
    components.append(Component(
        id=back_id, kind="panel", role="back_panel", name="후판",
        parent_id=assembly_id, material_id="PB_9T_BACK",
        dimensions=Dimensions(p.width, p.height, bt),
        position=Position3D(0, 0, p.depth - bt),
    ))

    # ── Countertop ─────────────────────────────────────────
    ct_id = _uuid()
    ct_depth = p.depth + p.countertop_overhang
    components.append(Component(
        id=ct_id, kind="panel", role="top_panel", name="상판(카운터탑)",
        parent_id=assembly_id, material_id="PB_18T_WHITE",
        dimensions=Dimensions(p.width, COUNTERTOP_THICKNESS, ct_depth),
        position=Position3D(0, p.height, -p.countertop_overhang),
        custom_props={"is_countertop": True, "sink_cutout": p.sink_cutout},
    ))

    # ── Sink cutout marker (if applicable) ──────────────────
    if p.sink_cutout:
        cutout_w = min(600, usable_width - 100)  # standard sink max 600mm
        cutout_id = _uuid()
        components.append(Component(
            id=cutout_id, kind="cutout", role="generic", name="싱크 개구부",
            parent_id=assembly_id, material_id=None,
            dimensions=Dimensions(cutout_w, COUNTERTOP_THICKNESS + 5, p.depth // 2),
            position=Position3D(p.ep_left + (usable_width - cutout_w) // 2, p.height - 5, 0),
            custom_props={"cutout_type": "sink"},
        ))

    # ── Modules ────────────────────────────────────────────
    module_x = p.ep_left

    for mod_idx in range(p.module_count):
        mod_id = _uuid()
        is_last = mod_idx == p.module_count - 1
        mw = last_module_width if is_last else module_width
        mod_comp_ids: list[str] = []

        # Side panel
        side_id = _uuid()
        components.append(Component(
            id=side_id, kind="panel", role="left_side",
            name=f"측판L-{mod_idx + 1}",
            parent_id=mod_id, material_id="PB_18T_WHITE",
            dimensions=Dimensions(t, p.height, p.depth - bt),
            position=Position3D(module_x, 0, 0),
        ))
        mod_comp_ids.append(side_id)

        if is_last:
            r_side_id = _uuid()
            components.append(Component(
                id=r_side_id, kind="panel", role="right_side",
                name=f"측판R-{mod_idx + 1}",
                parent_id=mod_id, material_id="PB_18T_WHITE",
                dimensions=Dimensions(t, p.height, p.depth - bt),
                position=Position3D(module_x + mw - t, 0, 0),
            ))
            mod_comp_ids.append(r_side_id)

        # Bottom panel
        bot_id = _uuid()
        components.append(Component(
            id=bot_id, kind="panel", role="bottom_panel",
            name=f"하판-{mod_idx + 1}",
            parent_id=mod_id, material_id="PB_18T_WHITE",
            dimensions=Dimensions(mw - t * 2, t, p.depth - bt),
            position=Position3D(module_x + t, 0, 0),
        ))
        mod_comp_ids.append(bot_id)

        # Drawers (bottom zone)
        y_cursor = t
        for d_idx in range(p.drawer_count):
            drw_id = _uuid()
            components.append(Component(
                id=drw_id, kind="drawer", role="drawer",
                name=f"서랍-{mod_idx + 1}-{d_idx + 1}",
                parent_id=mod_id, material_id="PB_18T_WHITE",
                dimensions=Dimensions(mw - t * 2 - 4, DRAWER_HEIGHT_STANDARD - 4, p.depth - bt - 40),
                position=Position3D(module_x + t + 2, y_cursor + 2, 20),
            ))
            mod_comp_ids.append(drw_id)
            y_cursor += DRAWER_HEIGHT_STANDARD

        # Door (if swing and remaining height after drawers)
        remaining_h = inner_height - p.drawer_count * DRAWER_HEIGHT_STANDARD
        if p.door_type == "swing" and remaining_h > 100:
            d_door_id = _uuid()
            components.append(Component(
                id=d_door_id, kind="door", role="door",
                name=f"도어-{mod_idx + 1}",
                parent_id=mod_id, material_id="PET_DOOR_WHITE",
                dimensions=Dimensions(mw - t * 2 - 4, remaining_h - 4, t),
                position=Position3D(module_x + t + 2, y_cursor + 2, -t),
            ))
            mod_comp_ids.append(d_door_id)
            relations.append(Relation(from_id=d_door_id, to_id=mod_id, type="covers_front"))

        # Module object
        modules.append(Module(
            id=mod_id, type="kitchen_base",
            name=f"주방 하부장-{mod_idx + 1}",
            dimensions=Dimensions(mw, p.height, p.depth),
            position=Position3D(module_x, 0, 0),
            component_ids=mod_comp_ids,
            door_type=p.door_type,
        ))
        module_x += mw

    assembly = Assembly(
        id=assembly_id, type="kitchen_base", name="주방 하부장",
        dimensions=Dimensions(p.width, p.height, p.depth),
        modules=modules,
        ep_left=p.ep_left, ep_right=p.ep_right, ep_top=0,
        base_height=0, top_sr=0,
        module_count=p.module_count, door_type=p.door_type,
    )

    constraints = [
        Constraint(id="outer_width_sum", type="sum_equals", severity="error"),
        Constraint(id="within_bounds", type="within_bounds", severity="error"),
        Constraint(id="no_duplicate_uuid", type="no_duplicate_uuid", severity="error"),
        Constraint(id="kitchen_drawer_stack", type="gap_rule", severity="error",
                   params={"max_stack_mm": inner_height}),
    ]

    return DesignGraph(
        schema_version=SCHEMA_VERSION, unit="mm",
        assembly=assembly, components=components,
        constraints=constraints, relations=relations,
        metadata={
            "source": "kitchen_base_factory",
            "ontology_version": ONTOLOGY_VERSION,
            "created_at": datetime.datetime.now(datetime.UTC).isoformat(),
            "sink_cutout": p.sink_cutout,
            "drawer_count": p.drawer_count,
        },
    )


# ──────────────────────────────────────────────────────────
# Wall factory
# ──────────────────────────────────────────────────────────

def create_kitchen_wall_assembly(params: KitchenWallParams) -> DesignGraph:
    """Generate schema v2 DesignGraph for kitchen wall cabinet."""
    p = params
    t = p.panel_thickness
    bt = p.back_thickness

    assembly_id = _uuid()
    components: list[Component] = []
    relations: list[Relation] = []
    modules: list[Module] = []

    usable_width = p.width - p.ep_left - p.ep_right
    module_width = usable_width // p.module_count
    last_module_width = usable_width - module_width * (p.module_count - 1)
    inner_height = p.height - t * 2

    # EP
    ep_l = _uuid()
    components.append(Component(
        id=ep_l, kind="ep", role="left_ep", name="좌측 EP",
        parent_id=assembly_id, material_id="PB_18T_WHITE",
        dimensions=Dimensions(p.ep_left, p.height, p.depth - bt),
        position=Position3D(0, 0, 0),
    ))
    ep_r = _uuid()
    components.append(Component(
        id=ep_r, kind="ep", role="right_ep", name="우측 EP",
        parent_id=assembly_id, material_id="PB_18T_WHITE",
        dimensions=Dimensions(p.ep_right, p.height, p.depth - bt),
        position=Position3D(p.width - p.ep_right, 0, 0),
    ))

    # Back panel
    back_id = _uuid()
    components.append(Component(
        id=back_id, kind="panel", role="back_panel", name="후판",
        parent_id=assembly_id, material_id="PB_9T_BACK",
        dimensions=Dimensions(p.width, p.height, bt),
        position=Position3D(0, 0, p.depth - bt),
    ))

    module_x = p.ep_left

    for mod_idx in range(p.module_count):
        mod_id = _uuid()
        is_last = mod_idx == p.module_count - 1
        mw = last_module_width if is_last else module_width
        mod_comp_ids: list[str] = []

        # Side panel
        side_l = _uuid()
        components.append(Component(
            id=side_l, kind="panel", role="left_side",
            name=f"측판L-{mod_idx + 1}",
            parent_id=mod_id, material_id="PB_18T_WHITE",
            dimensions=Dimensions(t, p.height, p.depth - bt),
            position=Position3D(module_x, 0, 0),
        ))
        mod_comp_ids.append(side_l)

        if is_last:
            side_r = _uuid()
            components.append(Component(
                id=side_r, kind="panel", role="right_side",
                name=f"측판R-{mod_idx + 1}",
                parent_id=mod_id, material_id="PB_18T_WHITE",
                dimensions=Dimensions(t, p.height, p.depth - bt),
                position=Position3D(module_x + mw - t, 0, 0),
            ))
            mod_comp_ids.append(side_r)

        # Top panel
        top_p = _uuid()
        components.append(Component(
            id=top_p, kind="panel", role="top_panel",
            name=f"상판-{mod_idx + 1}",
            parent_id=mod_id, material_id="PB_18T_WHITE",
            dimensions=Dimensions(mw - t * 2, t, p.depth - bt),
            position=Position3D(module_x + t, p.height - t, 0),
        ))
        mod_comp_ids.append(top_p)

        # Bottom panel
        bot_p = _uuid()
        components.append(Component(
            id=bot_p, kind="panel", role="bottom_panel",
            name=f"하판-{mod_idx + 1}",
            parent_id=mod_id, material_id="PB_18T_WHITE",
            dimensions=Dimensions(mw - t * 2, t, p.depth - bt),
            position=Position3D(module_x + t, 0, 0),
        ))
        mod_comp_ids.append(bot_p)

        # Shelf
        shelf_id = _uuid()
        components.append(Component(
            id=shelf_id, kind="shelf", role="shelf",
            name=f"선반-{mod_idx + 1}",
            parent_id=mod_id, material_id="PB_18T_WHITE",
            dimensions=Dimensions(mw - t * 2 - 4, t, p.depth - bt - 20),
            position=Position3D(module_x + t + 2, t + (inner_height // 2), 10),
        ))
        mod_comp_ids.append(shelf_id)

        # Door
        if p.door_type == "swing":
            door_h = inner_height - 4
            door_id = _uuid()
            components.append(Component(
                id=door_id, kind="door", role="door",
                name=f"도어-{mod_idx + 1}",
                parent_id=mod_id, material_id="PET_DOOR_WHITE",
                dimensions=Dimensions(mw - t * 2 - 4, door_h, t),
                position=Position3D(module_x + t + 2, t + 2, -t),
            ))
            mod_comp_ids.append(door_id)
            relations.append(Relation(from_id=door_id, to_id=mod_id, type="covers_front"))

        modules.append(Module(
            id=mod_id, type="kitchen_wall",
            name=f"주방 상부장-{mod_idx + 1}",
            dimensions=Dimensions(mw, p.height, p.depth),
            position=Position3D(module_x, 0, 0),
            component_ids=mod_comp_ids,
            door_type=p.door_type,
        ))
        module_x += mw

    assembly = Assembly(
        id=assembly_id, type="kitchen_wall", name="주방 상부장",
        dimensions=Dimensions(p.width, p.height, p.depth),
        modules=modules,
        ep_left=p.ep_left, ep_right=p.ep_right, ep_top=0,
        base_height=0, top_sr=0,
        module_count=p.module_count, door_type=p.door_type,
    )

    constraints = [
        Constraint(id="outer_width_sum", type="sum_equals", severity="error"),
        Constraint(id="within_bounds", type="within_bounds", severity="error"),
        Constraint(id="no_duplicate_uuid", type="no_duplicate_uuid", severity="error"),
        Constraint(id="wall_depth_max", type="max_size", severity="error",
                   params={"max_depth_mm": WALL_DEPTH_MAX}),
    ]

    return DesignGraph(
        schema_version=SCHEMA_VERSION, unit="mm",
        assembly=assembly, components=components,
        constraints=constraints, relations=relations,
        metadata={
            "source": "kitchen_wall_factory",
            "ontology_version": ONTOLOGY_VERSION,
            "created_at": datetime.datetime.now(datetime.UTC).isoformat(),
        },
    )


# ──────────────────────────────────────────────────────────
# Registry hook
# ──────────────────────────────────────────────────────────

def _register_kitchen_factories() -> None:
    """Register kitchen_base and kitchen_wall in the factory registry."""
    import dataclasses
    from foms.services.designer.factory_registry import register

    def _base_defaults() -> dict:
        return {f.name: f.default for f in dataclasses.fields(KitchenBaseParams)
                if f.default is not dataclasses.MISSING}

    def _wall_defaults() -> dict:
        return {f.name: f.default for f in dataclasses.fields(KitchenWallParams)
                if f.default is not dataclasses.MISSING}

    register("kitchen_base", create_kitchen_base_assembly, KitchenBaseParams,
             _base_defaults, _validate_base_params)
    register("kitchen_wall", create_kitchen_wall_assembly, KitchenWallParams,
             _wall_defaults, _validate_wall_params)
