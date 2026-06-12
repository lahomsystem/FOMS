"""SketchUpLayoutGraph → DesignGraph schema v2.

Plan §4.5. The mapper is deterministic: same LayoutGraph → same
DesignGraph. No Gemini, no DB. The Gemini assist path (B8) only adds
suggestions on top of the result; it never edits the mapper output.

DesignGraph v2 shape (matches foms/services/designer/layout_graph_mapper.py):

  {
    "schema_version": 2,
    "unit": "mm",
    "assembly": {
      "id": str,
      "type": str,
      "dimensions": {"width": int, "height": int, "depth": int},
      "position": {"x": int, "y": int, "z": int},
      "modules": [...],
      "module_count": int,
      ...
    },
    "components": [
      {"id": str, "kind": str, "role": str,
       "position": {"x": int, "y": int, "z": int},
       "dimensions": {"width": int, "height": int, "depth": int},
       "material": str | null, ...}
    ],
    "constraints": [],
    "relations": [...],
    "metadata": {...},
  }

Validator (same checks as `_validate_design_graph` in the image mapper):
  - assembly.dimensions {width,height,depth} > 0
  - components non-empty
  - no duplicate component ids
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from foms.services.designer.sketchup_layout_extractor import ROLE_TO_KIND


logger = logging.getLogger(__name__)


DESIGN_GRAPH_SCHEMA_VERSION = 2
DEFAULT_PANEL_THICKNESS_MM = 18
DEFAULT_BASE_HEIGHT_MM = 60


@dataclass
class GraphMappingResult:
    """Output of `map_sketchup_layout_to_design_graph`.

    `design_graph` is always present even on validator errors so the UI
    can render whatever was extractable (gated by `preview_allowed`).
    `approval_blocking_reasons` is the union of LayoutGraph-level
    blockers, validator errors, and any mapping-time inconsistencies.
    """

    design_graph: dict[str, Any]
    preview_allowed: bool
    confidence: float
    approval_blocking_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    unresolved_fields: list[str] = field(default_factory=list)


def _int_mm(value: Any) -> int:
    """Round a millimetre value to the nearest integer.

    DesignGraph v2 consumers (Three.js editor, validator) expect integer
    millimetres on dimensions/positions. Source LayoutGraph carries
    floats — we round once at the boundary to keep the editor's pixel
    math stable across re-maps.
    """
    if value is None:
        return 0
    return int(round(float(value)))


def _component_payload(layout_component: dict[str, Any]) -> dict[str, Any]:
    dims = layout_component.get("dimensions") or {}
    pos = layout_component.get("position") or {}
    return {
        "id": layout_component["id"],
        "kind": layout_component.get("kind") or ROLE_TO_KIND.get(
            layout_component.get("role") or "generic", "unknown"
        ),
        "role": layout_component.get("role") or "generic",
        "name": layout_component.get("name"),
        "module_id": layout_component.get("module_id"),
        "position": {
            "x": _int_mm(pos.get("x_mm")),
            "y": _int_mm(pos.get("y_mm")),
            "z": _int_mm(pos.get("z_mm")),
        },
        "dimensions": {
            "width": _int_mm(dims.get("width_mm")),
            "height": _int_mm(dims.get("height_mm")),
            "depth": _int_mm(dims.get("depth_mm")),
        },
        "material": layout_component.get("material"),
        "confidence": float(layout_component.get("confidence") or 0.0),
        "evidence": list(layout_component.get("evidence") or []),
        "source_node_ids": list(layout_component.get("source_node_ids") or []),
    }


def _module_payload(layout_module: dict[str, Any]) -> dict[str, Any]:
    dims = layout_module.get("dimensions") or {}
    pos = layout_module.get("position") or {}
    return {
        "id": layout_module["id"],
        "type": layout_module.get("type") or "unknown",
        "name": layout_module.get("name"),
        "position": {
            "x": _int_mm(pos.get("x_mm")),
            "y": _int_mm(pos.get("y_mm")),
            "z": _int_mm(pos.get("z_mm")),
        },
        "dimensions": {
            "width": _int_mm(dims.get("width_mm")),
            "height": _int_mm(dims.get("height_mm")),
            "depth": _int_mm(dims.get("depth_mm")),
        },
        "source_node_ids": list(layout_module.get("source_node_ids") or []),
        "confidence": float(layout_module.get("confidence") or 0.0),
    }


def _assembly_dimensions(layout_graph: dict[str, Any]) -> dict[str, int]:
    bbox = (layout_graph.get("overall") or {}).get("bbox_mm") or {}
    return {
        "width": _int_mm(bbox.get("width_mm")),
        "height": _int_mm(bbox.get("height_mm")),
        "depth": _int_mm(bbox.get("depth_mm")),
    }


def _validate_design_graph(design_graph: dict[str, Any]) -> list[str]:
    """Same gates as the image mapper's `_validate_design_graph`.

    Kept in sync intentionally — the React editor consumes both image
    and SketchUp candidates through the same code path, so changes here
    must mirror `foms/services/designer/layout_graph_mapper.py`.
    """
    errors: list[str] = []
    asm = design_graph.get("assembly") or {}
    dims = asm.get("dimensions") or {}
    for axis in ("width", "height", "depth"):
        if (dims.get(axis) or 0) <= 0:
            errors.append(f"assembly.dimensions.{axis}_is_zero_or_missing")

    components = design_graph.get("components") or []
    if not components:
        errors.append("no_components_in_design_graph")

    ids = [c.get("id") for c in components if c.get("id")]
    if len(ids) != len(set(ids)):
        errors.append("duplicate_component_ids")

    return errors


def _aggregate_confidence(layout_graph: dict[str, Any]) -> float:
    """Average component confidence, falling back to overall.confidence."""
    components = layout_graph.get("components") or []
    if not components:
        return float((layout_graph.get("overall") or {}).get("confidence") or 0.0)
    total = sum(float(c.get("confidence") or 0.0) for c in components)
    return round(total / len(components), 3)


def map_sketchup_layout_to_design_graph(
    layout_graph: dict[str, Any],
    *,
    source_extraction_id: int | None = None,
    source_candidate_id: int | None = None,
    upstream_blocking_reasons: list[str] | None = None,
) -> GraphMappingResult:
    """Deterministic LayoutGraph → DesignGraph v2 mapping.

    `upstream_blocking_reasons` lets the caller forward LayoutGraph-
    level blockers (loose geometry, schema invalid) so the final result
    carries the union — the worker / API never needs to merge two
    parallel lists.
    """
    blocking: list[str] = list(upstream_blocking_reasons or [])
    warnings: list[str] = list(layout_graph.get("warnings") or [])
    unresolved: list[str] = list(layout_graph.get("unresolved_fields") or [])

    components = [_component_payload(c) for c in (layout_graph.get("components") or [])]
    modules = [_module_payload(m) for m in (layout_graph.get("modules") or [])]
    asm_dimensions = _assembly_dimensions(layout_graph)

    # Validator constraint (constraint_engine.OUTER_WIDTH_MISMATCH):
    #   outer_width == ep_left + sum(modules.width) + ep_right
    # The SketchUp model's overall bbox may be larger than the modules'
    # extent when extraction is incomplete (loose nodes outside the
    # walked groups, hidden helper meshes, etc.). To keep the graph
    # internally consistent we override the width with the modules' sum
    # + EP and stamp a `module_coverage_mismatch` warning so reviewers
    # can see something was missed. Height/depth follow the same
    # principle but only when modules exist — for empty-module cases the
    # bbox stays as the only available signal.
    coverage_warnings: list[str] = []
    if modules:
        ep_total = 2 * DEFAULT_PANEL_THICKNESS_MM
        module_width_sum = sum(m["dimensions"]["width"] for m in modules)
        derived_width = module_width_sum + ep_total
        if asm_dimensions["width"] and abs(asm_dimensions["width"] - derived_width) > 5:
            coverage_warnings.append(
                f"module_coverage_mismatch:width({asm_dimensions['width']}→{derived_width})"
            )
            asm_dimensions = {
                **asm_dimensions,
                "width": derived_width,
            }
        else:
            asm_dimensions = {**asm_dimensions, "width": derived_width}

    asm_id = f"assembly_extr_{source_extraction_id or source_candidate_id or 'unknown'}"
    assembly = {
        "id": asm_id,
        "type": (layout_graph.get("overall") or {}).get("furniture_type") or "custom_storage",
        "dimensions": asm_dimensions,
        "position": {"x": 0, "y": 0, "z": 0},
        "modules": modules,
        "ep_left": DEFAULT_PANEL_THICKNESS_MM,
        "ep_right": DEFAULT_PANEL_THICKNESS_MM,
        "ep_top": DEFAULT_PANEL_THICKNESS_MM,
        "base_height": DEFAULT_BASE_HEIGHT_MM,
        "top_sr": DEFAULT_PANEL_THICKNESS_MM,
        "module_count": len(modules),
        "door_type": "open",
    }
    warnings.extend(coverage_warnings)

    relations = []
    for rel in (layout_graph.get("relations") or []):
        relations.append(
            {
                "from": rel.get("from"),
                "to": rel.get("to"),
                "type": rel.get("type"),
                "confidence": float(rel.get("confidence") or 0.0),
            }
        )

    design_graph: dict[str, Any] = {
        "schema_version": DESIGN_GRAPH_SCHEMA_VERSION,
        "unit": "mm",
        "assembly": assembly,
        "components": components,
        "constraints": [],
        "relations": relations,
        "metadata": {
            "source_extraction_id": source_extraction_id,
            "source_candidate_id": source_candidate_id,
            "source_kind": "sketchup_model",
            "coordinate_system": layout_graph.get("coordinate_system"),
            "furniture_type": assembly["type"],
            "mapped_by": "sketchup_graph_mapper_b6",
            "warnings": warnings,
            "unresolved_fields": unresolved,
        },
    }

    validation_errors = _validate_design_graph(design_graph)
    for err in validation_errors:
        if err not in blocking:
            blocking.append(err)

    aggregate_conf = _aggregate_confidence(layout_graph)
    if blocking:
        # Drop confidence when blocking reasons exist so the UI's
        # confidence ribbon matches the "cannot preview" state.
        aggregate_conf = min(aggregate_conf, 0.5)

    preview_allowed = bool(components) and not validation_errors
    # LayoutGraph-level blockers (loose geometry, etc.) also disable
    # preview even when components were extracted — the user must fix
    # the source model first.
    if blocking and "no_components_in_design_graph" not in blocking:
        # If components exist but a blocking reason came in from
        # upstream (loose_geometry_requires_grouping, etc.), we still
        # block preview because the extraction is untrustworthy.
        preview_allowed = preview_allowed and not (
            set(blocking) & {
                "loose_geometry_requires_grouping",
                "layout_schema_invalid",
                "overall_bbox_zero_or_missing",
            }
        )

    return GraphMappingResult(
        design_graph=design_graph,
        preview_allowed=preview_allowed,
        confidence=aggregate_conf,
        approval_blocking_reasons=blocking,
        warnings=warnings,
        unresolved_fields=unresolved,
    )


__all__ = [
    "DESIGN_GRAPH_SCHEMA_VERSION",
    "GraphMappingResult",
    "map_sketchup_layout_to_design_graph",
]
