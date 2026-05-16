"""FOMS Brain C1 — Outline Polygon Validator.

Validates that a polygon extracted from a drawing is geometrically sound:
  - Is closed (vertices form a loop)
  - Has no self-intersections
  - Meets minimum area threshold
  - Classifies shape_type (rect/L_shape/T_shape/U_shape/irregular)

No external library dependencies — pure Python geometry only.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# ──────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────

_MIN_VERTEX_COUNT = 4
_MIN_AREA_MM2 = 10_000.0   # 100mm × 100mm
_ANGLE_TOLERANCE_DEG = 5.0  # degrees — tolerance for "right angle" classification


# ──────────────────────────────────────────────────────────
# Result dataclass
# ──────────────────────────────────────────────────────────

@dataclass
class PolygonValidationResult:
    """Result of polygon validation.

    Attributes:
        is_valid: True when the polygon passes all geometric checks.
        shape_type: Classified shape (rect/L_shape/T_shape/U_shape/irregular).
        area_mm2: Area computed via Shoelace formula (mm²).
        error: None if valid; human-readable reason string if invalid.
        vertex_count: Number of input vertices.
    """

    is_valid: bool
    shape_type: str
    area_mm2: float
    error: str | None
    vertex_count: int


# ──────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────

def validate_polygon(vertices_mm: list[list[float]]) -> PolygonValidationResult:
    """Validate a polygon extracted from a furniture drawing.

    Checks:
      1. Minimum vertex count (≥4)
      2. Minimum area (≥10 000 mm²)
      3. No self-intersections (proper crossing of non-adjacent edges)

    Args:
        vertices_mm: Ordered list of [x, y] pairs in mm.  The polygon is
            treated as closed — the last vertex connects back to the first.

    Returns:
        PolygonValidationResult with is_valid, shape_type, area_mm2, error,
        and vertex_count populated.
    """
    n = len(vertices_mm)
    area = compute_area_mm2(vertices_mm)
    shape = classify_shape_type(vertices_mm)

    if n < _MIN_VERTEX_COUNT:
        return PolygonValidationResult(
            is_valid=False,
            shape_type=shape,
            area_mm2=area,
            error=f"too_few_vertices:{n} (minimum {_MIN_VERTEX_COUNT})",
            vertex_count=n,
        )

    # Self-intersection checked before area: a bowtie polygon has undefined/zero
    # net area via Shoelace, so area check would fire first giving a misleading error.
    if _has_self_intersection(vertices_mm):
        return PolygonValidationResult(
            is_valid=False,
            shape_type=shape,
            area_mm2=area,
            error="self_intersection_detected",
            vertex_count=n,
        )

    if area < _MIN_AREA_MM2:
        return PolygonValidationResult(
            is_valid=False,
            shape_type=shape,
            area_mm2=area,
            error=f"area_too_small:{area:.1f}mm2 (minimum {_MIN_AREA_MM2})",
            vertex_count=n,
        )

    return PolygonValidationResult(
        is_valid=True,
        shape_type=shape,
        area_mm2=area,
        error=None,
        vertex_count=n,
    )


def classify_shape_type(vertices_mm: list[list[float]]) -> str:
    """Classify the overall shape of a polygon by vertex count and right-angle structure.

    Classification rules:
      - rect:      4 vertices, all interior angles ≈ 90°
      - L_shape:   6 vertices, all right angles, exactly one reflex (concave) corner
      - T_shape:   8 vertices, all right angles, T-shaped topology
      - U_shape:   8 vertices, all right angles, U-shaped topology
      - irregular: anything else

    Args:
        vertices_mm: Ordered [x, y] pairs in mm.

    Returns:
        Shape type string: "rect", "L_shape", "T_shape", "U_shape", or "irregular".
    """
    n = len(vertices_mm)
    if n < _MIN_VERTEX_COUNT:
        return "irregular"

    if not _all_right_angles(vertices_mm):
        return "irregular"

    if n == 4:
        return "rect"

    if n == 6:
        reflex_count = _count_reflex_vertices(vertices_mm)
        if reflex_count == 1:
            return "L_shape"
        return "irregular"

    if n == 8:
        reflex_count = _count_reflex_vertices(vertices_mm)
        if reflex_count == 2:
            return _classify_8_vertex_shape(vertices_mm)
        return "irregular"

    return "irregular"


def compute_area_mm2(vertices_mm: list[list[float]]) -> float:
    """Compute the signed area of a polygon using the Shoelace formula.

    The result is always the absolute value (positive), regardless of
    vertex ordering direction (CW or CCW).

    Args:
        vertices_mm: Ordered list of [x, y] pairs in mm.

    Returns:
        Area in mm² (non-negative float).  Returns 0.0 for degenerate inputs.
    """
    n = len(vertices_mm)
    if n < 3:
        return 0.0

    total = 0.0
    for i in range(n):
        x0, y0 = vertices_mm[i][0], vertices_mm[i][1]
        x1, y1 = vertices_mm[(i + 1) % n][0], vertices_mm[(i + 1) % n][1]
        total += (x0 * y1) - (x1 * y0)

    return abs(total) / 2.0


def segments_intersect(
    a1: list[float],
    a2: list[float],
    b1: list[float],
    b2: list[float],
) -> bool:
    """Test whether two line segments (a1→a2) and (b1→b2) properly intersect.

    Only detects *proper* (transversal) intersections — shared endpoints are
    not counted, which avoids false positives for adjacent polygon edges.

    Args:
        a1, a2: Endpoints of the first segment ([x, y] each).
        b1, b2: Endpoints of the second segment ([x, y] each).

    Returns:
        True if the segments cross strictly in their interiors.
    """
    def cross_2d(o: list[float], a: list[float], b: list[float]) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    d1 = cross_2d(b1, b2, a1)
    d2 = cross_2d(b1, b2, a2)
    d3 = cross_2d(a1, a2, b1)
    d4 = cross_2d(a1, a2, b2)

    if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and \
       ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)):
        return True

    return False


# ──────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────

def _has_self_intersection(vertices_mm: list[list[float]]) -> bool:
    """Return True if any two non-adjacent edges of the polygon cross.

    Args:
        vertices_mm: Ordered polygon vertices.

    Returns:
        True if a proper self-intersection is found.
    """
    n = len(vertices_mm)
    edges = [(vertices_mm[i], vertices_mm[(i + 1) % n]) for i in range(n)]

    for i in range(n):
        for j in range(i + 2, n):
            # Skip adjacent edges (they share a vertex)
            if i == 0 and j == n - 1:
                continue
            if segments_intersect(edges[i][0], edges[i][1], edges[j][0], edges[j][1]):
                return True

    return False


def _interior_angle_deg(
    p_prev: list[float],
    p_curr: list[float],
    p_next: list[float],
) -> float:
    """Compute the interior angle at p_curr formed by p_prev→p_curr→p_next.

    Returns the angle in degrees [0, 360).

    Args:
        p_prev: Previous vertex [x, y].
        p_curr: Current vertex [x, y].
        p_next: Next vertex [x, y].

    Returns:
        Interior angle in degrees.
    """
    dx1, dy1 = p_prev[0] - p_curr[0], p_prev[1] - p_curr[1]
    dx2, dy2 = p_next[0] - p_curr[0], p_next[1] - p_curr[1]

    len1 = math.hypot(dx1, dy1)
    len2 = math.hypot(dx2, dy2)

    if len1 < 1e-9 or len2 < 1e-9:
        return 0.0

    cos_a = (dx1 * dx2 + dy1 * dy2) / (len1 * len2)
    cos_a = max(-1.0, min(1.0, cos_a))
    return math.degrees(math.acos(cos_a))


def _signed_cross(p_prev: list[float], p_curr: list[float], p_next: list[float]) -> float:
    """2D signed cross product of vectors (prev→curr) and (curr→next).

    Positive = left turn (CCW), negative = right turn (CW).
    """
    return (
        (p_curr[0] - p_prev[0]) * (p_next[1] - p_curr[1])
        - (p_curr[1] - p_prev[1]) * (p_next[0] - p_curr[0])
    )


def _all_right_angles(vertices_mm: list[list[float]]) -> bool:
    """Return True if every interior angle of the polygon is ≈ 90° or 270°.

    Args:
        vertices_mm: Ordered polygon vertices.

    Returns:
        True when all corners are right angles within _ANGLE_TOLERANCE_DEG.
    """
    n = len(vertices_mm)
    for i in range(n):
        prev_v = vertices_mm[(i - 1) % n]
        curr_v = vertices_mm[i]
        next_v = vertices_mm[(i + 1) % n]
        angle = _interior_angle_deg(prev_v, curr_v, next_v)
        # Accept 90° or 270° (reflex)
        if not (
            abs(angle - 90.0) <= _ANGLE_TOLERANCE_DEG
            or abs(angle - 270.0) <= _ANGLE_TOLERANCE_DEG
        ):
            return False
    return True


def _count_reflex_vertices(vertices_mm: list[list[float]]) -> int:
    """Count vertices where the interior angle is reflex (≈270°) for a CCW polygon.

    Determines orientation first, then uses signed cross product sign to
    identify reflex corners.

    Args:
        vertices_mm: Ordered polygon vertices.

    Returns:
        Number of reflex (concave) vertices.
    """
    n = len(vertices_mm)
    # Determine polygon orientation via signed area
    signed_area = 0.0
    for i in range(n):
        x0, y0 = vertices_mm[i]
        x1, y1 = vertices_mm[(i + 1) % n]
        signed_area += (x0 * y1) - (x1 * y0)
    # CCW → signed_area > 0; CW → signed_area < 0
    ccw = signed_area > 0

    reflex = 0
    for i in range(n):
        prev_v = vertices_mm[(i - 1) % n]
        curr_v = vertices_mm[i]
        next_v = vertices_mm[(i + 1) % n]
        cross = _signed_cross(prev_v, curr_v, next_v)
        # Reflex: cross sign opposite to polygon winding
        if ccw and cross < 0:
            reflex += 1
        elif not ccw and cross > 0:
            reflex += 1
    return reflex


def _classify_8_vertex_shape(vertices_mm: list[list[float]]) -> str:
    """Distinguish T_shape from U_shape for 8-vertex rectilinear polygons.

    Key geometric difference:
      - U_shape: the concave notch opens all the way through — the two reflex
        vertices are adjacent in the vertex sequence (index gap = 1).
        Example: ㄷ-shape where the open side is on the right.
      - T_shape: the concave notch is cut from one face but does NOT pass
        through to the opposite face — the two reflex vertices are separated
        by at least 2 convex vertices (index gap >= 2) on each side.
        Example: ㅜ-shape where the notch is in the middle of the top edge.

    Args:
        vertices_mm: 8-vertex ordered polygon (already confirmed all-right-angle,
            exactly 2 reflex vertices).

    Returns:
        "T_shape", "U_shape", or "irregular".
    """
    n = len(vertices_mm)
    signed_area = 0.0
    for i in range(n):
        x0, y0 = vertices_mm[i]
        x1, y1 = vertices_mm[(i + 1) % n]
        signed_area += (x0 * y1) - (x1 * y0)
    ccw = signed_area > 0

    reflex_indices: list[int] = []
    for i in range(n):
        prev_v = vertices_mm[(i - 1) % n]
        curr_v = vertices_mm[i]
        next_v = vertices_mm[(i + 1) % n]
        cross = _signed_cross(prev_v, curr_v, next_v)
        if (ccw and cross < 0) or (not ccw and cross > 0):
            reflex_indices.append(i)

    if len(reflex_indices) != 2:
        return "irregular"

    i0, i1 = reflex_indices[0], reflex_indices[1]
    # Circular distance between the two reflex indices
    gap = min(abs(i1 - i0), n - abs(i1 - i0))

    # Adjacent reflex vertices (gap == 1) → U_shape
    # Non-adjacent (gap >= 2) → T_shape
    if gap == 1:
        return "U_shape"
    return "T_shape"
