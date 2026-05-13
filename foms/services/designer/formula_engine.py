"""FOMS Brain Design Kernel V1 — Formula Engine (Python backend).

DK-B2: deterministic formula evaluator.

Features:
- assembly/module/component dimension 참조
- parent dimension 변경 시 child 재계산
- mm 정수 normalize
- circular formula 감지
"""

from __future__ import annotations

import math
from typing import Any

from foms.services.designer.ontology_types import DesignGraph, Component

# ──────────────────────────────────────────────────────────
# Formula variable resolution
# ──────────────────────────────────────────────────────────

_SAFE_MATH = {
    "abs": abs,
    "round": round,
    "floor": math.floor,
    "ceil": math.ceil,
    "int": int,
}


def _build_context(graph: DesignGraph, component: Component | None = None) -> dict[str, Any]:
    """Build formula evaluation context from design graph."""
    asm = graph.assembly
    ctx: dict[str, Any] = {
        # assembly-level shortcuts
        "outer_width": asm.dimensions.width,
        "outer_height": asm.dimensions.height,
        "outer_depth": asm.dimensions.depth,
        "total_width": asm.dimensions.width,
        "total_height": asm.dimensions.height,
        "total_depth": asm.dimensions.depth,
        "ep_left": asm.ep_left,
        "ep_right": asm.ep_right,
        "ep_top": asm.ep_top,
        "base": asm.base_height,
        "top_sr": asm.top_sr,
        "module_count": asm.module_count,
        # common gaps / constants
        "gap": 2,      # 도어 간격 기본값 2mm
        "pb_t": 18,    # PB 기본 두께
        "back_t": 9,   # 후판 두께
    }

    # assembly namespace
    ctx["assembly"] = {
        "width": asm.dimensions.width,
        "height": asm.dimensions.height,
        "depth": asm.dimensions.depth,
        "ep_left": asm.ep_left,
        "ep_right": asm.ep_right,
        "ep_top": asm.ep_top,
        "base_height": asm.base_height,
        "top_sr": asm.top_sr,
        "module_count": asm.module_count,
    }

    if component:
        ctx["this"] = {
            "width": component.dimensions.width,
            "height": component.dimensions.height,
            "depth": component.dimensions.depth,
        }
        # parent (module) dimension lookup
        if component.parent_id:
            parent_mod = graph.get_module(component.parent_id)
            if parent_mod:
                ctx["parent"] = {
                    "width": parent_mod.dimensions.width,
                    "height": parent_mod.dimensions.height,
                    "depth": parent_mod.dimensions.depth,
                }

    return ctx


def _normalize_mm(value: float) -> int:
    """Round formula result to nearest mm integer."""
    return int(round(value))


def _eval_expr(expression: str, context: dict[str, Any]) -> int:
    """
    Safely evaluate a formula expression string.
    Supports only arithmetic + context variables.
    """
    try:
        result = eval(  # noqa: S307
            expression,
            {"__builtins__": {}},
            {**_SAFE_MATH, **context},
        )
        if not isinstance(result, (int, float)):
            raise ValueError(f"공식 결과가 숫자가 아닙니다: {result!r}")
        return _normalize_mm(result)
    except Exception as exc:
        raise FormulaError(f"공식 평가 실패: {expression!r} — {exc}") from exc


# ──────────────────────────────────────────────────────────
# Built-in formula library
# ──────────────────────────────────────────────────────────

BUILTIN_FORMULAS: dict[str, dict[str, Any]] = {
    "module_width": {
        "expression": "(outer_width - ep_left - ep_right) / module_count",
        "description": "모듈 폭 = (전체 폭 - 좌EP - 우EP) / 모듈수",
    },
    "door_height": {
        "expression": "outer_height - top_sr - base - gap",
        "description": "도어 높이 = 전체 높이 - 상부SR - 받침대 - 간격",
    },
    "inner_height": {
        "expression": "outer_height - top_sr - base - pb_t * 2",
        "description": "내부 유효 높이 = 전체 높이 - SR - 받침대 - 상하판",
    },
    "inner_width_per_module": {
        "expression": "(outer_width - ep_left - ep_right - pb_t * (module_count - 1)) / module_count",
        "description": "모듈 내부 폭 (칸막이 판재 포함 공제)",
    },
    "back_panel_width": {
        "expression": "outer_width",
        "description": "후판 폭 = 전체 폭",
    },
    "back_panel_height": {
        "expression": "outer_height",
        "description": "후판 높이 = 전체 높이",
    },
    "side_panel_height": {
        "expression": "outer_height",
        "description": "측판 높이 = 전체 높이",
    },
    "shelf_width": {
        "expression": "parent.width - pb_t * 2",
        "description": "선반 폭 = 모듈 폭 - 좌우 판재 두께",
    },
}


def evaluate_formula(
    formula_id: str,
    graph: DesignGraph,
    component: Component | None = None,
    overrides: dict[str, Any] | None = None,
) -> int:
    """Evaluate a built-in formula by id against the design graph.

    Args:
        formula_id: key in BUILTIN_FORMULAS
        graph: current DesignGraph
        component: optional component context (for 'parent'/'this' refs)
        overrides: extra variable overrides

    Returns:
        mm integer result

    Raises:
        FormulaError on unknown formula or evaluation failure.
    """
    if formula_id not in BUILTIN_FORMULAS:
        raise FormulaError(f"알 수 없는 공식: {formula_id!r}")

    formula = BUILTIN_FORMULAS[formula_id]
    ctx = _build_context(graph, component)
    if overrides:
        ctx.update(overrides)
    return _eval_expr(formula["expression"], ctx)


def evaluate_expression(
    expression: str,
    graph: DesignGraph,
    component: Component | None = None,
    overrides: dict[str, Any] | None = None,
) -> int:
    """Evaluate an arbitrary formula expression string against the design graph."""
    ctx = _build_context(graph, component)
    if overrides:
        ctx.update(overrides)
    return _eval_expr(expression, ctx)


# ──────────────────────────────────────────────────────────
# Circular dependency detection
# ──────────────────────────────────────────────────────────

def check_circular_formulas(formula_deps: dict[str, list[str]]) -> list[str]:
    """
    Detect circular dependencies in a formula dependency graph.

    Args:
        formula_deps: {formula_id: [dependent_formula_ids]}

    Returns:
        List of formula ids that form cycles (empty if none).
    """
    visited: set[str] = set()
    in_stack: set[str] = set()
    cycles: list[str] = []

    def dfs(node: str) -> bool:
        visited.add(node)
        in_stack.add(node)
        for dep in formula_deps.get(node, []):
            if dep not in visited:
                if dfs(dep):
                    cycles.append(node)
                    return True
            elif dep in in_stack:
                cycles.append(node)
                return True
        in_stack.discard(node)
        return False

    for fid in formula_deps:
        if fid not in visited:
            dfs(fid)

    return cycles


# ──────────────────────────────────────────────────────────
# Batch recalculate: apply formulas to all components in graph
# ──────────────────────────────────────────────────────────

def recalculate_graph(graph: DesignGraph) -> list[dict]:
    """
    Recalculate all components that have formula_refs.
    Returns list of {component_id, prop, before, after} dicts for audit.
    """
    changes: list[dict] = []

    for comp in graph.components:
        for formula_id in comp.formula_refs:
            if formula_id not in BUILTIN_FORMULAS:
                continue
            try:
                new_value = evaluate_formula(formula_id, graph, comp)
                # Determine which dimension this formula targets
                target = BUILTIN_FORMULAS[formula_id].get("description", "")
                if "높이" in target or "height" in formula_id:
                    old = comp.dimensions.height
                    if old != new_value:
                        changes.append({
                            "component_id": comp.id,
                            "prop": "dimensions.height",
                            "before": old,
                            "after": new_value,
                        })
                        comp.dimensions.height = new_value
                elif "폭" in target or "width" in formula_id:
                    old = comp.dimensions.width
                    if old != new_value:
                        changes.append({
                            "component_id": comp.id,
                            "prop": "dimensions.width",
                            "before": old,
                            "after": new_value,
                        })
                        comp.dimensions.width = new_value
            except FormulaError:
                pass  # non-blocking; constraint engine will catch invalid states

    return changes


# ──────────────────────────────────────────────────────────
# Error
# ──────────────────────────────────────────────────────────

class FormulaError(Exception):
    """Raised when a formula cannot be evaluated."""
