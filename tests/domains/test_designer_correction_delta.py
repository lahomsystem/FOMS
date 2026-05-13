"""DK-B8 Correction Delta tests."""

from __future__ import annotations

import pytest

from foms.services.designer.corrections import build_manual_edit_delta, log_correction_delta
from foms.services.designer.command_engine import apply_command
from foms.services.designer.assembly_factories import WardrobeParams, create_wardrobe_assembly
from foms.services.designer.ontology_types import DesignCommand


def _graph(**kwargs):
    return create_wardrobe_assembly(WardrobeParams(**kwargs))


def _cmd(intent, comp_id, operation) -> DesignCommand:
    return DesignCommand(
        command_id="test",
        source="manual_json",
        intent=intent,
        target_component_id=comp_id,
        operation=operation,
        preview_only=False,
    )


class TestBuildManualEditDelta:
    def test_basic_delta(self):
        delta = build_manual_edit_delta(
            target_id="comp-001",
            before={"height": 300},
            after={"height": 330},
            reason="현장 조정",
        )
        assert delta["correction_id"]
        assert delta["target_id"] == "comp-001"
        assert delta["before"]["height"] == 300
        assert delta["after"]["height"] == 330
        assert delta["source"] == "user_manual_edit"
        assert delta["validated"] is True
        assert delta["reason"] == "현장 조정"

    def test_no_change_sets_validated_false(self):
        delta = build_manual_edit_delta(
            target_id="comp-001",
            before={"height": 300},
            after={"height": 300},  # same
        )
        assert delta["validated"] is False

    def test_candidate_rule_hint(self):
        delta = build_manual_edit_delta(
            target_id="sr-top-001",
            before={"height": 50},
            after={"height": 30},
            reason="상부 여유가 작아 SR 축소",
            candidate_rule_hint="top_sr_prefers_30mm_when_ceiling_gap_under_60mm",
        )
        assert delta["candidate_rule_hint"] == "top_sr_prefers_30mm_when_ceiling_gap_under_60mm"


class TestCommandApplyDelta:
    def _make(self):
        return _graph(width=3000, height=2400, depth=620, module_count=3)

    def test_command_apply_generates_delta(self):
        graph = self._make()
        shelf = next(c for c in graph.components if c.kind == "shelf")
        cmd = _cmd("move_component", shelf.id, {"axis": "y", "delta_mm": 50})
        result = apply_command(cmd, graph)
        assert result["success"] is True
        delta = result["correction_delta"]
        assert delta["source"] == "command_apply"
        assert delta["validated"] is True
        assert delta["correction_id"]

    def test_command_resize_delta_contains_before_after(self):
        graph = self._make()
        shelf = next(c for c in graph.components if c.kind == "shelf")
        old_h = shelf.dimensions.height
        cmd = _cmd("resize_component", shelf.id, {"dimension": "height", "value_mm": old_h + 15})
        result = apply_command(cmd, graph)
        assert result["success"] is True
        delta = result["correction_delta"]
        assert "dimensions.height" in delta["before"]
        assert delta["before"]["dimensions.height"] == old_h
        assert delta["after"]["dimensions.height"] == old_h + 15

    def test_invalid_command_no_delta(self):
        graph = self._make()
        shelf = next(c for c in graph.components if c.kind == "shelf")
        # zero dimension = invalid
        cmd = _cmd("resize_component", shelf.id, {"dimension": "width", "value_mm": 0})
        result = apply_command(cmd, graph)
        assert result["success"] is False
        # No correction delta for invalid commands
        assert "correction_delta" not in result or result.get("correction_delta") is None


class TestCorrectionDeltaContract:
    """Verify CorrectionDelta shape matches Data Contract V1 spec."""

    def test_delta_has_all_required_fields(self):
        delta = build_manual_edit_delta(
            target_id="sr-top-001",
            before={"height": 50},
            after={"height": 30},
            reason="reason text",
        )
        required = {"correction_id", "target_id", "before", "after", "reason", "source", "validated"}
        assert required.issubset(set(delta.keys()))

    def test_delta_source_is_valid(self):
        delta = build_manual_edit_delta(
            target_id="x",
            before={"h": 1},
            after={"h": 2},
        )
        valid_sources = {"user_manual_edit", "command_apply", "ai_suggestion"}
        assert delta["source"] in valid_sources

    def test_command_delta_source_is_command_apply(self):
        graph = _graph(width=2400, height=2200, depth=600, module_count=2)
        shelf = next(c for c in graph.components if c.kind == "shelf")
        cmd = _cmd("move_component", shelf.id, {"axis": "y", "delta_mm": 10})
        result = apply_command(cmd, graph)
        assert result["correction_delta"]["source"] == "command_apply"
