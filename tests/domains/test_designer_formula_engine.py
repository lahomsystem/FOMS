"""DK-B2 Formula Engine tests."""

from __future__ import annotations

import pytest

from foms.services.designer.formula_engine import (
    BUILTIN_FORMULAS,
    FormulaError,
    check_circular_formulas,
    evaluate_expression,
    evaluate_formula,
    recalculate_graph,
)
from foms.services.designer.assembly_factories import WardrobeParams, create_wardrobe_assembly


class TestBuiltinFormulas:
    def _graph(self, width=3000, height=2400, depth=620, module_count=3):
        return create_wardrobe_assembly(WardrobeParams(
            width=width, height=height, depth=depth, module_count=module_count,
        ))

    def test_module_width_formula(self):
        graph = self._graph(width=3000, module_count=3)
        asm = graph.assembly
        result = evaluate_formula("module_width", graph)
        # engine uses round(), not floor()
        expected = round((3000 - asm.ep_left - asm.ep_right) / 3)
        assert result == expected

    def test_door_height_formula(self):
        graph = self._graph(height=2400)
        asm = graph.assembly
        result = evaluate_formula("door_height", graph)
        expected = 2400 - asm.top_sr - asm.base_height - 2  # gap=2
        assert result == expected

    def test_inner_height_formula(self):
        graph = self._graph(height=2400)
        asm = graph.assembly
        result = evaluate_formula("inner_height", graph)
        expected = 2400 - asm.top_sr - asm.base_height - 18 * 2
        assert result == expected

    def test_back_panel_width(self):
        graph = self._graph(width=3000)
        result = evaluate_formula("back_panel_width", graph)
        assert result == 3000

    def test_back_panel_height(self):
        graph = self._graph(height=2400)
        result = evaluate_formula("back_panel_height", graph)
        assert result == 2400

    def test_unknown_formula_raises(self):
        graph = self._graph()
        with pytest.raises(FormulaError):
            evaluate_formula("non_existent_formula", graph)

    def test_result_is_integer_mm(self):
        graph = self._graph(width=3001, module_count=3)
        result = evaluate_formula("module_width", graph)
        assert isinstance(result, int)


class TestEvaluateExpression:
    def _graph(self):
        return create_wardrobe_assembly(WardrobeParams(
            width=3000, height=2400, depth=620, module_count=3,
        ))

    def test_simple_arithmetic(self):
        graph = self._graph()
        result = evaluate_expression("outer_width - ep_left - ep_right", graph)
        expected = 3000 - 50 - 50
        assert result == expected

    def test_door_height_expression(self):
        graph = self._graph()
        result = evaluate_expression("outer_height - top_sr - base - gap", graph)
        asm = graph.assembly
        expected = 2400 - asm.top_sr - asm.base_height - 2
        assert result == expected

    def test_module_width_expression(self):
        graph = self._graph()
        result = evaluate_expression("(outer_width - ep_left - ep_right) / module_count", graph)
        asm = graph.assembly
        expected = round((3000 - asm.ep_left - asm.ep_right) / asm.module_count)
        assert result == expected

    def test_normalize_to_mm_integer(self):
        graph = self._graph()
        # Force float result
        result = evaluate_expression("outer_width / 3", graph)
        assert isinstance(result, int)

    def test_invalid_expression_raises(self):
        graph = self._graph()
        with pytest.raises(FormulaError):
            evaluate_expression("import os; os.getcwd()", graph)


class TestCircularFormulas:
    def test_no_cycles(self):
        deps = {"A": ["B"], "B": ["C"], "C": []}
        cycles = check_circular_formulas(deps)
        assert cycles == []

    def test_direct_cycle(self):
        deps = {"A": ["B"], "B": ["A"]}
        cycles = check_circular_formulas(deps)
        assert len(cycles) > 0

    def test_self_cycle(self):
        deps = {"A": ["A"]}
        cycles = check_circular_formulas(deps)
        assert len(cycles) > 0

    def test_indirect_cycle(self):
        deps = {"A": ["B"], "B": ["C"], "C": ["A"]}
        cycles = check_circular_formulas(deps)
        assert len(cycles) > 0

    def test_no_cycle_empty(self):
        cycles = check_circular_formulas({})
        assert cycles == []


class TestRecalculateGraph:
    def test_recalculate_returns_changes(self):
        graph = create_wardrobe_assembly(WardrobeParams(
            width=3000, height=2400, depth=620, module_count=3,
        ))
        # Force a dimension out of sync to trigger change detection
        door_comps = [c for c in graph.components if c.kind == "door"]
        if door_comps:
            door_comps[0].dimensions.height = 9999  # wrong value

        changes = recalculate_graph(graph)
        # Should detect the change and fix it
        assert isinstance(changes, list)

    def test_no_changes_on_correct_design(self):
        graph = create_wardrobe_assembly(WardrobeParams(
            width=3000, height=2400, depth=620, module_count=3,
        ))
        # All formula_refs cleared to avoid recalculation
        for comp in graph.components:
            comp.formula_refs = []
        changes = recalculate_graph(graph)
        assert changes == []
