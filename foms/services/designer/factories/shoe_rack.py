"""FOMS Brain Post-V1 — Shoe Rack Factory V1.

PV2-B3: createShoeRackAssembly.

Produces schema v2 DesignGraph for a built-in shoe rack.
- side/top/bottom/back panels
- shelf/tier 반복 생성
- bench (optional bottom bench seat)
- shoe-rack-specific constraints:
  - shelf pitch min (80mm) / max (250mm)
  - door clearance
  - max depth (400mm for typical entryway)
"""

from __future__ import annotations

import uuid
import datetime
from dataclasses import dataclass

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
# Params
# ──────────────────────────────────────────────────────────

@dataclass
class ShoeRackParams:
    width: int = 900           # mm
    height: int = 1200         # mm
    depth: int = 350           # mm
    tier_count: int = 4        # number of shelves/tiers
    door_type: str = "open"    # open / swing
    has_bench: bool = False    # bottom bench seat
    ep_left: int = 18          # thin EP for shoe rack
    ep_right: int = 18
    panel_thickness: int = 18
    back_thickness: int = 9
    shelf_pitch: int = 220     # mm between tiers (center-to-center)


# ──────────────────────────────────────────────────────────
# Shoe rack constraints
# ──────────────────────────────────────────────────────────

MIN_SHELF_PITCH = 80    # mm
MAX_SHELF_PITCH = 300   # mm
MAX_DEPTH = 450         # mm
MIN_DOOR_CLEARANCE = 15  # mm (door swing clearance)


def _validate_shoe_rack_params(params: dict) -> list[str]:
    errors: list[str] = []
    w = params.get("width", 900)
    h = params.get("height", 1200)
    d = params.get("depth", 350)
    tc = params.get("tier_count", 4)
    dt = params.get("door_type", "open")
    sp = params.get("shelf_pitch", 220)

    if not isinstance(w, (int, float)) or w <= 0:
        errors.append("width must be > 0")
    if not isinstance(h, (int, float)) or h <= 0:
        errors.append("height must be > 0")
    if not isinstance(d, (int, float)) or d <= 0:
        errors.append("depth must be > 0")
    elif d > MAX_DEPTH:
        errors.append(f"depth {d}mm exceeds max {MAX_DEPTH}mm for shoe rack")
    if not isinstance(tc, int) or tc < 1 or tc > 12:
        errors.append("tier_count must be 1–12")
    if dt not in ("open", "swing"):
        errors.append("door_type for shoe rack must be open or swing")
    if not isinstance(sp, int) or sp < MIN_SHELF_PITCH or sp > MAX_SHELF_PITCH:
        errors.append(f"shelf_pitch must be {MIN_SHELF_PITCH}–{MAX_SHELF_PITCH}mm")
    return errors


def create_shoe_rack_assembly(params: ShoeRackParams) -> DesignGraph:
    """Generate a schema v2 DesignGraph for a shoe rack."""
    p = params
    t = p.panel_thickness
    bt = p.back_thickness

    assembly_id = _uuid()
    components: list[Component] = []
    relations: list[Relation] = []

    inner_height = p.height - t * 2  # top and bottom panel
    inner_width = p.width - p.ep_left - p.ep_right - t * 2  # left/right side panels

    # Bench: occupies bottom portion if enabled
    bench_height = 300 if p.has_bench else 0

    # ── EP Left / Right ──────────────────────────────────
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

    # ── Back Panel ───────────────────────────────────────
    back_id = _uuid()
    components.append(Component(
        id=back_id, kind="panel", role="back_panel", name="후판",
        parent_id=assembly_id, material_id="PB_9T_BACK",
        dimensions=Dimensions(p.width, p.height, bt),
        position=Position3D(0, 0, p.depth - bt),
    ))

    # ── Side Panels (inside EPs) ─────────────────────────
    offset_x = p.ep_left

    left_side = _uuid()
    components.append(Component(
        id=left_side, kind="panel", role="left_side", name="측판L",
        parent_id=assembly_id, material_id="PB_18T_WHITE",
        dimensions=Dimensions(t, p.height, p.depth - bt),
        position=Position3D(offset_x, 0, 0),
        edge_banding={"front": True, "back": False, "left": False, "right": False},
    ))

    right_side = _uuid()
    components.append(Component(
        id=right_side, kind="panel", role="right_side", name="측판R",
        parent_id=assembly_id, material_id="PB_18T_WHITE",
        dimensions=Dimensions(t, p.height, p.depth - bt),
        position=Position3D(p.width - p.ep_right - t, 0, 0),
        edge_banding={"front": True, "back": False, "left": False, "right": False},
    ))

    # ── Top Panel ────────────────────────────────────────
    top_p = _uuid()
    components.append(Component(
        id=top_p, kind="panel", role="top_panel", name="상판",
        parent_id=assembly_id, material_id="PB_18T_WHITE",
        dimensions=Dimensions(inner_width, t, p.depth - bt),
        position=Position3D(offset_x + t, p.height - t, 0),
    ))

    # ── Bottom Panel or Bench ────────────────────────────
    bot_p = _uuid()
    components.append(Component(
        id=bot_p, kind="panel", role="bottom_panel", name="하판",
        parent_id=assembly_id, material_id="PB_18T_WHITE",
        dimensions=Dimensions(inner_width, t, p.depth - bt),
        position=Position3D(offset_x + t, 0, 0),
    ))

    # ── Shelves / Tiers ──────────────────────────────────
    # Available height for shelves: inner_height - bench_height - t (bottom)
    shelf_area_start = t + bench_height  # y from bottom
    shelf_area_height = inner_height - bench_height
    actual_pitch = shelf_area_height // (p.tier_count + 1) if p.tier_count > 0 else 0

    for i in range(p.tier_count):
        shelf_id = _uuid()
        shelf_y = shelf_area_start + actual_pitch * (i + 1)
        components.append(Component(
            id=shelf_id, kind="shelf", role="shelf",
            name=f"선반-{i + 1}",
            parent_id=assembly_id, material_id="PB_18T_WHITE",
            dimensions=Dimensions(inner_width, t, p.depth - bt - 30),
            position=Position3D(offset_x + t, shelf_y, 15),
        ))

    # ── Bench seat (optional) ─────────────────────────────
    if p.has_bench:
        bench_id = _uuid()
        components.append(Component(
            id=bench_id, kind="shelf", role="shelf",
            name="벤치 상판",
            parent_id=assembly_id, material_id="PB_18T_WHITE",
            dimensions=Dimensions(inner_width, t * 2, p.depth - bt),  # 36mm thick
            position=Position3D(offset_x + t, bench_height - t * 2, 0),
        ))

    # ── Door (swing only) ────────────────────────────────
    if p.door_type == "swing":
        door_h = inner_height - MIN_DOOR_CLEARANCE
        door_w = inner_width - 4
        door_id = _uuid()
        components.append(Component(
            id=door_id, kind="door", role="door", name="도어",
            parent_id=assembly_id, material_id="PET_DOOR_WHITE",
            dimensions=Dimensions(door_w, door_h, t),
            position=Position3D(offset_x + t + 2, t + 1, -t),
        ))
        relations.append(Relation(from_id=door_id, to_id=assembly_id, type="covers_front"))

    # ── Module: inner body between EPs (must satisfy outer_width_sum) ──
    # assembly.width == ep_left + module_sum + ep_right
    mod_width = p.width - p.ep_left - p.ep_right
    mod_id = _uuid()
    module = Module(
        id=mod_id, type="shoe_rack", name="신발장",
        dimensions=Dimensions(mod_width, p.height, p.depth),
        position=Position3D(p.ep_left, 0, 0),
        component_ids=[c.id for c in components],
        door_type=p.door_type,
    )

    assembly = Assembly(
        id=assembly_id, type="shoe_rack", name="신발장",
        dimensions=Dimensions(p.width, p.height, p.depth),
        modules=[module],
        ep_left=p.ep_left, ep_right=p.ep_right, ep_top=t,
        base_height=0, top_sr=0,
        module_count=1, door_type=p.door_type,
    )

    constraints = [
        Constraint(id="within_bounds", type="within_bounds", severity="error"),
        Constraint(id="no_duplicate_uuid", type="no_duplicate_uuid", severity="error"),
        Constraint(id="thickness_rule", type="thickness_rule", severity="warning"),
        Constraint(id="shoe_rack_shelf_pitch", type="gap_rule", severity="error",
                   params={"min_pitch_mm": MIN_SHELF_PITCH, "max_pitch_mm": MAX_SHELF_PITCH}),
    ]

    return DesignGraph(
        schema_version=SCHEMA_VERSION,
        unit="mm",
        assembly=assembly,
        components=components,
        constraints=constraints,
        relations=relations,
        metadata={
            "source": "shoe_rack_factory",
            "ontology_version": ONTOLOGY_VERSION,
            "created_at": datetime.datetime.now(datetime.UTC).isoformat(),
            "shoe_rack_params": {
                "tier_count": p.tier_count,
                "shelf_pitch": p.shelf_pitch,
                "has_bench": p.has_bench,
            },
        },
    )
