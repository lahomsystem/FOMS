"""C2: Outline → 3D Extrusion — Unit Tests.

Covers:
  1.  rect polygon → 1 module, valid assembly
  2.  L_shape polygon → 2 modules
  3.  T_shape polygon → 2 modules
  4.  U_shape polygon → 3 modules
  5.  invalid polygon (self-intersecting) → blocking_reason
  6.  depth_mm <= 0 → blocking_reason
  7.  Assembly schema_version is "v2"
  8.  Module dimensions match rect dimensions
  9.  Each module has ep_left, ep_right, base, top components
  10. outline_polygon stored in assembly custom_props
"""

from __future__ import annotations

import pytest

from foms.services.designer.outline_to_3d import outline_to_3d

# ── Fixtures (reuse polygon defs from C1 tests) ──────────────────────────────

RECT_4V = [
    [0.0, 0.0],
    [2400.0, 0.0],
    [2400.0, 2000.0],
    [0.0, 2000.0],
]

L_SHAPE_6V = [
    [0.0, 0.0],
    [2288.0, 0.0],
    [2288.0, 1880.0],
    [1376.0, 1880.0],
    [1376.0, 2225.0],
    [0.0, 2225.0],
]

T_SHAPE_8V = [
    [500.0, 0.0],
    [2500.0, 0.0],
    [2500.0, 800.0],
    [3000.0, 800.0],
    [3000.0, 2000.0],
    [0.0, 2000.0],
    [0.0, 800.0],
    [500.0, 800.0],
]

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

BOWTIE_4V = [
    [0.0, 0.0],
    [1000.0, 1000.0],
    [1000.0, 0.0],
    [0.0, 1000.0],
]

_DEPTH = 600.0


# ── Test 1: rect → 1 module ──────────────────────────────────────────────────

def test_rect_produces_one_module():
    result = outline_to_3d(RECT_4V, _DEPTH)
    assert result.blocking_reasons == []
    modules = result.design_graph["assembly"]["modules"]
    assert len(modules) == 1


# ── Test 2: L_shape → 2 modules ─────────────────────────────────────────────

def test_l_shape_produces_two_modules():
    result = outline_to_3d(L_SHAPE_6V, _DEPTH)
    assert result.blocking_reasons == []
    modules = result.design_graph["assembly"]["modules"]
    assert len(modules) == 2


# ── Test 3: T_shape → 2 modules ─────────────────────────────────────────────

def test_t_shape_produces_two_modules():
    result = outline_to_3d(T_SHAPE_8V, _DEPTH)
    assert result.blocking_reasons == []
    modules = result.design_graph["assembly"]["modules"]
    assert len(modules) == 2


# ── Test 4: U_shape → 3 modules ─────────────────────────────────────────────

def test_u_shape_produces_three_modules():
    result = outline_to_3d(U_SHAPE_8V, _DEPTH)
    assert result.blocking_reasons == []
    modules = result.design_graph["assembly"]["modules"]
    assert len(modules) == 3


# ── Test 5: self-intersecting → blocking ─────────────────────────────────────

def test_self_intersecting_polygon_is_blocked():
    result = outline_to_3d(BOWTIE_4V, _DEPTH)
    assert len(result.blocking_reasons) > 0
    assert "outline_polygon_invalid" in result.blocking_reasons[0]
    assert result.design_graph == {}


# ── Test 6: depth_mm <= 0 → blocking ────────────────────────────────────────

def test_non_positive_depth_is_blocked():
    result = outline_to_3d(RECT_4V, 0.0)
    assert len(result.blocking_reasons) > 0
    assert "depth_mm_must_be_positive" in result.blocking_reasons[0]
    assert result.design_graph == {}


# ── Test 7: schema_version is v2 ─────────────────────────────────────────────

def test_assembly_schema_version_is_v2():
    result = outline_to_3d(RECT_4V, _DEPTH)
    assert result.design_graph["schema_version"] == "v2"


# ── Test 8: module dimensions match rect dimensions ───────────────────────────

def test_rect_module_dimensions_match_polygon():
    result = outline_to_3d(RECT_4V, _DEPTH)
    mod = result.design_graph["assembly"]["modules"][0]
    assert mod["dimensions"]["width_mm"] == 2400
    assert mod["dimensions"]["height_mm"] == 2000
    assert mod["dimensions"]["depth_mm"] == int(_DEPTH)


# ── Test 9: each module has ep_left, ep_right, base, top ─────────────────────

def test_rect_module_has_structural_components():
    result = outline_to_3d(RECT_4V, _DEPTH)
    mod = result.design_graph["assembly"]["modules"][0]
    roles = {c["role"] for c in mod["components"]}
    assert "left_ep" in roles
    assert "right_ep" in roles
    assert "base" in roles
    assert "top" in roles


# ── Test 10: outline_polygon stored in custom_props ──────────────────────────

def test_outline_polygon_stored_in_custom_props():
    result = outline_to_3d(L_SHAPE_6V, _DEPTH, furniture_type="custom_storage")
    cp = result.design_graph["assembly"]["custom_props"]["outline_polygon"]
    assert cp["shape_type"] == "L_shape"
    assert cp["vertices_mm"] == L_SHAPE_6V
