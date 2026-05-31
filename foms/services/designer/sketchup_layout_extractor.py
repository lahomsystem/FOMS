"""SketchUp RawModelJson → SketchUpLayoutGraph.

Plan §6.3 (axis detection) + §6.4 (semantic extraction rules).

Responsibilities:
  - Decide an `axis_profile` mapping SketchUp world axes to FOMS
    (width / height / depth). The analyzer may pre-compute one; we
    accept it when confident and fall back to a heuristic otherwise.
  - Walk the node tree once, attaching a semantic role to each
    component_instance / group leaf using the priority chain:
        name → definition name → tag/layer → material → geometry
  - Collect top-level groups as `modules`, their leaves as
    `components`, and `contained_by` relations between them.
  - Compute confidence per §6.4 and surface unresolved fields +
    warnings that the approval gate keys off.
  - Detect loose_geometry-only models and emit the
    `loose_geometry_requires_grouping` blocking reason.

Outputs a dict conforming to `foms-sketchup-layout-v1.schema.json`.
Pure function — no DB, no subprocess, no network.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable

from foms.services.designer.sketchup_raw_schema import (
    SchemaValidationResult,
    validate_layout_graph_json,
)


logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────
# Role keyword tables (plan §6.4)
# ──────────────────────────────────────────────────────────

# Each role lists case-insensitive substrings (Korean + English).
# Order inside the list matters only for evidence reporting, not for
# matching — the first match wins per node lookup.
ROLE_KEYWORDS: list[tuple[str, list[str]]] = [
    ("shelf",        ["선반", "shelf", "SR"]),
    ("door",         ["도어", "문짝", "door"]),
    ("drawer",       ["서랍", "drawer"]),
    ("rail",         ["옷봉", "레일", "rail"]),
    ("hardware",     ["손잡이", "경첩", "hinge", "handle", "hardware"]),
    ("back_panel",   ["후판", "back"]),
    ("base",         ["걸레받이", "base", "kick"]),
    ("top_panel",    ["상판", "top"]),
    ("bottom_panel", ["하판", "bottom"]),
    # Side keywords need EP/측판 to remain prioritized over generic "panel".
    ("left_side",    ["좌측", "left_side", "left side", "측판 좌", "좌측 측판"]),
    ("right_side",   ["우측", "right_side", "right side", "측판 우", "우측 측판"]),
    ("side",         ["측판", "EP", "side panel", "end panel"]),
]

# Role → DesignGraph component kind. Same enum as plan §4.4.
ROLE_TO_KIND: dict[str, str] = {
    "shelf": "shelf",
    "door": "door",
    "drawer": "drawer",
    "rail": "hardware",
    "hardware": "hardware",
    "back_panel": "panel",
    "base": "panel",
    "top_panel": "panel",
    "bottom_panel": "panel",
    "left_side": "panel",
    "right_side": "panel",
    "side": "panel",
    "generic": "unknown",
}

# Confidence levels (plan §6.4 confidence ladder).
CONF_NAME_AND_GEO = 0.95
CONF_NAME_OR_TAG = 0.80
CONF_DEFINITION_NAME = 0.78
CONF_GEOMETRY_ONLY = 0.65
CONF_MATERIAL_HINT = 0.50
CONF_UNKNOWN = 0.30

# Geometry constants (plan §6.4 — panel heuristic).
PANEL_MIN_THICK_MM = 3
PANEL_MAX_THICK_MM = 40

DEFAULT_AXIS_PROFILE_CONFIDENCE = 0.95
AXIS_AMBIGUOUS_THRESHOLD = 0.80


# ──────────────────────────────────────────────────────────
# Result envelope
# ──────────────────────────────────────────────────────────


@dataclass
class LayoutExtractionResult:
    """Output of `extract_layout_graph`.

    `layout_graph` is always present and schema-valid; `warnings` and
    `unresolved_fields` are the same lists embedded inside `layout_graph`
    promoted to the result envelope so callers can branch without
    digging through the nested structure.
    """

    layout_graph: dict[str, Any]
    blocking_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    unresolved_fields: list[str] = field(default_factory=list)
    schema_validation: SchemaValidationResult | None = None


# ──────────────────────────────────────────────────────────
# Axis profile
# ──────────────────────────────────────────────────────────


def _resolve_axis_profile(raw: dict) -> tuple[dict[str, str], float, list[str]]:
    """Pick `(width_axis, height_axis, depth_axis)` for FOMS coords.

    SketchUp's default for upright furniture is X=width, Z=height,
    Y=depth (right-handed, Z-up). We trust the analyzer when it
    publishes its own `axis_profile` with confidence ≥ threshold; below
    that we keep the SketchUp default and emit `axis_profile_ambiguous`.
    """
    warnings: list[str] = []
    model = raw.get("model") or {}
    analyzer_profile = model.get("axis_profile") or {}
    conf = float(analyzer_profile.get("confidence") or 0)

    if conf >= AXIS_AMBIGUOUS_THRESHOLD and all(
        k in analyzer_profile for k in ("width_axis", "height_axis", "depth_axis")
    ):
        profile = {
            "width_axis": analyzer_profile["width_axis"],
            "height_axis": analyzer_profile["height_axis"],
            "depth_axis": analyzer_profile["depth_axis"],
        }
        return profile, conf, warnings

    if conf and conf < AXIS_AMBIGUOUS_THRESHOLD:
        warnings.append("axis_profile_ambiguous")

    # SketchUp default mapping (plan §6.3).
    return (
        {"width_axis": "x", "height_axis": "z", "depth_axis": "y"},
        DEFAULT_AXIS_PROFILE_CONFIDENCE,
        warnings,
    )


def _project_bbox(
    bbox: dict[str, Any],
    axis_profile: dict[str, str],
) -> tuple[dict[str, float], dict[str, float]]:
    """Return (position_mm, dimensions_mm) in FOMS axes.

    `bbox` is the SketchUp-axis bbox (`min`, `max`, optionally `size`).
    Position is the FOMS-coord lower-left corner; dimensions is
    width/height/depth derived from max-min on the same SketchUp axes.
    """
    mn = bbox.get("min") or {}
    mx = bbox.get("max") or {}

    def axis_value(coord: dict[str, Any], sk_axis: str) -> float:
        return float(coord.get(sk_axis) or 0)

    width = axis_value(mx, axis_profile["width_axis"]) - axis_value(mn, axis_profile["width_axis"])
    height = axis_value(mx, axis_profile["height_axis"]) - axis_value(mn, axis_profile["height_axis"])
    depth = axis_value(mx, axis_profile["depth_axis"]) - axis_value(mn, axis_profile["depth_axis"])

    return (
        {
            "x_mm": axis_value(mn, axis_profile["width_axis"]),
            "y_mm": axis_value(mn, axis_profile["height_axis"]),
            "z_mm": axis_value(mn, axis_profile["depth_axis"]),
        },
        {
            "width_mm": round(width, 3),
            "height_mm": round(height, 3),
            "depth_mm": round(depth, 3),
        },
    )


# ──────────────────────────────────────────────────────────
# Role classification
# ──────────────────────────────────────────────────────────


def _match_role_by_keyword(text: str | None) -> tuple[str, list[str]] | None:
    if not text:
        return None
    norm = text.lower()
    for role, keywords in ROLE_KEYWORDS:
        for kw in keywords:
            if kw.lower() in norm:
                return role, [f"keyword:{kw}"]
    return None


def _classify_by_geometry(
    dimensions: dict[str, float],
) -> tuple[str, float, list[str]]:
    """Geometry-only fallback (plan §6.4 panel heuristic).

    A board-like shape (one axis between 3-40mm and the other two
    much larger) is a panel. Which kind of panel depends on which
    FOMS axis is the thin one:
      - thin on height → shelf or top/bottom panel (we can't tell
        which without context, so we return 'shelf' and trust the
        review UI to correct it).
      - thin on width  → side panel.
      - thin on depth  → door or back panel; we default to 'door'
        which is the more common upright furniture case.
    """
    w = dimensions["width_mm"]
    h = dimensions["height_mm"]
    d = dimensions["depth_mm"]
    pairs = [(w, "width_mm"), (h, "height_mm"), (d, "depth_mm")]
    pairs.sort(key=lambda p: p[0])
    thin_val, thin_axis = pairs[0]
    if thin_val <= 0:
        return "generic", CONF_UNKNOWN, ["zero_dimension"]
    if not (PANEL_MIN_THICK_MM <= thin_val <= PANEL_MAX_THICK_MM):
        return "generic", CONF_UNKNOWN, ["no_panel_shape"]

    other = [v for v, _ in pairs[1:]]
    if min(other) < 100:
        # Not really a board — could be hardware-sized. Don't claim it.
        return "generic", CONF_UNKNOWN, ["thin_but_small"]

    if thin_axis == "height_mm":
        return "shelf", CONF_GEOMETRY_ONLY, ["geometry:horizontal_panel"]
    if thin_axis == "width_mm":
        return "side", CONF_GEOMETRY_ONLY, ["geometry:vertical_panel"]
    return "door", CONF_GEOMETRY_ONLY, ["geometry:depth_panel"]


def _classify_node(
    node: dict[str, Any],
    *,
    definitions_by_id: dict[str, dict[str, Any]],
    dimensions: dict[str, float],
) -> tuple[str, float, list[str]]:
    """Apply the §6.4 priority chain.

    Returns `(role, confidence, evidence)`. `evidence` is a flat list of
    short strings (`keyword:선반`, `geometry:horizontal_panel`, ...).
    """
    name = node.get("name")
    tag = node.get("tag")
    layer = node.get("layer")
    definition_id = node.get("definition_id")
    material = node.get("material")

    name_match = _match_role_by_keyword(name)
    geom_role, geom_conf, geom_evidence = _classify_by_geometry(dimensions)

    if name_match is not None:
        role, evidence = name_match
        if geom_role != "generic" and ROLE_TO_KIND.get(role) == ROLE_TO_KIND.get(geom_role):
            return role, CONF_NAME_AND_GEO, evidence + geom_evidence
        return role, CONF_NAME_OR_TAG, evidence

    # tag / layer fallback
    for label, source_name in ((tag, "tag"), (layer, "layer")):
        m = _match_role_by_keyword(label)
        if m is not None:
            role, evidence = m
            tagged = [f"{source_name}:{e.split(':', 1)[1]}" for e in evidence]
            return role, CONF_NAME_OR_TAG, tagged

    # definition name fallback
    if definition_id and definition_id in definitions_by_id:
        defn_name = (definitions_by_id[definition_id] or {}).get("name")
        m = _match_role_by_keyword(defn_name)
        if m is not None:
            role, _ = m
            return role, CONF_DEFINITION_NAME, [f"definition_name:{defn_name}"]

    # material hint — material alone never proves role, only suggests.
    if material and isinstance(material, str):
        if any(token in material.lower() for token in ("hinge", "handle", "경첩", "손잡이")):
            return "hardware", CONF_MATERIAL_HINT, [f"material:{material}"]

    if geom_role != "generic":
        return geom_role, geom_conf, geom_evidence

    return "generic", CONF_UNKNOWN, ["unknown_fallback"]


# ──────────────────────────────────────────────────────────
# Node tree walks
# ──────────────────────────────────────────────────────────


def _nodes_by_id(raw: dict) -> dict[str, dict[str, Any]]:
    return {n["node_id"]: n for n in (raw.get("nodes") or []) if "node_id" in n}


def _top_level_groups(raw: dict) -> list[dict[str, Any]]:
    return [
        n for n in (raw.get("nodes") or [])
        if n.get("kind") == "group" and not n.get("parent_id") and n.get("visible", True)
    ]


def _leaf_components(node: dict[str, Any], by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """All component_instance / face_shell leaves under `node`.

    We deliberately skip nested groups — those become their own modules
    when promoted to top level. For B6 we keep the hierarchy one level
    deep; deeper structures fall back to generic flat extraction.
    """
    out: list[dict[str, Any]] = []
    for child_id in (node.get("children_ids") or []):
        child = by_id.get(child_id)
        if not child:
            continue
        if not child.get("visible", True):
            continue
        kind = child.get("kind")
        if kind == "component_instance":
            out.append(child)
        elif kind == "group":
            out.extend(_leaf_components(child, by_id))
        # face_shell / loose_geometry at the leaf level are flagged in
        # `extract_layout_graph` rather than promoted to components.
    return out


def _has_grouping(raw: dict) -> bool:
    """True iff *any* visible group or component_instance exists.

    Used to detect the "exploded loose geometry" case (plan §6.4) where
    the user uploaded a raw mesh — review must be blocked until they
    re-group in SketchUp.
    """
    for node in raw.get("nodes") or []:
        if not node.get("visible", True):
            continue
        if node.get("kind") in {"group", "component_instance"}:
            return True
    return False


# ──────────────────────────────────────────────────────────
# Public entry
# ──────────────────────────────────────────────────────────


def _stable_id(prefix: str, *parts: Any) -> str:
    suffix = "_".join(str(p) for p in parts if p is not None and p != "")
    return f"{prefix}_{suffix}" if suffix else prefix


def _overall_bbox_mm(raw: dict, axis_profile: dict[str, str]) -> dict[str, float]:
    bbox = (raw.get("model") or {}).get("bbox_mm") or {}
    _, dims = _project_bbox(bbox, axis_profile)
    return dims


def _normalize_warning(w: Any) -> str:
    if isinstance(w, str):
        return w
    if isinstance(w, dict) and "code" in w:
        return str(w["code"])
    return str(w)


def extract_layout_graph(
    raw: dict,
    *,
    source_artifact_id: int | None = None,
) -> LayoutExtractionResult:
    """Build a `foms-sketchup-layout-v1` payload from a raw model.

    The result is always schema-validated before being returned; a
    placeholder shape is returned with `blocking_reasons` populated when
    extraction cannot produce a meaningful layout (loose geometry,
    empty model, etc.). Callers must consult `blocking_reasons` /
    `unresolved_fields` rather than guessing from confidence alone.
    """
    warnings: list[str] = [_normalize_warning(w) for w in (raw.get("warnings") or [])]
    unresolved: list[str] = []
    blocking: list[str] = []

    axis_profile, axis_conf, axis_warnings = _resolve_axis_profile(raw)
    warnings.extend(axis_warnings)
    if "axis_profile_ambiguous" in axis_warnings:
        unresolved.append("axis_profile")

    overall_bbox = _overall_bbox_mm(raw, axis_profile)
    if not (overall_bbox["width_mm"] and overall_bbox["height_mm"] and overall_bbox["depth_mm"]):
        blocking.append("overall_bbox_zero_or_missing")

    # Loose-geometry-only models are review-blocked (plan §6.4).
    if not _has_grouping(raw):
        blocking.append("loose_geometry_requires_grouping")

    definitions_by_id = {
        d["definition_id"]: d
        for d in (raw.get("definitions") or [])
        if "definition_id" in d
    }
    by_id = _nodes_by_id(raw)

    modules: list[dict[str, Any]] = []
    components: list[dict[str, Any]] = []
    relations: list[dict[str, Any]] = []
    seen_definitions: dict[str, int] = {}
    next_component_index = 0

    for module_node in _top_level_groups(raw):
        m_position, m_dimensions = _project_bbox(
            module_node.get("bbox_mm") or {}, axis_profile
        )
        module_id = _stable_id("module", module_node["node_id"])
        modules.append(
            {
                "id": module_id,
                "type": "storage_box" if m_dimensions["height_mm"] >= 600 else "unknown",
                "name": module_node.get("name"),
                "position": m_position,
                "dimensions": m_dimensions,
                "source_node_ids": [module_node["node_id"]],
                "confidence": 0.7,
            }
        )

        leaves = _leaf_components(module_node, by_id)
        for leaf in leaves:
            next_component_index += 1
            c_position, c_dimensions = _project_bbox(
                leaf.get("bbox_mm") or {}, axis_profile
            )
            role, conf, evidence = _classify_node(
                leaf,
                definitions_by_id=definitions_by_id,
                dimensions=c_dimensions,
            )
            kind = ROLE_TO_KIND.get(role, "unknown")
            comp_id = _stable_id("component", leaf["node_id"])
            components.append(
                {
                    "id": comp_id,
                    "kind": kind,
                    "role": role,
                    "name": leaf.get("name"),
                    "module_id": module_id,
                    "position": c_position,
                    "dimensions": c_dimensions,
                    "material": leaf.get("material"),
                    "source_node_ids": [leaf["node_id"]],
                    "evidence": evidence,
                    "confidence": conf,
                }
            )
            relations.append(
                {
                    "from": comp_id,
                    "to": module_id,
                    "type": "contained_by",
                    "confidence": 0.9,
                }
            )

            if conf < 0.7:
                unresolved.append(f"component.{comp_id}.role")
            defn = leaf.get("definition_id")
            if defn:
                seen_definitions[defn] = seen_definitions.get(defn, 0) + 1

    # Repeated definitions are evidence for reusable block candidates.
    repeated = [d for d, n in seen_definitions.items() if n > 1]
    if repeated:
        warnings.append(f"repeated_definitions:{len(repeated)}")

    if not components:
        # Don't mark this twice if loose geometry already accounts for it.
        if "loose_geometry_requires_grouping" not in blocking:
            blocking.append("no_components_extracted")

    layout_graph: dict[str, Any] = {
        "schema_version": "foms-sketchup-layout-v1",
        "coordinate_system": "sketchup_world_mm",
        "source_artifact_id": source_artifact_id,
        "overall": {
            "furniture_type": "unknown",
            "bbox_mm": overall_bbox,
            "confidence": axis_conf if not blocking else min(axis_conf, 0.5),
        },
        "modules": modules,
        "components": components,
        "relations": relations,
        "unresolved_fields": unresolved,
        "warnings": warnings,
    }

    validation = validate_layout_graph_json(layout_graph)
    if not validation.is_valid:
        # The placeholder schema must always validate. If it doesn't,
        # that's a programmer bug — flag it loudly so tests catch it.
        logger.error(
            "[SKETCHUP] layout_graph schema_invalid: %s",
            validation.as_error_text(),
        )
        # Demote the candidate to blocked rather than crashing the caller.
        blocking.append("layout_schema_invalid")
        warnings.append("layout_schema_invalid_internal_error")

    return LayoutExtractionResult(
        layout_graph=layout_graph,
        blocking_reasons=blocking,
        warnings=warnings,
        unresolved_fields=unresolved,
        schema_validation=validation,
    )


__all__ = [
    "AXIS_AMBIGUOUS_THRESHOLD",
    "CONF_GEOMETRY_ONLY",
    "CONF_NAME_AND_GEO",
    "CONF_NAME_OR_TAG",
    "CONF_UNKNOWN",
    "LayoutExtractionResult",
    "ROLE_KEYWORDS",
    "ROLE_TO_KIND",
    "extract_layout_graph",
]
