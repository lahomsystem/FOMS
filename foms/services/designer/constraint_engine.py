"""FOMS Brain Design Kernel V1 — Constraint Engine / Hard Validator V2.

DK-B3: manufacturing-logic constraint validation.

Rules:
1. outer_width == ep_left + module_sum + ep_right
2. component dimensions within parent boundary
3. material max size check
4. door gap rule
5. panel thickness rule
6. duplicate UUID check
7. severity: error / warning / info
"""

from __future__ import annotations

from foms.services.designer.ontology_types import (
    DesignGraph,
    ConstraintResult,
    ConstraintViolation,
)
from foms.services.designer.component_catalog import get_material

# ──────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────

MIN_PANEL_THICKNESS = 9     # mm
MAX_PANEL_THICKNESS = 36    # mm
MIN_DOOR_GAP = 1            # mm
MIN_DIMENSION = 1           # mm
OUTER_WIDTH_TOLERANCE = 5   # mm (공차)


# ──────────────────────────────────────────────────────────
# Individual rule validators
# ──────────────────────────────────────────────────────────

def _check_outer_width_sum(graph: DesignGraph) -> list[ConstraintViolation]:
    """Rule: outer_width == ep_left + module_sum + ep_right."""
    violations: list[ConstraintViolation] = []
    asm = graph.assembly
    if not asm.modules:
        return violations

    module_sum = sum(m.dimensions.width for m in asm.modules)
    expected = asm.ep_left + module_sum + asm.ep_right
    actual = asm.dimensions.width
    diff = abs(actual - expected)

    if diff > OUTER_WIDTH_TOLERANCE:
        violations.append(ConstraintViolation(
            constraint_id="outer_width_sum",
            severity="error",
            code="OUTER_WIDTH_MISMATCH",
            message=(
                f"외경 폭 불일치: 전체 {actual}mm ≠ 좌EP({asm.ep_left}) "
                f"+ 모듈합({module_sum}) + 우EP({asm.ep_right}) = {expected}mm"
            ),
            path="assembly.dimensions.width",
        ))
    return violations


def _check_component_within_parent(graph: DesignGraph) -> list[ConstraintViolation]:
    """Rule: each component must be within its parent boundary (absolute coords)."""
    violations: list[ConstraintViolation] = []

    asm = graph.assembly
    asm_right = asm.dimensions.width
    asm_top = asm.dimensions.height

    for comp in graph.components:
        if comp.parent_id:
            parent_mod = graph.get_module(comp.parent_id)
            if parent_mod is None:
                continue
            # Parent boundary in absolute coordinates
            parent_abs_right = parent_mod.position.x + parent_mod.dimensions.width
            parent_abs_top = parent_mod.position.y + parent_mod.dimensions.height
        else:
            # Parent is assembly (origin at 0,0)
            parent_abs_right = asm_right
            parent_abs_top = asm_top

        comp_right = comp.position.x + comp.dimensions.width
        comp_top = comp.position.y + comp.dimensions.height

        if comp_right > parent_abs_right + OUTER_WIDTH_TOLERANCE:
            violations.append(ConstraintViolation(
                constraint_id="within_bounds",
                severity="error",
                code="COMPONENT_EXCEEDS_PARENT_WIDTH",
                message=(
                    f"부재 '{comp.id}' 가 부모 폭 경계를 초과: "
                    f"x({comp.position.x}) + w({comp.dimensions.width}) = {comp_right} "
                    f"> parent_right({parent_abs_right})"
                ),
                path=f"components[{comp.id}].position.x",
            ))

        if comp_top > parent_abs_top + OUTER_WIDTH_TOLERANCE:
            violations.append(ConstraintViolation(
                constraint_id="within_bounds",
                severity="error",
                code="COMPONENT_EXCEEDS_PARENT_HEIGHT",
                message=(
                    f"부재 '{comp.id}' 가 부모 높이 경계를 초과: "
                    f"y({comp.position.y}) + h({comp.dimensions.height}) = {comp_top} "
                    f"> parent_top({parent_abs_top})"
                ),
                path=f"components[{comp.id}].position.y",
            ))

    return violations


def _check_material_max_size(graph: DesignGraph) -> list[ConstraintViolation]:
    """Rule: component dimensions must not exceed material max size.

    Checks in optimal orientation (short side vs max_width, long side vs max_height).
    Back panels (role='back_panel') are exempt — they are assembled from multiple sheets.
    """
    violations: list[ConstraintViolation] = []

    for comp in graph.components:
        if not comp.material_id:
            continue
        mat = get_material(comp.material_id)
        if not mat:
            continue
        if mat.category not in ("board", "door"):
            continue

        # Back panels are multi-piece; skip max-size check
        if comp.role == "back_panel":
            continue

        # Get the two non-thickness dimensions (the flat face dimensions)
        dims = sorted([comp.dimensions.width, comp.dimensions.height, comp.dimensions.depth],
                      reverse=True)
        # Remove the thickness (smallest dimension) if it matches
        flat_dims = [d for d in dims if d > mat.thickness] if mat.thickness > 0 else dims[:2]
        if not flat_dims:
            flat_dims = dims[:2]
        flat_dims = sorted(flat_dims, reverse=True)[:2]  # [long_side, short_side]

        long_side = flat_dims[0] if flat_dims else 0
        short_side = flat_dims[1] if len(flat_dims) > 1 else 0

        # Check: short_side ≤ max_width AND long_side ≤ max_height (optimal orientation)
        # Also try rotated: short_side ≤ max_height AND long_side ≤ max_width
        mat_long = max(mat.max_width, mat.max_height)
        mat_short = min(mat.max_width, mat.max_height)

        if long_side > mat_long:
            violations.append(ConstraintViolation(
                constraint_id="max_size",
                severity="error",
                code="MATERIAL_MAX_SIZE_EXCEEDED",
                message=(
                    f"부재 '{comp.id}' 의 최대 치수 {long_side}mm 가 "
                    f"자재 '{mat.id}' 최대 규격 {mat_long}mm 초과"
                ),
                path=f"components[{comp.id}].dimensions",
            ))
        elif short_side > mat_short:
            violations.append(ConstraintViolation(
                constraint_id="max_size",
                severity="error",
                code="MATERIAL_MAX_SIZE_EXCEEDED",
                message=(
                    f"부재 '{comp.id}' 의 단변 {short_side}mm 가 "
                    f"자재 '{mat.id}' 단변 최대 규격 {mat_short}mm 초과"
                ),
                path=f"components[{comp.id}].dimensions",
            ))

    return violations


def _check_door_gap(graph: DesignGraph) -> list[ConstraintViolation]:
    """Rule: door height must be <= assembly inner height (with gap)."""
    violations: list[ConstraintViolation] = []
    asm = graph.assembly

    door_components = [c for c in graph.components if c.kind == "door"]
    if not door_components:
        return violations

    inner_height = asm.dimensions.height - asm.top_sr - asm.base_height - MIN_DOOR_GAP

    for door in door_components:
        if door.dimensions.height > inner_height:
            violations.append(ConstraintViolation(
                constraint_id="door_gap_rule",
                severity="error",
                code="DOOR_HEIGHT_EXCEEDS_INNER",
                message=(
                    f"도어 '{door.id}' 높이 {door.dimensions.height}mm 가 "
                    f"내부 유효 높이 {inner_height}mm 초과 (SR + 받침대 + 간격 공제 후)"
                ),
                path=f"components[{door.id}].dimensions.height",
            ))

    return violations


def _check_panel_thickness(graph: DesignGraph) -> list[ConstraintViolation]:
    """Rule: panel thickness must be within allowed range.

    SR and base are spacer components — their height dimension is their functional
    depth, not their sheet thickness. Only check actual panel/shelf kinds.
    """
    violations: list[ConstraintViolation] = []

    panel_kinds = {"panel", "shelf"}  # ep/sr/base are spacers; skip thickness check

    for comp in graph.components:
        if comp.kind not in panel_kinds:
            continue
        # thickness is the smallest non-zero dimension
        dims = [comp.dimensions.width, comp.dimensions.height, comp.dimensions.depth]
        thickness = min(d for d in dims if d > 0)

        if thickness < MIN_PANEL_THICKNESS:
            violations.append(ConstraintViolation(
                constraint_id="thickness_rule",
                severity="warning",
                code="PANEL_THICKNESS_TOO_THIN",
                message=(
                    f"부재 '{comp.id}' 최소 치수 {thickness}mm 가 "
                    f"권장 최소 두께 {MIN_PANEL_THICKNESS}mm 미만"
                ),
                path=f"components[{comp.id}].dimensions",
            ))
        elif thickness > MAX_PANEL_THICKNESS:
            violations.append(ConstraintViolation(
                constraint_id="thickness_rule",
                severity="warning",
                code="PANEL_THICKNESS_TOO_THICK",
                message=(
                    f"부재 '{comp.id}' 최소 치수 {thickness}mm 가 "
                    f"권장 최대 두께 {MAX_PANEL_THICKNESS}mm 초과"
                ),
                path=f"components[{comp.id}].dimensions",
            ))

    return violations


def _check_duplicate_uuid(graph: DesignGraph) -> list[ConstraintViolation]:
    """Rule: no duplicate component UUIDs."""
    violations: list[ConstraintViolation] = []
    seen: set[str] = set()

    for i, comp in enumerate(graph.components):
        if comp.id in seen:
            violations.append(ConstraintViolation(
                constraint_id="no_duplicate_uuid",
                severity="error",
                code="DUPLICATE_COMPONENT_UUID",
                message=f"부재 UUID '{comp.id}' 가 중복됩니다.",
                path=f"components[{i}].id",
            ))
        else:
            seen.add(comp.id)

    return violations


def _check_basic_dimensions(graph: DesignGraph) -> list[ConstraintViolation]:
    """Rule: all dimensions must be > 0."""
    violations: list[ConstraintViolation] = []
    asm = graph.assembly

    for dim_name in ("width", "height", "depth"):
        val = getattr(asm.dimensions, dim_name)
        if val <= 0:
            violations.append(ConstraintViolation(
                constraint_id="basic_dimensions",
                severity="error",
                code=f"ASSEMBLY_{dim_name.upper()}_INVALID",
                message=f"Assembly {dim_name} 은 0보다 커야 합니다 (현재: {val})",
                path=f"assembly.dimensions.{dim_name}",
            ))

    for comp in graph.components:
        for dim_name in ("width", "height", "depth"):
            val = getattr(comp.dimensions, dim_name)
            if val <= 0:
                violations.append(ConstraintViolation(
                    constraint_id="basic_dimensions",
                    severity="error",
                    code="COMPONENT_DIM_ZERO",
                    message=f"부재 '{comp.id}' 의 {dim_name} 은 0보다 커야 합니다.",
                    path=f"components[{comp.id}].dimensions.{dim_name}",
                ))

    return violations


# ──────────────────────────────────────────────────────────
# Main validator (schema v2)
# ──────────────────────────────────────────────────────────

def validate_design_graph(graph: DesignGraph) -> ConstraintResult:
    """
    Run all hard constraint rules against a DesignGraph.

    Returns ConstraintResult. If valid is False, callers MUST NOT persist.
    """
    all_violations: list[ConstraintViolation] = []

    rules = [
        _check_basic_dimensions,
        _check_duplicate_uuid,
        _check_outer_width_sum,
        _check_component_within_parent,
        _check_material_max_size,
        _check_door_gap,
        _check_panel_thickness,
    ]

    for rule_fn in rules:
        try:
            all_violations.extend(rule_fn(graph))
        except Exception as exc:
            all_violations.append(ConstraintViolation(
                constraint_id="constraint_engine_error",
                severity="error",
                code="CONSTRAINT_RULE_ERROR",
                message=f"제약 규칙 실행 오류 ({rule_fn.__name__}): {exc}",
                path="$",
            ))

    has_errors = any(v.severity == "error" for v in all_violations)
    return ConstraintResult(valid=not has_errors, violations=all_violations)


def validate_design_graph_from_dict(design_json: dict) -> ConstraintResult:
    """Validate a raw dict as schema v2 DesignGraph."""
    from foms.services.designer.ontology_types import DesignGraph as _DesignGraph
    try:
        graph = _DesignGraph.from_dict(design_json)
    except Exception as exc:
        return ConstraintResult(
            valid=False,
            violations=[ConstraintViolation(
                constraint_id="parse_error",
                severity="error",
                code="DESIGN_PARSE_ERROR",
                message=f"Design graph 파싱 실패: {exc}",
                path="$",
            )],
        )
    return validate_design_graph(graph)
