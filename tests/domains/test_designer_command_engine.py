"""DK-B7 Command Engine tests."""

from __future__ import annotations

import pytest

from foms.services.designer.assembly_factories import WardrobeParams, create_wardrobe_assembly
from foms.services.designer.command_engine import (
    preview_command,
    apply_command,
    CommandError,
)
from foms.services.designer.ontology_types import DesignCommand


def _make_graph(**kwargs):
    return create_wardrobe_assembly(WardrobeParams(**kwargs))


def _cmd(intent: str, component_id: str, operation: dict, preview_only: bool = True) -> DesignCommand:
    return DesignCommand(
        command_id="test-cmd",
        source="manual_json",
        intent=intent,
        target_component_id=component_id,
        operation=operation,
        preview_only=preview_only,
    )


class TestPreviewCommand:
    def _graph(self):
        return _make_graph(width=2400, height=2200, depth=600, module_count=2)

    def test_preview_move_component_y(self):
        graph = self._graph()
        shelf = next(c for c in graph.components if c.kind == "shelf")
        cmd = _cmd("move_component", shelf.id, {"axis": "y", "delta_mm": 50})
        result = preview_command(cmd, graph)
        assert result["success"] is True
        assert len(result["patches"]) == 1
        assert result["patches"][0]["prop_path"] == "position.y"
        assert result["patches"][0]["after"] == result["patches"][0]["before"] + 50

    def test_preview_resize_component(self):
        graph = self._graph()
        shelf = next(c for c in graph.components if c.kind == "shelf")
        old_h = shelf.dimensions.height
        cmd = _cmd("resize_component", shelf.id, {"dimension": "height", "value_mm": old_h + 10})
        result = preview_command(cmd, graph)
        assert result["success"] is True
        assert result["patches"][0]["prop_path"] == "dimensions.height"

    def test_preview_does_not_modify_graph(self):
        graph = self._graph()
        shelf = next(c for c in graph.components if c.kind == "shelf")
        old_y = shelf.position.y
        cmd = _cmd("move_component", shelf.id, {"axis": "y", "delta_mm": 100})
        preview_command(cmd, graph)
        # Graph must NOT be modified
        shelf_after = graph.get_component(shelf.id)
        assert shelf_after.position.y == old_y

    def test_preview_invalid_component_returns_error(self):
        graph = self._graph()
        cmd = _cmd("move_component", "non-existent-uuid", {"axis": "y", "delta_mm": 50})
        result = preview_command(cmd, graph)
        assert result["success"] is False
        assert "찾을 수 없습니다" in result["error"]

    def test_preview_invalid_intent_returns_error(self):
        graph = self._graph()
        shelf = next(c for c in graph.components if c.kind == "shelf")
        cmd = _cmd("destroy_everything", shelf.id, {})
        result = preview_command(cmd, graph)
        assert result["success"] is False

    def test_preview_set_property(self):
        graph = self._graph()
        shelf = next(c for c in graph.components if c.kind == "shelf")
        cmd = _cmd("set_property", shelf.id, {"property": "material_id", "value": "MDF_18T"})
        result = preview_command(cmd, graph)
        assert result["success"] is True
        assert result["patches"][0]["after"] == "MDF_18T"

    def test_preview_includes_constraint_result(self):
        graph = self._graph()
        shelf = next(c for c in graph.components if c.kind == "shelf")
        cmd = _cmd("move_component", shelf.id, {"axis": "y", "delta_mm": 10})
        result = preview_command(cmd, graph)
        assert "constraint_result" in result
        assert "valid" in result["constraint_result"]


class TestApplyCommand:
    def _graph(self):
        return _make_graph(width=2400, height=2200, depth=600, module_count=2)

    def test_apply_move_modifies_graph(self):
        graph = self._graph()
        shelf = next(c for c in graph.components if c.kind == "shelf")
        old_y = shelf.position.y
        cmd = _cmd("move_component", shelf.id, {"axis": "y", "delta_mm": 30}, preview_only=False)
        result = apply_command(cmd, graph)
        assert result["success"] is True
        shelf_after = graph.get_component(shelf.id)
        assert shelf_after.position.y == old_y + 30

    def test_apply_resize_modifies_graph(self):
        graph = self._graph()
        shelf = next(c for c in graph.components if c.kind == "shelf")
        old_h = shelf.dimensions.height
        new_h = old_h + 5
        cmd = _cmd("resize_component", shelf.id, {"dimension": "height", "value_mm": new_h}, preview_only=False)
        result = apply_command(cmd, graph)
        assert result["success"] is True
        shelf_after = graph.get_component(shelf.id)
        assert shelf_after.dimensions.height == new_h

    def test_apply_returns_correction_delta(self):
        graph = self._graph()
        shelf = next(c for c in graph.components if c.kind == "shelf")
        cmd = _cmd("move_component", shelf.id, {"axis": "y", "delta_mm": 20}, preview_only=False)
        result = apply_command(cmd, graph)
        assert result["success"] is True
        assert "correction_delta" in result
        delta = result["correction_delta"]
        assert delta["source"] == "command_apply"
        assert delta["validated"] is True

    def test_apply_invalid_command_rejected(self):
        graph = self._graph()
        shelf = next(c for c in graph.components if c.kind == "shelf")
        # Make a zero-dimension resize (invalid)
        cmd = _cmd("resize_component", shelf.id, {"dimension": "width", "value_mm": 0}, preview_only=False)
        result = apply_command(cmd, graph)
        assert result["success"] is False

    def test_apply_no_component_id_rejected(self):
        graph = self._graph()
        cmd = DesignCommand(
            command_id="test",
            source="manual_json",
            intent="move_component",
            target_component_id="",  # empty
            operation={"axis": "y", "delta_mm": 10},
        )
        result = apply_command(cmd, graph)
        assert result["success"] is False


class TestMoveComponentIntents:
    def _graph(self):
        return _make_graph(width=2400, height=2200, depth=600, module_count=2)

    def test_move_by_delta(self):
        graph = self._graph()
        shelf = next(c for c in graph.components if c.kind == "shelf")
        old_y = shelf.position.y
        cmd = _cmd("move_component", shelf.id, {"axis": "y", "delta_mm": 100}, preview_only=False)
        result = apply_command(cmd, graph)
        assert result["success"] is True
        assert graph.get_component(shelf.id).position.y == old_y + 100

    def test_move_absolute(self):
        graph = self._graph()
        shelf = next(c for c in graph.components if c.kind == "shelf")
        # Keep same x (to stay within parent), only change y slightly
        orig_x = shelf.position.x
        orig_y = shelf.position.y
        new_y = orig_y + 10  # small valid shift
        cmd = _cmd("move_component", shelf.id, {"x": orig_x, "y": new_y, "z": 0}, preview_only=False)
        result = apply_command(cmd, graph)
        assert result["success"] is True
        c = graph.get_component(shelf.id)
        assert c.position.x == orig_x
        assert c.position.y == new_y


class TestGenerateLayout:
    def _graph(self):
        return _make_graph(width=2400, height=2200, depth=600, module_count=2)

    def test_generate_layout_preview(self):
        graph = self._graph()
        shelf = next(c for c in graph.components if c.kind == "shelf")
        cmd = _cmd("generate_layout", shelf.id, {"module_count": 3, "door_type": "open"})
        result = preview_command(cmd, graph)
        # generate_layout modifies assembly-level props
        assert result["success"] is True


class TestCorrectionsFromCommand:
    def _graph(self):
        return _make_graph(width=3000, height=2400, depth=620, module_count=3)

    def test_apply_correction_delta_has_target_id(self):
        graph = self._graph()
        shelf = next(c for c in graph.components if c.kind == "shelf")
        cmd = _cmd("move_component", shelf.id, {"axis": "y", "delta_mm": 50}, preview_only=False)
        result = apply_command(cmd, graph)
        assert result["success"] is True
        delta = result["correction_delta"]
        assert delta["target_id"] == shelf.id

    def test_apply_correction_delta_has_before_after(self):
        graph = self._graph()
        shelf = next(c for c in graph.components if c.kind == "shelf")
        old_y = shelf.position.y
        cmd = _cmd("move_component", shelf.id, {"axis": "y", "delta_mm": 50}, preview_only=False)
        result = apply_command(cmd, graph)
        delta = result["correction_delta"]
        assert "position.y" in delta["before"]
        assert "position.y" in delta["after"]
        assert delta["before"]["position.y"] == old_y
        assert delta["after"]["position.y"] == old_y + 50
