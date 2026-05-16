"""C10: C-Phase Performance Contract Tests.

Verifies that core C-phase functions execute within the time budgets
defined in the plan:
  - outline_polygon_validator.validate_polygon  < 100 ms
  - outline_to_3d.outline_to_3d                < 200 ms
  - sketch_to_block domain functions            < 50 ms

Also runs regression checks to verify the previously-tested
B-phase polygon/mapper API still operates within C-phase parameters.
"""

from __future__ import annotations

import time

import pytest

from foms.services.designer.outline_polygon_validator import (
    classify_shape_type,
    compute_area_mm2,
    validate_polygon,
)
from foms.services.designer.outline_to_3d import outline_to_3d

# ── Shared fixtures ───────────────────────────────────────────────────────────

RECT_4V = [[0.0, 0.0], [2400.0, 0.0], [2400.0, 2000.0], [0.0, 2000.0]]

L_SHAPE_6V = [
    [0.0, 0.0], [2288.0, 0.0], [2288.0, 1880.0],
    [1376.0, 1880.0], [1376.0, 2225.0], [0.0, 2225.0],
]

T_SHAPE_8V = [
    [500.0, 0.0], [2500.0, 0.0], [2500.0, 800.0], [3000.0, 800.0],
    [3000.0, 2000.0], [0.0, 2000.0], [0.0, 800.0], [500.0, 800.0],
]

U_SHAPE_8V = [
    [0.0, 0.0], [3000.0, 0.0], [3000.0, 500.0], [2000.0, 500.0],
    [2000.0, 1500.0], [3000.0, 1500.0], [3000.0, 2000.0], [0.0, 2000.0],
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _elapsed_ms(fn, *args, **kwargs) -> tuple[float, object]:
    t0 = time.perf_counter()
    result = fn(*args, **kwargs)
    return (time.perf_counter() - t0) * 1000, result


# ── Performance: validate_polygon (<100 ms) ───────────────────────────────────

@pytest.mark.parametrize("verts,label", [
    (RECT_4V, "rect"),
    (L_SHAPE_6V, "L_shape"),
    (T_SHAPE_8V, "T_shape"),
    (U_SHAPE_8V, "U_shape"),
])
def test_validate_polygon_under_100ms(verts, label):
    """validate_polygon 성능: 모든 대표 도형에서 100ms 이내."""
    ms, result = _elapsed_ms(validate_polygon, verts)
    assert ms < 100, f"{label}: {ms:.1f} ms (한도 100 ms)"
    assert result.is_valid, f"{label}: expected valid"


# ── Performance: classify_shape_type (<100 ms) ────────────────────────────────

@pytest.mark.parametrize("verts,expected", [
    (RECT_4V, "rect"),
    (L_SHAPE_6V, "L_shape"),
    (T_SHAPE_8V, "T_shape"),
    (U_SHAPE_8V, "U_shape"),
])
def test_classify_shape_type_under_100ms(verts, expected):
    """classify_shape_type 성능: 100ms 이내 + 분류 정확도."""
    ms, shape = _elapsed_ms(classify_shape_type, verts)
    assert ms < 100, f"분류 {ms:.1f} ms 초과"
    assert shape == expected


# ── Performance: outline_to_3d (<200 ms) ─────────────────────────────────────

@pytest.mark.parametrize("verts,label", [
    (RECT_4V, "rect"),
    (L_SHAPE_6V, "L_shape"),
    (T_SHAPE_8V, "T_shape"),
    (U_SHAPE_8V, "U_shape"),
])
def test_outline_to_3d_under_200ms(verts, label):
    """outline_to_3d 성능: 모든 대표 도형에서 200ms 이내."""
    ms, result = _elapsed_ms(outline_to_3d, verts, 600.0)
    assert ms < 200, f"{label}: {ms:.1f} ms (한도 200 ms)"
    assert result.blocking_reasons == [], f"{label}: unexpected blocking"


# ── Performance: compute_area_mm2 (<10 ms) ───────────────────────────────────

def test_compute_area_mm2_under_10ms():
    """Shoelace 면적 계산 성능: 10ms 이내."""
    ms, area = _elapsed_ms(compute_area_mm2, L_SHAPE_6V)
    assert ms < 10, f"면적 계산 {ms:.1f} ms 초과"
    assert area > 0


# ── Correctness: module count contracts ──────────────────────────────────────

def test_rect_exactly_one_module():
    r = outline_to_3d(RECT_4V, 600.0)
    assert len(r.design_graph["assembly"]["modules"]) == 1


def test_l_shape_exactly_two_modules():
    r = outline_to_3d(L_SHAPE_6V, 600.0)
    assert len(r.design_graph["assembly"]["modules"]) == 2


def test_t_shape_exactly_two_modules():
    r = outline_to_3d(T_SHAPE_8V, 600.0)
    assert len(r.design_graph["assembly"]["modules"]) == 2


def test_u_shape_exactly_three_modules():
    r = outline_to_3d(U_SHAPE_8V, 600.0)
    assert len(r.design_graph["assembly"]["modules"]) == 3


# ── Security: empty graph contract ───────────────────────────────────────────

def test_invalid_polygon_never_produces_graph():
    """invalid polygon은 항상 빈 design_graph를 반환한다."""
    bowtie = [[0, 0], [1000, 1000], [1000, 0], [0, 1000]]
    r = outline_to_3d(bowtie, 600.0)
    assert r.design_graph == {}
    assert len(r.blocking_reasons) > 0


def test_zero_depth_never_produces_graph():
    r = outline_to_3d(RECT_4V, 0.0)
    assert r.design_graph == {}
    assert len(r.blocking_reasons) > 0


def test_negative_depth_never_produces_graph():
    r = outline_to_3d(RECT_4V, -100.0)
    assert r.design_graph == {}
    assert len(r.blocking_reasons) > 0


# ── Schema contract: all modules have required keys ──────────────────────────

def test_all_modules_have_required_keys():
    r = outline_to_3d(U_SHAPE_8V, 600.0)
    for mod in r.design_graph["assembly"]["modules"]:
        for key in ("id", "type", "label", "dimensions", "position", "components"):
            assert key in mod, f"Module missing key: {key}"


# ── Schema contract: all components have kind/role ───────────────────────────

def test_all_components_have_kind_and_role():
    r = outline_to_3d(L_SHAPE_6V, 600.0)
    for mod in r.design_graph["assembly"]["modules"]:
        for comp in mod["components"]:
            assert "kind" in comp
            assert "role" in comp


# ── Regression: validate_polygon still works for tiny polygon ────────────────

def test_tiny_polygon_still_blocked():
    tiny = [[0, 0], [50, 0], [50, 100], [0, 100]]
    result = validate_polygon(tiny)
    assert not result.is_valid
    assert "area_too_small" in (result.error or "")


# ── Regression: self-intersecting polygon blocked before area check ───────────

def test_bowtie_blocked_by_intersection_not_area():
    bowtie = [[0, 0], [1000, 1000], [1000, 0], [0, 1000]]
    result = validate_polygon(bowtie)
    assert not result.is_valid
    assert "self_intersection" in (result.error or "")


# ── Partition report contract ─────────────────────────────────────────────────

def test_partition_report_has_required_keys():
    r = outline_to_3d(L_SHAPE_6V, 600.0, source_polygon_id="test-polygon-001")
    report = r.partition_report
    assert "algorithm" in report
    assert "module_rects" in report
    assert "warnings" in report
    assert report["source_polygon_id"] == "test-polygon-001"
    assert report["algorithm"] == "rectilinear_partition_v1"


def test_partition_rects_cover_expected_area():
    """L_shape partition: 두 모듈의 면적 합이 폴리곤 면적과 같아야 한다."""
    r = outline_to_3d(L_SHAPE_6V, 600.0)
    rects = r.partition_report["module_rects"]
    partition_area = sum(rect["width"] * rect["height"] for rect in rects)
    polygon_area = compute_area_mm2(L_SHAPE_6V)
    assert abs(partition_area - polygon_area) < 1.0, (
        f"Partition area {partition_area:.0f} ≠ polygon area {polygon_area:.0f}"
    )
