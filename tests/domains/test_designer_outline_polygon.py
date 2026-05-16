"""C1: Outline Polygon Validator — Unit Tests.

Covers:
  1.  rect 4-vertex polygon → valid, shape_type="rect"
  2.  L_shape 6-vertex polygon → valid, shape_type="L_shape"
  3.  L_shape area accuracy (Shoelace formula)
  4.  3-vertex polygon → invalid (too few vertices)
  5.  Tiny polygon (area < 10 000 mm²) → invalid
  6.  Self-intersecting polygon → invalid
  7.  T_shape 8-vertex polygon → shape_type="T_shape"
  8.  U_shape 8-vertex polygon → shape_type="U_shape"
  9.  Irregular polygon → shape_type="irregular"
  10. outline_polygon=None in extraction → mapping_report has no outline_shape_type
"""

from __future__ import annotations

import pytest

from foms.services.designer.outline_polygon_validator import (
    PolygonValidationResult,
    classify_shape_type,
    compute_area_mm2,
    validate_polygon,
)
from foms.services.designer.layout_graph_mapper import (
    LayoutMappingInput,
    map_layout_to_design_graph,
)


# ──────────────────────────────────────────────────────────
# Shared polygon fixtures
# ──────────────────────────────────────────────────────────

# Simple 2400×2000 rectangle (CW order)
RECT_4V = [
    [0.0, 0.0],
    [2400.0, 0.0],
    [2400.0, 2000.0],
    [0.0, 2000.0],
]

# L_shape: 2288×2225 with 912×345 notch cut from top-right (CCW order)
# Total area = 2288×2225 − 912×345 = 5 091 000 − 314 640 = 4 776 360 mm²
L_SHAPE_6V = [
    [0.0, 0.0],
    [2288.0, 0.0],
    [2288.0, 1880.0],
    [1376.0, 1880.0],
    [1376.0, 2225.0],
    [0.0, 2225.0],
]
_L_SHAPE_EXPECTED_AREA = 2288 * 2225 - (2288 - 1376) * (2225 - 1880)
# = 5_091_000 - 912 * 345 = 5_091_000 - 314_640 = 4_776_360

# T_shape: 8 vertices — narrow stem at bottom, wide cap at top (ㅜ rotated 180°).
# Cap: x=0–3000, y=800–2000.  Stem: x=500–2500, y=0–800.
# Reflex vertices at index 2 (2500,800) and 7 (500,800).
# gap = min(|7-2|, 8-|7-2|) = min(5, 3) = 3 ≥ 2 → T_shape.
T_SHAPE_8V = [
    [500.0, 0.0],      # 0 — stem bottom-left
    [2500.0, 0.0],     # 1 — stem bottom-right
    [2500.0, 800.0],   # 2 — reflex: stem meets cap right shoulder
    [3000.0, 800.0],   # 3 — cap bottom-right
    [3000.0, 2000.0],  # 4 — cap top-right
    [0.0, 2000.0],     # 5 — cap top-left
    [0.0, 800.0],      # 6 — cap bottom-left
    [500.0, 800.0],    # 7 — reflex: stem meets cap left shoulder
]

# U_shape: 8 vertices — right side open (ㄷ-shape).
# Outer: 3000×2000.  Notch: x 2000–3000, y 500–1500 (right middle removed).
# The two reflex vertices (index 4 and 5) are adjacent (gap=1) → U_shape.
U_SHAPE_8V = [
    [0.0, 0.0],
    [3000.0, 0.0],
    [3000.0, 500.0],
    [2000.0, 500.0],
    [2000.0, 1500.0],
    [3000.0, 1500.0],
    [3000.0, 2000.0],
    [0.0, 2000.0],
]

# Irregular: non-right-angle triangle (only 3 vertices — also too few)
TRIANGLE_3V = [
    [0.0, 0.0],
    [500.0, 1000.0],
    [1000.0, 0.0],
]

# Tiny rect: 50×100 = 5 000 mm² < threshold
TINY_RECT_4V = [
    [0.0, 0.0],
    [50.0, 0.0],
    [50.0, 100.0],
    [0.0, 100.0],
]

# Self-intersecting polygon (bowtie)
BOWTIE_4V = [
    [0.0, 0.0],
    [1000.0, 1000.0],
    [1000.0, 0.0],
    [0.0, 1000.0],
]

# Irregular: 5-vertex polygon with non-right angle
IRREGULAR_5V = [
    [0.0, 0.0],
    [1000.0, 0.0],
    [1200.0, 800.0],
    [600.0, 1500.0],
    [0.0, 1000.0],
]


# ──────────────────────────────────────────────────────────
# Test 1: rect 4-vertex → valid, shape_type="rect"
# ──────────────────────────────────────────────────────────

def test_rect_4v_valid():
    """rect 4꼭짓점 → is_valid=True, shape_type='rect'."""
    result = validate_polygon(RECT_4V)
    assert result.is_valid is True
    assert result.shape_type == "rect"
    assert result.vertex_count == 4
    assert result.error is None


# ──────────────────────────────────────────────────────────
# Test 2: L_shape 6-vertex → valid, shape_type="L_shape"
# ──────────────────────────────────────────────────────────

def test_l_shape_6v_valid():
    """L_shape 6꼭짓점 → is_valid=True, shape_type='L_shape'."""
    result = validate_polygon(L_SHAPE_6V)
    assert result.is_valid is True
    assert result.shape_type == "L_shape"
    assert result.vertex_count == 6
    assert result.error is None


# ──────────────────────────────────────────────────────────
# Test 3: L_shape area accuracy (Shoelace formula)
# ──────────────────────────────────────────────────────────

def test_l_shape_area_accuracy():
    """L_shape 6꼭짓점 area_mm2 계산이 Shoelace 공식으로 정확해야 한다."""
    area = compute_area_mm2(L_SHAPE_6V)
    assert abs(area - _L_SHAPE_EXPECTED_AREA) < 1.0, (
        f"Expected area ≈{_L_SHAPE_EXPECTED_AREA}, got {area}"
    )


# ──────────────────────────────────────────────────────────
# Test 4: 3-vertex → invalid (too few vertices)
# ──────────────────────────────────────────────────────────

def test_triangle_too_few_vertices():
    """3꼭짓점 → is_valid=False (꼭짓점 수 부족)."""
    result = validate_polygon(TRIANGLE_3V)
    assert result.is_valid is False
    assert "too_few_vertices" in (result.error or "")
    assert result.vertex_count == 3


# ──────────────────────────────────────────────────────────
# Test 5: tiny polygon (area < 10 000 mm²) → invalid
# ──────────────────────────────────────────────────────────

def test_tiny_polygon_area_too_small():
    """면적 5 000 mm² → is_valid=False (최소 면적 미달)."""
    result = validate_polygon(TINY_RECT_4V)
    assert result.is_valid is False
    assert "area_too_small" in (result.error or "")


# ──────────────────────────────────────────────────────────
# Test 6: self-intersecting polygon → invalid
# ──────────────────────────────────────────────────────────

def test_self_intersecting_polygon():
    """자가교차 폴리곤(나비넥타이) → is_valid=False."""
    result = validate_polygon(BOWTIE_4V)
    assert result.is_valid is False
    assert "self_intersection" in (result.error or "")


# ──────────────────────────────────────────────────────────
# Test 7: T_shape 8-vertex → shape_type="T_shape"
# ──────────────────────────────────────────────────────────

def test_t_shape_classification():
    """T형 8꼭짓점 → shape_type='T_shape'."""
    shape = classify_shape_type(T_SHAPE_8V)
    assert shape == "T_shape"


# ──────────────────────────────────────────────────────────
# Test 8: U_shape 8-vertex → shape_type="U_shape"
# ──────────────────────────────────────────────────────────

def test_u_shape_classification():
    """U형 8꼭짓점 → shape_type='U_shape'."""
    shape = classify_shape_type(U_SHAPE_8V)
    assert shape == "U_shape"


# ──────────────────────────────────────────────────────────
# Test 9: irregular polygon → shape_type="irregular"
# ──────────────────────────────────────────────────────────

def test_irregular_polygon_classification():
    """비직각 5꼭짓점 → shape_type='irregular'."""
    shape = classify_shape_type(IRREGULAR_5V)
    assert shape == "irregular"


# ──────────────────────────────────────────────────────────
# Test 10: outline_polygon=None in extraction → no outline_shape_type
# ──────────────────────────────────────────────────────────

def test_outline_polygon_none_no_shape_type_in_report():
    """outline_polygon이 None이면 mapping_report에 outline_shape_type이 기록되지 않는다."""
    mapping_input = LayoutMappingInput(
        furniture_type="wardrobe",
        site_size={"width_mm": 3000, "height_mm": 2400, "depth_mm": 600},
        layout_graph={},
        outline_polygon=None,
    )
    result = map_layout_to_design_graph(mapping_input)
    report_dict = result.mapping_report.to_dict()
    assert "outline_shape_type" not in report_dict, (
        "outline_shape_type should not appear when outline_polygon is None"
    )
    assert result.mapping_report.outline_shape_type is None
