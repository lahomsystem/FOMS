"""FOMS Brain B1 — Deterministic Layout Graph Mapper.

Maps Gemini design_understanding.layout_graph → FOMS DesignGraph (schema v2).

Contract:
- No LLM calls. Pure deterministic transformation.
- Missing or ambiguous values go to unresolved_fields and warnings — never fabricated.
- All component IDs are stable deterministic UUIDs derived from source evidence keys.
- preview_allowed=True means the 3D editor can show the candidate.
- approval_blocking_reasons=[] is required before approve-and-save is permitted.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────
# Parts table code → component kind/role mapping
# ──────────────────────────────────────────────────────────

_PARTS_CODE_MAP: dict[str, dict[str, str]] = {
    "[SR]":   {"kind": "sr",       "role": "shelf",        "name": "선반"},
    "[EP]":   {"kind": "ep",       "role": "left_ep",      "name": "측판"},
    "[DOOR]": {"kind": "door",     "role": "door",         "name": "도어"},
    "도어":   {"kind": "door",     "role": "door",         "name": "도어"},
    "선반":   {"kind": "sr",       "role": "shelf",        "name": "선반"},
    "서랍":   {"kind": "drawer",   "role": "drawer",       "name": "서랍"},
    "보조목": {"kind": "panel",    "role": "generic",      "name": "보조목"},
    "옷봉":   {"kind": "hardware", "role": "generic",      "name": "옷봉"},
    "[마이다]": {"kind": "hardware", "role": "generic",    "name": "마이다"},
}

# Zone role → Module type mapping
_ZONE_ROLE_TO_MODULE_TYPE: dict[str, str] = {
    "hanging":     "hanging_bay",
    "shelves":     "shelf_stack",
    "drawers":     "drawer_stack",
    "appliance":   "appliance_bay",
    "open_space":  "open_space",
    "unknown":     "storage_box",
}

# Gemini module type → Component kind
_MODULE_TYPE_TO_KIND: dict[str, str] = {
    "vertical_bay":   "box",
    "drawer_stack":   "drawer",
    "shelf_stack":    "shelf",
    "door_panel":     "door",
    "side_panel":     "panel",
    "top_panel":      "panel",
    "bottom_panel":   "panel",
    "rail":           "hardware",
    "hardware":       "hardware",
    "unknown":        "box",
}

_STANDARD_PANEL_THICKNESS = 18  # mm
_MIN_VALID_DIM = 10             # mm — below this is unresolvable
_MAX_VALID_DIM = 15000          # mm


# ──────────────────────────────────────────────────────────
# Input / Output dataclasses
# ──────────────────────────────────────────────────────────

@dataclass
class LayoutMappingInput:
    """Normalized input for layout_graph_mapper."""

    source_extraction_id: int | None = None
    source_candidate_id: int | None = None
    furniture_type: str = "custom_storage"
    site_size: dict[str, Any] = field(default_factory=dict)
    layout_graph: dict[str, Any] = field(default_factory=dict)
    block_candidates: list[dict[str, Any]] = field(default_factory=list)
    parts_table: list[dict[str, Any]] = field(default_factory=list)
    learned_design_category: dict[str, Any] = field(default_factory=dict)
    similar_cases: list[dict[str, Any]] = field(default_factory=list)
    ontology_rules: dict[str, Any] = field(default_factory=dict)
    extracted_params: dict[str, Any] = field(default_factory=dict)
    outline_polygon: dict[str, Any] | None = None

    # Known Korean furniture type names → FOMS canonical English keys
    _KO_FURNITURE_TYPE_MAP: dict[str, str] = field(default_factory=lambda: {
        "수납장": "custom_storage",
        "붙박이장": "wardrobe",
        "신발장": "shoe_rack",
        "주방하부장": "kitchen_base",
        "주방상부장": "kitchen_wall",
        "부엌가구": "kitchen_base",
        "드레스룸": "wardrobe",
        "거실장": "custom_storage",
        "TV장": "custom_storage",
    })

    def __post_init__(self) -> None:
        # Normalize Korean furniture type to English canonical key
        ko_map = {
            "수납장": "custom_storage", "붙박이장": "wardrobe",
            "신발장": "shoe_rack", "주방하부장": "kitchen_base",
            "주방상부장": "kitchen_wall", "부엌가구": "kitchen_base",
            "드레스룸": "wardrobe",
            "거실장": "custom_storage", "TV장": "custom_storage",
        }
        if self.furniture_type in ko_map:
            self.furniture_type = ko_map[self.furniture_type]

    @classmethod
    def from_extraction(cls, extraction: dict[str, Any], **kwargs: Any) -> "LayoutMappingInput":
        """Build LayoutMappingInput from a raw Gemini extraction dict."""
        du = extraction.get("design_understanding") or {}
        ss = extraction.get("site_size") or {}
        ep = extraction.get("extracted_params") or {}

        # site_size may also be inside extracted_params
        if not ss:
            ss = {
                "width_mm": ep.get("width"),
                "height_mm": ep.get("height"),
                "depth_mm": ep.get("depth"),
            }

        outline_polygon = du.get("outline_polygon")  # None when absent or explicitly null

        return cls(
            furniture_type=extraction.get("furniture_type", "custom_storage"),
            site_size=ss,
            layout_graph=du.get("layout_graph") or {},
            block_candidates=du.get("block_candidates") or [],
            parts_table=extraction.get("parts_table") or [],
            learned_design_category=du.get("learned_design_category") or {},
            extracted_params=ep,
            outline_polygon=outline_polygon,
            **kwargs,
        )


@dataclass
class MappingReport:
    """Human-readable report of the mapping result."""

    mapped_components: list[dict[str, Any]] = field(default_factory=list)
    unresolved_fields: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source_evidence: list[str] = field(default_factory=list)
    outline_shape_type: str | None = None  # populated when outline_polygon is valid

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "mapped_components": self.mapped_components,
            "unresolved_fields": self.unresolved_fields,
            "warnings": self.warnings,
            "source_evidence": self.source_evidence,
        }
        if self.outline_shape_type is not None:
            result["outline_shape_type"] = self.outline_shape_type
        return result


@dataclass
class LayoutMappingResult:
    """Output of layout_graph_mapper."""

    design_graph: dict[str, Any] = field(default_factory=dict)
    mapping_report: MappingReport = field(default_factory=MappingReport)
    confidence: float = 0.0
    preview_allowed: bool = False
    approval_blocking_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "design_graph": self.design_graph,
            "mapping_report": self.mapping_report.to_dict(),
            "confidence": self.confidence,
            "preview_allowed": self.preview_allowed,
            "approval_blocking_reasons": self.approval_blocking_reasons,
        }


# ──────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────

def _stable_id(prefix: str, *keys: str) -> str:
    """Generate a deterministic UUID-like id from prefix + keys.

    Uses uuid5 (name-based) so the same inputs always produce the same id,
    making re-mapping idempotent.
    """
    name = f"{prefix}:{'|'.join(str(k) for k in keys)}"
    return str(uuid.uuid5(uuid.NAMESPACE_OID, name))


def _parse_dim(value: Any) -> int | None:
    """Parse a dimension value to int mm, or None if invalid."""
    if value is None:
        return None
    try:
        v = int(float(str(value)))
    except (TypeError, ValueError):
        return None
    if _MIN_VALID_DIM <= v <= _MAX_VALID_DIM:
        return v
    return None


def _parse_coord(value: Any) -> int | None:
    """Parse a coordinate value to int mm, allowing 0 and negative offsets."""
    if value is None:
        return None
    try:
        v = int(float(str(value)))
    except (TypeError, ValueError):
        return None
    if -_MAX_VALID_DIM <= v <= _MAX_VALID_DIM:
        return v
    return None


def _parse_dim_from(source: dict[str, Any], *keys: str) -> int | None:
    """Parse the first valid dimension from a dict key list."""
    for key in keys:
        parsed = _parse_dim(source.get(key))
        if parsed is not None:
            return parsed
    return None


def _parse_coord_from(source: dict[str, Any], *keys: str) -> int | None:
    """Parse the first valid coordinate from a dict key list."""
    for key in keys:
        parsed = _parse_coord(source.get(key))
        if parsed is not None:
            return parsed
    return None


def _parse_site_size(site_size: dict[str, Any]) -> tuple[int | None, int | None, int | None, list[str]]:
    """Extract (width, height, depth, unresolved) from site_size dict."""
    w = _parse_dim_from(site_size, "width_mm", "width")
    h = _parse_dim_from(site_size, "height_mm", "height")
    d = _parse_dim_from(site_size, "depth_mm", "depth")

    unresolved: list[str] = []
    if w is None:
        unresolved.append("site_size.width_mm")
    if h is None:
        unresolved.append("site_size.height_mm")
    if d is None:
        unresolved.append("site_size.depth_mm")

    return w, h, d, unresolved


def _build_parts_index(parts_table: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Build a lookup index from parts_table by normalized code."""
    index: dict[str, list[dict[str, Any]]] = {}
    for part in parts_table:
        code = str(part.get("code") or "").strip().upper()
        if code:
            index.setdefault(code, []).append(part)
        desc = str(part.get("description") or "").strip()
        if desc:
            index.setdefault(desc, []).append(part)
    return index


def _resolve_component_kind_role(
    module_type: str,
    parts_index: dict[str, list[dict[str, Any]]],
    code_hint: str = "",
) -> tuple[str, str]:
    """Resolve (kind, role) from module type and optional parts code hint."""
    code_upper = code_hint.upper()
    for key, mapping in _PARTS_CODE_MAP.items():
        if key.upper() in code_upper or code_upper == key.upper():
            return mapping["kind"], mapping["role"]
    kind = _MODULE_TYPE_TO_KIND.get(module_type, "box")
    role = "generic"
    if kind == "door":
        role = "door"
    elif kind in ("sr", "shelf"):
        role = "shelf"
    elif kind == "drawer":
        role = "drawer"
    elif kind == "panel" and "side" in module_type:
        role = "left_side"
    return kind, role


def _derive_assembly_dimensions_from_geometry(
    asm_w: int | None,
    asm_h: int | None,
    asm_d: int | None,
    modules: list[dict[str, Any]],
    components: list[dict[str, Any]],
    report: MappingReport,
) -> tuple[int | None, int | None, int | None]:
    """Fill missing assembly W/H/D from mapped module/component extents.

    The derived dimensions are for preview geometry only. Missing site_size
    fields remain unresolved so approval still requires human review.
    """
    max_x = max_y = max_z = None

    def absorb(item: dict[str, Any]) -> None:
        nonlocal max_x, max_y, max_z
        dims = item.get("dimensions") or {}
        pos = item.get("position") or {}
        w = _parse_dim(dims.get("width"))
        h = _parse_dim(dims.get("height"))
        d = _parse_dim(dims.get("depth"))
        if w is None or h is None or d is None:
            return
        x = _parse_coord(pos.get("x")) or 0
        y = _parse_coord(pos.get("y")) or 0
        z = _parse_coord(pos.get("z")) or 0
        max_x = max(max_x or 0, x + w)
        max_y = max(max_y or 0, y + h)
        max_z = max(max_z or 0, z + d)

    for module in modules:
        absorb(module)
    for component in components:
        absorb(component)

    derived = {"width": max_x, "height": max_y, "depth": max_z}
    current = {"width": asm_w, "height": asm_h, "depth": asm_d}
    changed: list[str] = []

    if asm_w is None and derived["width"]:
        asm_w = derived["width"]
        changed.append(f"width={asm_w}")
    if asm_h is None and derived["height"]:
        asm_h = derived["height"]
        changed.append(f"height={asm_h}")
    if asm_d is None and derived["depth"]:
        asm_d = derived["depth"]
        changed.append(f"depth={asm_d}")

    if changed:
        missing_axes = [axis for axis, value in current.items() if value is None]
        report.warnings.append(
            "Assembly dimensions derived from mapped geometry for preview: "
            + ", ".join(changed)
            + f" (site_size still unresolved: {','.join(missing_axes)})"
        )

    return asm_w, asm_h, asm_d


def _map_zone_to_module(
    zone: dict[str, Any],
    assembly_w: int | None,
    assembly_h: int | None,
    assembly_d: int | None,
    zone_idx: int,
    extraction_id: str,
) -> tuple[dict[str, Any], list[str], list[str]]:
    """Map a single zone to an Assembly.Module dict.

    Returns: (module_dict, unresolved_fields, warnings)
    """
    zone_id = str(zone.get("id") or f"zone_{zone_idx}")
    role = str(zone.get("role") or "unknown")
    module_type = _ZONE_ROLE_TO_MODULE_TYPE.get(role, "storage_box")

    w = _parse_dim_from(zone, "width_mm", "width")
    h = _parse_dim_from(zone, "height_mm", "height")
    d = _parse_dim_from(zone, "depth_mm", "depth") or assembly_d
    x = _parse_coord_from(zone, "x_mm", "x") or 0
    y = _parse_coord_from(zone, "y_mm", "y") or 0

    unresolved: list[str] = []
    warnings: list[str] = []

    if w is None:
        unresolved.append(f"zone.{zone_id}.width_mm")
    if h is None:
        unresolved.append(f"zone.{zone_id}.height_mm")
    if d is None:
        warnings.append(f"zone.{zone_id}.depth_mm — fallback to assembly depth")
        d = assembly_d or 600

    module_id = _stable_id("module", extraction_id, zone_id)

    module = {
        "id": module_id,
        "type": module_type,
        "name": f"{role} {zone_idx + 1}",
        "dimensions": {
            "width": w or 0,
            "height": h or 0,
            "depth": d or 0,
        },
        "position": {"x": x, "y": y, "z": 0},
        "component_ids": [],
        "door_type": "open",
        "source_zone_id": zone_id,
    }

    return module, unresolved, warnings


def _map_gemini_module_to_component(
    gm: dict[str, Any],
    parent_module_id: str,
    parts_index: dict[str, list[dict[str, Any]]],
    gm_idx: int,
    extraction_id: str,
    zone_id: str,
) -> tuple[dict[str, Any] | None, list[str], list[str]]:
    """Map a Gemini layout_graph.module to a Component dict.

    Returns: (component_dict or None, unresolved_fields, warnings)
    """
    gm_id = str(gm.get("id") or f"gm_{gm_idx}")
    gm_type = str(gm.get("type") or "unknown")
    dims = gm.get("dimensions") or {}
    pos = gm.get("position") or {}

    w = _parse_dim_from(dims, "width_mm", "width")
    h = _parse_dim_from(dims, "height_mm", "height")
    d = _parse_dim_from(dims, "depth_mm", "depth")
    x = _parse_coord_from(pos, "x_mm", "x") or 0
    y = _parse_coord_from(pos, "y_mm", "y") or 0
    z = _parse_coord_from(pos, "z_mm", "z") or 0
    confidence = float(gm.get("confidence") or 0.0)

    unresolved: list[str] = []
    warnings: list[str] = []

    if confidence < 0.3:
        warnings.append(f"component.{gm_id} — low confidence ({confidence:.2f}), review recommended")

    kind, role = _resolve_component_kind_role(gm_type, parts_index)
    comp_id = _stable_id("comp", extraction_id, zone_id, gm_id)

    # Skip if all dimensions missing AND no parent context
    if w is None and h is None:
        unresolved.append(f"component.{gm_id}.dimensions")

    component = {
        "id": comp_id,
        "kind": kind,
        "role": role,
        "name": gm_type.replace("_", " "),
        "parent_id": parent_module_id,
        "material_id": None,
        "dimensions": {
            "width": w or 0,
            "height": h or 0,
            "depth": d or _STANDARD_PANEL_THICKNESS,
        },
        "position": {"x": x, "y": y, "z": z},
        "edge_banding": {},
        "formula_refs": [],
        "custom_props": {
            "source_gemini_type": gm_type,
            "source_gemini_id": gm_id,
            "confidence": confidence,
        },
    }

    return component, unresolved, warnings


def _map_block_candidates_to_components(
    block_candidates: list[dict[str, Any]],
    parent_module_id: str | None,
    extraction_id: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Convert block_candidates to supplementary Component dicts.

    These are lower-priority hints; they do not override zone-derived components.
    """
    components: list[dict[str, Any]] = []
    warnings: list[str] = []

    for i, bc in enumerate(block_candidates):
        block_key = str(bc.get("block_key") or f"block_{i}")
        fp = bc.get("factory_params") or {}
        confidence = float(bc.get("confidence") or 0.0)

        if confidence < 0.2:
            warnings.append(f"block_candidate.{block_key} — very low confidence ({confidence:.2f}), skipped")
            continue

        w = _parse_dim(fp.get("width") or fp.get("width_mm"))
        h = _parse_dim(fp.get("height") or fp.get("height_mm"))
        d = _parse_dim(fp.get("depth") or fp.get("depth_mm")) or _STANDARD_PANEL_THICKNESS

        # Infer kind/role from block_key
        kind, role = "box", "generic"
        lk = block_key.lower()
        if "shelf" in lk or "sr" in lk:
            kind, role = "sr", "shelf"
        elif "door" in lk:
            kind, role = "door", "door"
        elif "drawer" in lk:
            kind, role = "drawer", "drawer"
        elif "ep" in lk or "panel" in lk:
            kind, role = "ep", "generic"

        comp_id = _stable_id("block", extraction_id, block_key)
        components.append({
            "id": comp_id,
            "kind": kind,
            "role": role,
            "name": bc.get("label") or block_key,
            "parent_id": parent_module_id,
            "material_id": None,
            "dimensions": {
                "width": w or 0,
                "height": h or 0,
                "depth": d,
            },
            "position": {"x": 0, "y": 0, "z": 0},
            "edge_banding": {},
            "formula_refs": [],
            "custom_props": {
                "source_block_key": block_key,
                "block_confidence": confidence,
            },
        })

    return components, warnings


# ──────────────────────────────────────────────────────────
# Primary mapping function
# ──────────────────────────────────────────────────────────

def map_layout_to_design_graph(mapping_input: LayoutMappingInput) -> LayoutMappingResult:
    """Map layout_graph extraction to a DesignGraph candidate.

    This is the primary B1 entry point.

    Args:
        mapping_input: Normalized input from Gemini extraction + context.

    Returns:
        LayoutMappingResult with design_graph, mapping_report, preview_allowed,
        approval_blocking_reasons.
    """
    report = MappingReport()
    all_unresolved: list[str] = []
    approval_blocking: list[str] = []
    confidence_factors: list[float] = []

    extraction_id = str(
        mapping_input.source_extraction_id
        or mapping_input.source_candidate_id
        or "unknown"
    )

    # ── 1. Parse overall site dimensions ──────────────────
    asm_w, asm_h, asm_d, site_unresolved = _parse_site_size(mapping_input.site_size)
    all_unresolved.extend(site_unresolved)

    if site_unresolved:
        # Missing overall dimensions are a hard block for approval
        for u in site_unresolved:
            approval_blocking.append(f"unresolved_required_field:{u}")

    # Assembly ID
    asm_id = _stable_id("assembly", extraction_id)
    furniture_type = mapping_input.furniture_type or "custom_storage"

    # ── 1b. Process outline_polygon (C1) ─────────────────
    asm_w, asm_h = _apply_outline_polygon(
        mapping_input.outline_polygon,
        asm_w,
        asm_h,
        report,
        approval_blocking,
    )
    if asm_w is not None:
        _remove_resolution_marker(all_unresolved, approval_blocking, "site_size.width_mm")
    if asm_h is not None:
        _remove_resolution_marker(all_unresolved, approval_blocking, "site_size.height_mm")

    outline_result = _map_valid_outline_polygon(
        mapping_input.outline_polygon,
        asm_d,
        furniture_type,
        extraction_id,
        report,
        approval_blocking,
        mapping_input.source_extraction_id,
        mapping_input.source_candidate_id,
    )
    if outline_result is not None:
        return outline_result

    # ── 2. Parse zones → modules ──────────────────────────
    layout_graph = mapping_input.layout_graph
    zones = layout_graph.get("zones") or []
    gemini_modules = layout_graph.get("modules") or []

    modules: list[dict[str, Any]] = []
    all_components: list[dict[str, Any]] = []
    relations: list[dict[str, Any]] = []

    parts_index = _build_parts_index(mapping_input.parts_table)

    # Map zones to modules
    for i, zone in enumerate(zones):
        module, z_unresolved, z_warnings = _map_zone_to_module(
            zone, asm_w, asm_h, asm_d, i, extraction_id
        )
        all_unresolved.extend(z_unresolved)
        report.warnings.extend(z_warnings)
        modules.append(module)

        # Find gemini modules that belong to this zone
        zone_id = str(zone.get("id") or f"zone_{i}")
        zone_children = [
            gm for gm in gemini_modules
            if _belongs_to_zone(gm, zone)
        ]

        for j, gm in enumerate(zone_children):
            comp, c_unresolved, c_warnings = _map_gemini_module_to_component(
                gm, module["id"], parts_index, j, extraction_id, zone_id
            )
            if comp:
                all_components.append(comp)
                module["component_ids"].append(comp["id"])
                report.mapped_components.append({
                    "component_id": comp["id"],
                    "source": f"layout_graph.modules[{j}]",
                    "kind": comp["kind"],
                })
                # Relation: module contains component
                relations.append({
                    "from": module["id"],
                    "to": comp["id"],
                    "type": "contains_component",
                })
            all_unresolved.extend(c_unresolved)
            report.warnings.extend(c_warnings)

    # ── 3. Add zone-frame components for zones that have no child components ─
    # (e.g. TV stand zones with no gemini modules defined)
    for module in modules:
        if not module.get("component_ids") and module["dimensions"]["width"] > 0:
            zone_comp_id = _stable_id("zone_frame", extraction_id, module["id"])
            zone_frame = {
                "id": zone_comp_id,
                "kind": "box",
                "role": "generic",
                "name": module["name"],
                "parent_id": module["id"],
                "material_id": None,
                "dimensions": {
                    "width": module["dimensions"]["width"],
                    "height": module["dimensions"]["height"],
                    "depth": module["dimensions"]["depth"],
                },
                "position": {"x": module["position"]["x"], "y": 0, "z": 0},
                "edge_banding": {},
                "formula_refs": [],
                "custom_props": {"source": "zone_frame_auto"},
            }
            all_components.append(zone_frame)
            module["component_ids"].append(zone_comp_id)
            report.mapped_components.append({
                "component_id": zone_comp_id,
                "source": f"zone_frame:{module.get('source_zone_id', module['id'])}",
                "kind": "box",
            })

    # ── 4. Fallback: if no zones, try gemini modules directly ─
    if not zones and gemini_modules:
        report.warnings.append("No zones found — using layout_graph.modules directly as components")
        fallback_module = {
            "id": _stable_id("module", extraction_id, "fallback"),
            "type": furniture_type,
            "name": "기본 모듈",
            "dimensions": {
                "width": asm_w or 0,
                "height": asm_h or 0,
                "depth": asm_d or 600,
            },
            "position": {"x": 0, "y": 0, "z": 0},
            "component_ids": [],
            "door_type": "open",
        }
        modules.append(fallback_module)

        for j, gm in enumerate(gemini_modules):
            comp, c_unresolved, c_warnings = _map_gemini_module_to_component(
                gm, fallback_module["id"], parts_index, j, extraction_id, "fallback"
            )
            if comp:
                all_components.append(comp)
                fallback_module["component_ids"].append(comp["id"])
                report.mapped_components.append({
                    "component_id": comp["id"],
                    "source": f"layout_graph.modules[{j}] (fallback)",
                    "kind": comp["kind"],
                })
            all_unresolved.extend(c_unresolved)
            report.warnings.extend(c_warnings)

    # ── 4b. Fallback: build modules from extracted_params.module_widths ──
    # Triggers when layout_graph had no zones/modules (common for custom_storage drawings)
    if not modules:
        mw_list = [
            w for w in (mapping_input.extracted_params.get("module_widths") or [])
            if _parse_dim(w) is not None
        ]
        if mw_list and asm_h:
            report.warnings.append(
                f"No layout_graph zones/modules — building {len(mw_list)} modules "
                "from extracted_params.module_widths"
            )
            x_offset = 0
            for i, raw_mw in enumerate(mw_list):
                mw = _parse_dim(raw_mw) or 0
                mod_id = _stable_id("module", extraction_id, f"epmod_{i}")
                module = {
                    "id": mod_id,
                    "type": furniture_type,
                    "name": f"모듈 {i + 1}",
                    "dimensions": {
                        "width": mw,
                        "height": asm_h,
                        "depth": asm_d or 600,
                    },
                    "position": {"x": x_offset, "y": 0, "z": 0},
                    "component_ids": [],
                    "door_type": "open",
                    "source_ep": f"extracted_params.module_widths[{i}]",
                }
                modules.append(module)
                # Frame component for this module
                comp_id = _stable_id("comp", extraction_id, f"epmod_{i}", "frame")
                comp = {
                    "id": comp_id,
                    "kind": "box",
                    "role": "generic",
                    "name": f"모듈 {i + 1} 프레임",
                    "parent_id": mod_id,
                    "material_id": None,
                    "dimensions": {"width": mw, "height": asm_h, "depth": asm_d or 600},
                    "position": {"x": x_offset, "y": 0, "z": 0},
                    "edge_banding": {},
                    "formula_refs": [],
                    "custom_props": {"source": "extracted_params_module_widths"},
                }
                all_components.append(comp)
                module["component_ids"].append(comp_id)
                report.mapped_components.append({
                    "component_id": comp_id,
                    "source": f"extracted_params.module_widths[{i}]",
                    "kind": "box",
                })
                x_offset += mw

    # ── 5. Block candidates fallback: create module if none exists ─
    if not modules and mapping_input.block_candidates:
        report.warnings.append("No modules from zones — creating fallback module from block_candidates")
        fallback_module = {
            "id": _stable_id("module", extraction_id, "block_fallback"),
            "type": furniture_type,
            "name": "기본 모듈",
            "dimensions": {
                "width": asm_w or 0,
                "height": asm_h or 0,
                "depth": asm_d or 600,
            },
            "position": {"x": 0, "y": 0, "z": 0},
            "component_ids": [],
            "door_type": "open",
        }
        modules.append(fallback_module)

    # ── 5c. Last-resort fallback: overall dimensions box ─────
    # When all other sources failed but we have site dimensions, create a single box
    # so the 3D editor shows something reviewable rather than empty.
    if not modules and asm_w and asm_h:
        report.warnings.append(
            "No structural data found — creating single overview box from site dimensions"
        )
        fb_mod_id = _stable_id("module", extraction_id, "dim_fallback")
        fb_comp_id = _stable_id("comp", extraction_id, "dim_fallback", "box")
        modules.append({
            "id": fb_mod_id,
            "type": furniture_type,
            "name": "전체 박스 (치수 기반)",
            "dimensions": {"width": asm_w, "height": asm_h, "depth": asm_d or 600},
            "position": {"x": 0, "y": 0, "z": 0},
            "component_ids": [fb_comp_id],
            "door_type": "open",
        })
        all_components.append({
            "id": fb_comp_id,
            "kind": "box",
            "role": "generic",
            "name": "전체 박스",
            "parent_id": fb_mod_id,
            "material_id": None,
            "dimensions": {"width": asm_w, "height": asm_h, "depth": asm_d or 600},
            "position": {"x": 0, "y": 0, "z": 0},
            "edge_banding": {},
            "formula_refs": [],
            "custom_props": {"source": "site_dimensions_fallback"},
        })
        report.mapped_components.append({
            "component_id": fb_comp_id,
            "source": "site_dimensions_fallback",
            "kind": "box",
        })

    # ── 6. Block candidates as supplementary components ───
    first_module_id = modules[0]["id"] if modules else None
    block_comps, block_warnings = _map_block_candidates_to_components(
        mapping_input.block_candidates, first_module_id, extraction_id
    )
    report.warnings.extend(block_warnings)
    # Only add block_candidates as components if they don't duplicate existing ones
    existing_kinds = {c["kind"] for c in all_components}
    for bc in block_comps:
        if bc["kind"] not in existing_kinds or bc["custom_props"].get("block_confidence", 0) > 0.7:
            all_components.append(bc)
            if first_module_id:
                for m in modules:
                    if m["id"] == first_module_id:
                        m["component_ids"].append(bc["id"])

    # ── 5. Apply parts table hints to fill material/roles ─
    _apply_parts_table_hints(all_components, mapping_input.parts_table)

    asm_w, asm_h, asm_d = _derive_assembly_dimensions_from_geometry(
        asm_w,
        asm_h,
        asm_d,
        modules,
        all_components,
        report,
    )

    # ── 6. Confidence calculation ─────────────────────────
    overall_conf = layout_graph.get("overall_shape") and 0.5 or 0.3
    if asm_w and asm_h and asm_d:
        overall_conf += 0.2
    if all_components:
        overall_conf += 0.1
    if not all_unresolved:
        overall_conf += 0.2
    learned_conf = float(
        (mapping_input.learned_design_category or {}).get("confidence") or 0.0
    )
    final_conf = min(1.0, (overall_conf + learned_conf) / 2 if learned_conf > 0 else overall_conf)

    # ── 7. Deduplicate unresolved ──────────────────────────
    report.unresolved_fields = list(dict.fromkeys(all_unresolved))

    # ── 8. Determine approval_blocking_reasons ────────────
    if report.unresolved_fields:
        for u in report.unresolved_fields:
            if u not in approval_blocking:
                approval_blocking.append(f"unresolved_field:{u}")

    if not all_components:
        approval_blocking.append("no_components_mapped")

    # ── 9. Build DesignGraph dict ─────────────────────────
    assembly_dict = {
        "id": asm_id,
        "type": furniture_type,
        "name": mapping_input.learned_design_category.get("label_ko") or furniture_type,
        "dimensions": {
            "width": asm_w or 0,
            "height": asm_h or 0,
            "depth": asm_d or 0,
        },
        "modules": modules,
        "ep_left": _STANDARD_PANEL_THICKNESS,
        "ep_right": _STANDARD_PANEL_THICKNESS,
        "ep_top": _STANDARD_PANEL_THICKNESS,
        "base_height": 60,
        "top_sr": _STANDARD_PANEL_THICKNESS,
        "module_count": len(modules),
        "door_type": "open",
    }

    design_graph = {
        "schema_version": 2,
        "unit": "mm",
        "assembly": assembly_dict,
        "components": all_components,
        "constraints": [],
        "relations": relations,
        "metadata": {
            "source_extraction_id": mapping_input.source_extraction_id,
            "source_candidate_id": mapping_input.source_candidate_id,
            "furniture_type": furniture_type,
            "mapped_by": "layout_graph_mapper_b1",
        },
    }

    # ── 10. Run validator ─────────────────────────────────
    validation_errors = _validate_design_graph(design_graph, report)
    for err in validation_errors:
        if err not in approval_blocking:
            approval_blocking.append(err)

    # preview_allowed: True if we have at least one module, even with warnings
    preview_allowed = len(modules) > 0

    report.source_evidence.append(f"extraction_id:{extraction_id}")
    if mapping_input.parts_table:
        report.source_evidence.append(f"parts_table:{len(mapping_input.parts_table)}_rows")
    if mapping_input.block_candidates:
        report.source_evidence.append(f"block_candidates:{len(mapping_input.block_candidates)}_items")

    logger.info(
        "[LAYOUT_MAPPER] extraction_id=%s zones=%d components=%d "
        "unresolved=%d approval_blocking=%d preview=%s",
        extraction_id, len(zones), len(all_components),
        len(report.unresolved_fields), len(approval_blocking), preview_allowed,
    )

    return LayoutMappingResult(
        design_graph=design_graph,
        mapping_report=report,
        confidence=round(final_conf, 4),
        preview_allowed=preview_allowed,
        approval_blocking_reasons=approval_blocking,
    )


# ──────────────────────────────────────────────────────────
# Internal validation helpers
# ──────────────────────────────────────────────────────────

def _apply_outline_polygon(
    outline_polygon: dict[str, Any] | None,
    asm_w: int | None,
    asm_h: int | None,
    report: MappingReport,
    approval_blocking: list[str],
) -> tuple[int | None, int | None]:
    """Process the C1 outline_polygon field and update assembly dimensions.

    - If outline_polygon is None → no action (existing path preserved).
    - If outline_polygon is present but invalid → append blocking reason.
    - If outline_polygon is valid → override asm_w/asm_h from bounding box,
      and record outline_shape_type in the mapping report.

    Args:
        outline_polygon: Dict from design_understanding.outline_polygon or None.
        asm_w: Current assembly width (mm) — may be None.
        asm_h: Current assembly height (mm) — may be None.
        report: MappingReport to update in-place.
        approval_blocking: List to append blocking reasons to.

    Returns:
        Tuple (asm_w, asm_h), potentially updated from bounding box.
    """
    if outline_polygon is None:
        return asm_w, asm_h

    try:
        from foms.services.designer.outline_polygon_validator import validate_polygon
    except ImportError:
        report.warnings.append("outline_polygon_validator not available — skipping C1 validation")
        return asm_w, asm_h

    raw_vertices = outline_polygon.get("vertices_mm")
    if not raw_vertices or not isinstance(raw_vertices, list):
        approval_blocking.append("outline_polygon_invalid:missing_vertices_mm")
        return asm_w, asm_h

    result = validate_polygon(raw_vertices)

    if not result.is_valid:
        approval_blocking.append(f"outline_polygon_invalid:{result.error}")
        logger.warning("[LAYOUT_MAPPER] outline_polygon invalid: %s", result.error)
        return asm_w, asm_h

    # Valid polygon — record shape type in report
    report.outline_shape_type = result.shape_type

    # Compute bounding box and update assembly dimensions
    xs = [v[0] for v in raw_vertices]
    ys = [v[1] for v in raw_vertices]
    bbox_w = _parse_dim(max(xs) - min(xs))
    bbox_h = _parse_dim(max(ys) - min(ys))

    if bbox_w is not None and bbox_w > 0:
        if asm_w is None:
            asm_w = bbox_w
            logger.info("[LAYOUT_MAPPER] asm_w set from outline_polygon bbox: %d", asm_w)
        elif asm_w != bbox_w:
            report.warnings.append(
                f"outline_polygon bbox_w={bbox_w} differs from site_size.width_mm={asm_w} — using site_size"
            )

    if bbox_h is not None and bbox_h > 0:
        if asm_h is None:
            asm_h = bbox_h
            logger.info("[LAYOUT_MAPPER] asm_h set from outline_polygon bbox: %d", asm_h)
        elif asm_h != bbox_h:
            report.warnings.append(
                f"outline_polygon bbox_h={bbox_h} differs from site_size.height_mm={asm_h} — using site_size"
            )

    return asm_w, asm_h


def _remove_resolution_marker(
    unresolved: list[str],
    approval_blocking: list[str],
    field_name: str,
) -> None:
    """Remove missing-site-size markers once outline geometry supplies them."""
    while field_name in unresolved:
        unresolved.remove(field_name)
    marker = f"unresolved_required_field:{field_name}"
    while marker in approval_blocking:
        approval_blocking.remove(marker)


def _map_valid_outline_polygon(
    outline_polygon: dict[str, Any] | None,
    asm_d: int | None,
    furniture_type: str,
    extraction_id: str,
    report: MappingReport,
    approval_blocking: list[str],
    source_extraction_id: int | None,
    source_candidate_id: int | None,
) -> LayoutMappingResult | None:
    """Return a DesignGraph generated from outline_polygon when possible.

    This is the C1/C2 production path: a valid outline polygon is converted to
    modules/components immediately instead of falling through to a bounding-box
    fallback.
    """
    if outline_polygon is None:
        return None
    raw_vertices = outline_polygon.get("vertices_mm")
    if not raw_vertices or not isinstance(raw_vertices, list):
        return None
    if asm_d is None:
        return None

    from foms.services.designer.outline_to_3d import outline_to_3d

    result = outline_to_3d(
        vertices_mm=raw_vertices,
        depth_mm=float(asm_d),
        furniture_type=furniture_type,
        source_polygon_id=str(outline_polygon.get("id") or extraction_id),
    )
    if result.blocking_reasons:
        for reason in result.blocking_reasons:
            if reason not in approval_blocking:
                approval_blocking.append(reason)
        return None

    design_graph = result.design_graph
    if not design_graph.get("components"):
        approval_blocking.append("outline_to_3d:no_components_mapped")
        return None

    design_graph.setdefault("metadata", {})
    design_graph["metadata"].update({
        "source_extraction_id": source_extraction_id,
        "source_candidate_id": source_candidate_id,
        "furniture_type": furniture_type,
        "mapped_by": "outline_to_3d_c2",
    })

    for component in design_graph.get("components", []):
        report.mapped_components.append({
            "component_id": component.get("id"),
            "source": "outline_polygon",
            "kind": component.get("kind"),
        })
    report.warnings.extend(result.warnings)
    report.source_evidence.append(f"extraction_id:{extraction_id}")
    report.source_evidence.append(f"outline_polygon:{len(raw_vertices)}_vertices")

    validation_errors = _validate_design_graph(design_graph, report)
    for err in validation_errors:
        if err not in approval_blocking:
            approval_blocking.append(err)

    logger.info(
        "[LAYOUT_MAPPER] extraction_id=%s outline_to_3d modules=%d components=%d "
        "approval_blocking=%d preview=%s",
        extraction_id,
        len((design_graph.get("assembly") or {}).get("modules") or []),
        len(design_graph.get("components") or []),
        len(approval_blocking),
        not approval_blocking,
    )

    return LayoutMappingResult(
        design_graph=design_graph,
        mapping_report=report,
        confidence=0.85 if not approval_blocking else 0.65,
        preview_allowed=bool(design_graph.get("components")),
        approval_blocking_reasons=approval_blocking,
    )


def _belongs_to_zone(gemini_module: dict[str, Any], zone: dict[str, Any]) -> bool:
    """Check if a Gemini module visually overlaps with a zone based on relations or position."""
    # Check explicit relation reference
    for rel in (gemini_module.get("relations") or []):
        if str(zone.get("id")) in str(rel):
            return True

    # Positional overlap check
    zone_x = _parse_dim(zone.get("x_mm")) or 0
    zone_w = _parse_dim(zone.get("width_mm")) or 0
    if zone_w == 0:
        return False

    gm_pos = gemini_module.get("position") or {}
    gm_x = _parse_dim(gm_pos.get("x_mm")) or 0
    gm_dims = gemini_module.get("dimensions") or {}
    gm_w = _parse_dim(gm_dims.get("width_mm")) or 0

    # Simple x-axis overlap
    return gm_x >= zone_x and (gm_x + gm_w) <= (zone_x + zone_w + 50)  # 50mm tolerance


def _apply_parts_table_hints(
    components: list[dict[str, Any]],
    parts_table: list[dict[str, Any]],
) -> None:
    """Apply parts table hints (material_id, role corrections) to existing components."""
    for part in parts_table:
        code = str(part.get("code") or "").strip().upper()
        desc = str(part.get("description") or "").strip()

        for key, mapping in _PARTS_CODE_MAP.items():
            if key.upper() in code or key in desc:
                # Update first untyped component of this kind
                for comp in components:
                    if comp.get("kind") == mapping["kind"] and comp.get("material_id") is None:
                        comp["custom_props"]["parts_table_hint"] = code
                        break


def _validate_design_graph(
    design_graph: dict[str, Any],
    report: MappingReport,
) -> list[str]:
    """Run basic structural validation on the mapped DesignGraph.

    Returns list of approval_blocking error strings.
    """
    errors: list[str] = []
    asm = design_graph.get("assembly") or {}
    dims = asm.get("dimensions") or {}

    # Assembly dimensions
    for axis in ("width", "height", "depth"):
        val = dims.get(axis) or 0
        if val <= 0:
            errors.append(f"assembly.dimensions.{axis}_is_zero_or_missing")

    # Component count
    components = design_graph.get("components") or []
    if not components:
        errors.append("no_components_in_design_graph")
        report.warnings.append("No components mapped — cannot generate 3D preview")

    # Duplicate IDs
    ids = [c.get("id") for c in components if c.get("id")]
    if len(ids) != len(set(ids)):
        errors.append("duplicate_component_ids")
        report.warnings.append("Duplicate component IDs detected — remapping required")

    return errors


# ──────────────────────────────────────────────────────────
# Convenience entry point from raw extraction
# ──────────────────────────────────────────────────────────

def map_extraction_to_design_graph(
    extraction: dict[str, Any],
    source_extraction_id: int | None = None,
    source_candidate_id: int | None = None,
    similar_cases: list[dict[str, Any]] | None = None,
    ontology_rules: dict[str, Any] | None = None,
) -> LayoutMappingResult:
    """Convenience wrapper: build LayoutMappingInput from extraction and map.

    This is the primary entry point for the LangGraph workflow node.
    """
    mapping_input = LayoutMappingInput.from_extraction(
        extraction,
        source_extraction_id=source_extraction_id,
        source_candidate_id=source_candidate_id,
        similar_cases=similar_cases or [],
        ontology_rules=ontology_rules or {},
    )
    return map_layout_to_design_graph(mapping_input)
