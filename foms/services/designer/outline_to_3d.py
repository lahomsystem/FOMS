"""FOMS Brain C2 — Outline Polygon → 3D Assembly Extrusion.

Converts a validated 2D outline polygon to a DesignGraph v2 Assembly by
partitioning the polygon into axis-aligned rectangular modules and extruding
each by the given depth_mm.

Algorithm (rectilinear_partition_v1):
  1. Collect all unique y-coordinates from vertices as horizontal cut levels.
  2. For each y-band [y_i, y_{i+1}], cast a horizontal ray to find which
     x-intervals are inside the polygon (even-odd rule).
  3. Each x-interval × y-band × depth → one rectangular Module.
  4. Merge vertically adjacent rectangles with identical x-extent.
  5. Build ep (side panels) + base + top components inside each Module.

Contracts (from the C-plan):
  - Partition failure → empty graph NOT returned; blocking_reason instead.
  - irregular shape is attempted; 0 rectangles → partition_requires_manual_confirmation.
  - All output dimensions are int mm (rounded).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from foms.services.designer.outline_polygon_validator import validate_polygon

_PANEL_THICKNESS = 18  # mm
_ALGORITHM_VERSION = "rectilinear_partition_v1"


# ──────────────────────────────────────────────────────────
# Result dataclasses
# ──────────────────────────────────────────────────────────


@dataclass
class PartitionResult:
    """Decomposition of a polygon into non-overlapping axis-aligned rectangles."""

    module_rects: list[dict[str, float]]
    algorithm: str
    warnings: list[str] = field(default_factory=list)
    blocking_reason: str | None = None


@dataclass
class ExtrusionResult:
    """Result of outline_to_3d conversion."""

    design_graph: dict[str, Any]
    partition_report: dict[str, Any]
    blocking_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ──────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────


def outline_to_3d(
    vertices_mm: list[list[float]],
    depth_mm: float,
    furniture_type: str = "custom_storage",
    source_polygon_id: str | None = None,
) -> ExtrusionResult:
    """Convert a 2D outline polygon to a DesignGraph Assembly by extrusion.

    Args:
        vertices_mm: Ordered [x, y] pairs in mm.  Treated as a closed polygon.
        depth_mm: Extrusion depth (z-axis) in mm.  Must be > 0.
        furniture_type: FOMS canonical furniture type key.
        source_polygon_id: Optional ID of the originating DesignerOutlinePolygon
            row, stored in the partition_report for traceability.

    Returns:
        ExtrusionResult.  If blocking_reasons is non-empty, design_graph is {}
        and the caller must NOT persist or preview the graph.
    """
    # Validate polygon geometry first
    validation = validate_polygon(vertices_mm)
    if not validation.is_valid:
        return ExtrusionResult(
            design_graph={},
            partition_report={
                "algorithm": _ALGORITHM_VERSION,
                "source_polygon_id": source_polygon_id,
                "module_rects": [],
                "warnings": [],
            },
            blocking_reasons=[f"outline_polygon_invalid:{validation.error}"],
        )

    if depth_mm <= 0:
        return ExtrusionResult(
            design_graph={},
            partition_report={
                "algorithm": _ALGORITHM_VERSION,
                "source_polygon_id": source_polygon_id,
                "module_rects": [],
                "warnings": [],
            },
            blocking_reasons=["outline_polygon_invalid:depth_mm_must_be_positive"],
        )

    # Partition polygon into rectangles
    partition = _partition_polygon(vertices_mm, validation.shape_type)

    if partition.blocking_reason:
        return ExtrusionResult(
            design_graph={},
            partition_report={
                "algorithm": partition.algorithm,
                "source_polygon_id": source_polygon_id,
                "module_rects": [],
                "warnings": partition.warnings,
            },
            blocking_reasons=[partition.blocking_reason],
            warnings=partition.warnings,
        )

    # Build DesignGraph Assembly
    design_graph = _build_assembly(
        module_rects=partition.module_rects,
        depth_mm=depth_mm,
        shape_type=validation.shape_type,
        furniture_type=furniture_type,
        vertices_mm=vertices_mm,
    )

    partition_report = {
        "algorithm": partition.algorithm,
        "source_polygon_id": source_polygon_id,
        "module_rects": partition.module_rects,
        "warnings": partition.warnings,
    }

    return ExtrusionResult(
        design_graph=design_graph,
        partition_report=partition_report,
        blocking_reasons=[],
        warnings=partition.warnings,
    )


# ──────────────────────────────────────────────────────────
# Partition algorithm
# ──────────────────────────────────────────────────────────


def _partition_polygon(
    vertices_mm: list[list[float]],
    shape_type: str,
) -> PartitionResult:
    """Decompose polygon into non-overlapping axis-aligned rectangles."""
    try:
        rects = _horizontal_sweep_partition(vertices_mm)
    except Exception as exc:
        return PartitionResult(
            module_rects=[],
            algorithm=_ALGORITHM_VERSION,
            blocking_reason=f"partition_requires_manual_confirmation:{exc}",
        )

    if not rects:
        return PartitionResult(
            module_rects=[],
            algorithm=_ALGORITHM_VERSION,
            blocking_reason="partition_requires_manual_confirmation:no_rectangles_found",
        )

    warnings: list[str] = []
    if shape_type == "irregular":
        warnings.append("irregular_shape_auto_partitioned:verify_visually")

    return PartitionResult(
        module_rects=rects,
        algorithm=_ALGORITHM_VERSION,
        warnings=warnings,
    )


def _horizontal_sweep_partition(
    vertices_mm: list[list[float]],
) -> list[dict[str, float]]:
    """Decompose polygon into rectangles via horizontal sweep.

    For each y-band between consecutive vertex y-levels, cast a horizontal ray
    to find x-intervals inside the polygon using the even-odd rule.  Adjacent
    rectangles with identical x-extent are merged vertically.
    """
    ys = sorted(set(v[1] for v in vertices_mm))

    raw: list[dict[str, float]] = []

    for i in range(len(ys) - 1):
        y_bot = ys[i]
        y_top = ys[i + 1]
        if y_top - y_bot < 1e-6:
            continue

        y_mid = (y_bot + y_top) / 2.0
        intervals = _inside_x_intervals(vertices_mm, y_mid)

        for x_start, x_end in intervals:
            raw.append(
                {
                    "x": x_start,
                    "y": y_bot,
                    "width": x_end - x_start,
                    "height": y_top - y_bot,
                }
            )

    return _merge_vertical_rects(raw)


def _inside_x_intervals(
    vertices_mm: list[list[float]],
    y_mid: float,
) -> list[tuple[float, float]]:
    """Find x-intervals inside the polygon at horizontal line y = y_mid.

    Casts a horizontal ray at y_mid, finds all edge-crossing x-values, sorts
    them, and returns pairs (x_enter, x_exit) under the even-odd rule.
    """
    n = len(vertices_mm)
    x_crossings: list[float] = []

    for i in range(n):
        x0, y0 = vertices_mm[i][0], vertices_mm[i][1]
        x1, y1 = vertices_mm[(i + 1) % n][0], vertices_mm[(i + 1) % n][1]

        # Skip horizontal edges
        if abs(y1 - y0) < 1e-9:
            continue

        y_lo = min(y0, y1)
        y_hi = max(y0, y1)

        # Strict inequality avoids double-counting at shared vertices
        if not (y_lo < y_mid < y_hi):
            continue

        # General intersection formula (degenerates to x0 for vertical edges)
        x_cross = x0 + (y_mid - y0) * (x1 - x0) / (y1 - y0)
        x_crossings.append(x_cross)

    x_crossings.sort()

    intervals: list[tuple[float, float]] = []
    for j in range(0, len(x_crossings) - 1, 2):
        x_start = x_crossings[j]
        x_end = x_crossings[j + 1]
        if x_end - x_start > 1e-6:
            intervals.append((x_start, x_end))

    return intervals


def _merge_vertical_rects(
    rects: list[dict[str, float]],
) -> list[dict[str, float]]:
    """Merge vertically adjacent rectangles that share the same x and width."""
    if not rects:
        return []

    # Group by (x, width) with 3-decimal rounding to tolerate float noise
    from collections import defaultdict

    groups: dict[tuple[float, float], list[dict[str, float]]] = defaultdict(list)
    for r in rects:
        key = (round(r["x"], 3), round(r["width"], 3))
        groups[key].append(r)

    merged: list[dict[str, float]] = []
    for group in groups.values():
        group.sort(key=lambda r: r["y"])
        current = dict(group[0])
        for next_r in group[1:]:
            # Vertically adjacent when top of current == bottom of next
            if abs((current["y"] + current["height"]) - next_r["y"]) < 1e-6:
                current["height"] += next_r["height"]
            else:
                merged.append(current)
                current = dict(next_r)
        merged.append(current)

    # Return sorted by (y, x) for stable ordering
    merged.sort(key=lambda r: (r["y"], r["x"]))
    return merged


# ──────────────────────────────────────────────────────────
# DesignGraph v2 assembly builder
# ──────────────────────────────────────────────────────────


def _build_assembly(
    module_rects: list[dict[str, float]],
    depth_mm: float,
    shape_type: str,
    furniture_type: str,
    vertices_mm: list[list[float]],
) -> dict[str, Any]:
    """Build a DesignGraph v2 dict from the list of rectangular modules."""
    assembly_id = _stable_id("assembly", shape_type, furniture_type)
    bbox = _bounding_box(vertices_mm)

    modules: list[dict[str, Any]] = []
    for idx, rect in enumerate(module_rects):
        w = max(1, round(rect["width"]))
        h = max(1, round(rect["height"]))
        d = max(1, round(depth_mm))
        x = round(rect["x"])
        y = round(rect["y"])

        module_id = _stable_id("module", str(idx), str(x), str(y), str(w), str(h))
        components = _module_components(module_id, w, h, d)

        modules.append(
            {
                "id": module_id,
                "type": "storage_box",
                "label": f"구역-{idx + 1}",
                "dimensions": {"width_mm": w, "height_mm": h, "depth_mm": d},
                "position": {"x_mm": x, "y_mm": y, "z_mm": 0},
                "components": components,
            }
        )

    return {
        "schema_version": "v2",
        "assembly": {
            "id": assembly_id,
            "furniture_type": furniture_type,
            "shape_type": shape_type,
            "dimensions": {
                "width_mm": round(bbox["width"]),
                "height_mm": round(bbox["height"]),
                "depth_mm": round(depth_mm),
            },
            "custom_props": {
                "outline_polygon": {
                    "vertices_mm": vertices_mm,
                    "shape_type": shape_type,
                }
            },
            "modules": modules,
            "constraints": [],
            "relations": [],
        },
    }


def _module_components(
    module_id: str,
    width_mm: int,
    height_mm: int,
    depth_mm: int,
) -> list[dict[str, Any]]:
    """Generate structural ep/sr components for a rectangular module.

    Components:
      - Left EP (side panel)
      - Right EP (side panel)
      - Base SR (bottom shelf/board)
      - Top SR (top board)
      - 0..N mid shelves (one per 600 mm of usable height)
    """
    T = _PANEL_THICKNESS
    inner_w = max(0, width_mm - 2 * T)
    usable_h = max(0, height_mm - 2 * T)
    num_mid = max(0, usable_h // 600 - 1)

    comps: list[dict[str, Any]] = [
        {
            "id": _stable_id("ep_left", module_id),
            "kind": "ep",
            "role": "left_ep",
            "label": "좌측판",
            "dimensions": {"width_mm": T, "height_mm": height_mm, "depth_mm": depth_mm},
            "position": {"x_mm": 0, "y_mm": 0, "z_mm": 0},
        },
        {
            "id": _stable_id("ep_right", module_id),
            "kind": "ep",
            "role": "right_ep",
            "label": "우측판",
            "dimensions": {"width_mm": T, "height_mm": height_mm, "depth_mm": depth_mm},
            "position": {"x_mm": width_mm - T, "y_mm": 0, "z_mm": 0},
        },
        {
            "id": _stable_id("sr_base", module_id),
            "kind": "sr",
            "role": "base",
            "label": "바닥판",
            "dimensions": {"width_mm": inner_w, "height_mm": T, "depth_mm": depth_mm},
            "position": {"x_mm": T, "y_mm": 0, "z_mm": 0},
        },
        {
            "id": _stable_id("sr_top", module_id),
            "kind": "sr",
            "role": "top",
            "label": "천판",
            "dimensions": {"width_mm": inner_w, "height_mm": T, "depth_mm": depth_mm},
            "position": {"x_mm": T, "y_mm": height_mm - T, "z_mm": 0},
        },
    ]

    # Mid shelves evenly distributed in usable height
    if num_mid > 0:
        step = usable_h // (num_mid + 1)
        for k in range(1, num_mid + 1):
            y_pos = T + step * k
            comps.append(
                {
                    "id": _stable_id("sr_mid", module_id, str(k)),
                    "kind": "sr",
                    "role": "shelf",
                    "label": f"선반-{k}",
                    "dimensions": {
                        "width_mm": inner_w,
                        "height_mm": T,
                        "depth_mm": depth_mm,
                    },
                    "position": {"x_mm": T, "y_mm": y_pos, "z_mm": 0},
                }
            )

    return comps


# ──────────────────────────────────────────────────────────
# Utilities
# ──────────────────────────────────────────────────────────


def _stable_id(prefix: str, *keys: str) -> str:
    """Generate a deterministic UUID from prefix + keys."""
    name = f"{prefix}:{'|'.join(str(k) for k in keys)}"
    return str(uuid.uuid5(uuid.NAMESPACE_OID, name))


def _bounding_box(vertices_mm: list[list[float]]) -> dict[str, float]:
    """Compute the axis-aligned bounding box of a polygon."""
    xs = [v[0] for v in vertices_mm]
    ys = [v[1] for v in vertices_mm]
    return {
        "x_min": min(xs),
        "y_min": min(ys),
        "width": max(xs) - min(xs),
        "height": max(ys) - min(ys),
    }
