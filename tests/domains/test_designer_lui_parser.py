"""PV2-B1 LUI Parser tests — golden command set 50개.

Acceptance criteria:
- exact intent match >= 90% (45/50)
- wrong-apply = 0 (all ambiguous commands return ClarificationNeeded)
- ambiguous-to-clarification = 100%
- parser NEVER modifies design_context
"""

from __future__ import annotations

import copy
import pytest

from foms.services.designer.lui_parser import (
    parse_lui,
    ParsedCommand,
    ClarificationNeeded,
)

# ──────────────────────────────────────────────────────────
# Design context fixture (schema v2)
# ──────────────────────────────────────────────────────────

def _ctx(extra_components: list | None = None) -> dict:
    """Default context with multiple components per kind → ambiguous without selection."""
    base = {
        "schema_version": 2,
        "assembly": {"id": "asm-001", "module_count": 2, "door_type": "sliding"},
        "components": [
            {"id": "shelf-001", "kind": "shelf", "role": "shelf", "name": "선반-1-1"},
            {"id": "shelf-002", "kind": "shelf", "role": "shelf", "name": "선반-1-2"},
            {"id": "door-001", "kind": "door", "role": "door", "name": "도어-1"},
            {"id": "door-002", "kind": "door", "role": "door", "name": "도어-2"},
            {"id": "sr-001", "kind": "sr", "role": "top_sr", "name": "상부 SR"},
            {"id": "ep-001", "kind": "ep", "role": "left_ep", "name": "좌측 EP"},
            # Two panels so "측판" is ambiguous without selection
            {"id": "panel-001", "kind": "panel", "role": "left_side", "name": "측판L-1"},
            {"id": "panel-002", "kind": "panel", "role": "right_side", "name": "측판R-1"},
        ],
    }
    if extra_components:
        base["components"].extend(extra_components)
    return base


def _selected(ctx: dict, comp_id: str) -> str:
    return comp_id


# ──────────────────────────────────────────────────────────
# Golden Command Set 50개
# ──────────────────────────────────────────────────────────
# Format: (input_text, expected_intent, should_resolve, description)
# should_resolve=False → ClarificationNeeded expected

GOLDEN_COMMANDS: list[tuple[str, str, bool, str]] = [
    # ── Simple move/resize (20개) ──────────────────────────
    ("선반 50mm 위로", "move_component", True, "shelf up 50"),
    ("선반 100mm 아래로", "move_component", True, "shelf down 100"),
    ("선반 y +30", "move_component", True, "shelf y+30"),
    ("선반 y -20", "move_component", True, "shelf y-20"),
    ("선반 x +10", "move_component", True, "shelf x+10"),
    ("측판 50mm 왼쪽으로", "move_component", True, "panel left 50"),
    ("도어 z -10", "move_component", True, "door z-10"),
    ("선반 높이 300으로", "resize_component", True, "shelf height 300"),
    ("선반 높이 400", "resize_component", True, "shelf height 400"),
    ("선반 폭 500", "resize_component", True, "shelf width 500"),
    ("선반 깊이 580", "resize_component", True, "shelf depth 580"),
    ("상부 SR 30mm로", "resize_component", True, "SR to 30"),
    ("sr 높이 50으로", "resize_component", True, "sr height 50"),
    ("도어 높이 2000으로", "resize_component", True, "door height 2000"),
    ("ep 폭 50으로", "resize_component", True, "ep width 50"),
    ("측판 높이 2100", "resize_component", True, "panel height 2100"),
    ("도어 폭 550", "resize_component", True, "door width 550"),
    ("선반 깊이 500으로", "resize_component", True, "shelf depth 500"),
    ("ep 높이 2200", "resize_component", True, "ep height 2200"),
    ("선반 30mm 위로", "move_component", True, "shelf up 30"),

    # ── Layout / factory params (10개) ───────────────────
    ("3통 균등 배치", "generate_layout", True, "3 module layout"),
    ("2통 여닫이", "generate_layout", True, "2 module swing"),
    ("4통 슬라이딩", "generate_layout", True, "4 module sliding"),
    ("5통 배치", "generate_layout", True, "5 module"),
    ("통 수를 3으로", "generate_layout", True, "set module count 3"),
    ("모듈 2개로", "generate_layout", True, "2 modules"),
    ("도어를 슬라이딩으로", "generate_layout", True, "set sliding door"),
    ("도어를 여닫이로", "generate_layout", True, "set swing door"),
    ("도어를 오픈으로", "generate_layout", True, "set open door"),
    ("문을 슬라이딩으로 변경", "generate_layout", True, "change to sliding"),

    # ── Ambiguous / needs clarification (10개) ──────────
    # Multiple shelves → clarification (no selected_id)
    ("선반 50mm 위로", "clarification", False, "ambiguous: 2 shelves no selection"),
    ("도어 높이 2000으로", "clarification", False, "ambiguous: door no selection"),
    # empty input
    ("", "clarification", False, "empty input"),
    # unknown target
    ("xyz 50mm 위로", "clarification", False, "unknown target xyz"),
    # invalid value
    ("선반 높이 0으로", "clarification", False, "zero dimension"),
    # no match
    ("커피 주문해줘", "clarification", False, "unrelated input"),
    # ambiguous without context
    ("측판 50mm 위로", "clarification", False, "ambiguous panel"),
    # unknown property
    ("선반 색상을 파란색으로", "clarification", False, "unsupported property"),
    # out of range module count
    ("9통 배치", "clarification", False, "9 modules out of range"),
    ("0통 배치", "clarification", False, "0 modules out of range"),

    # ── Invalid / unsafe (10개) — must be clarification ─
    ("선반 높이 -100으로", "clarification", False, "negative resize"),
    ("도어 높이 -1", "clarification", False, "negative height"),
    ("통 수를 0으로", "clarification", False, "zero modules"),
    ("10통 배치", "clarification", False, "too many modules"),
    ("DROP TABLE; 선반 위로", "clarification", False, "sql injection attempt"),
    ("python os.system 실행", "clarification", False, "command injection"),
    ("import sys; sys", "clarification", False, "import injection"),
    ("선반 높이 99999으로", "resize_component", True, "very large value (valid — validator will catch)"),
    ("ep 폭 0으로", "clarification", False, "zero ep width"),
    ("선반 깊이 0", "clarification", False, "zero shelf depth"),
]


# ──────────────────────────────────────────────────────────
# Scoring helpers
# ──────────────────────────────────────────────────────────

def _run_case(text: str, expected_intent: str, should_resolve: bool) -> tuple[bool, str]:
    """Returns (passed, detail_msg)."""
    ctx = _ctx()

    # For ambiguous cases (index >= 30 and < 40): no selected_id, 2 shelves
    selected = None
    if should_resolve and expected_intent != "clarification":
        # Pick a specific selection based on target hint
        for comp in ctx["components"]:
            name_lower = comp["name"].lower()
            kind = comp["kind"]
            text_lower = text.lower()
            if ("선반" in text_lower and kind == "shelf") or \
               ("도어" in text_lower and kind == "door") or \
               ("sr" in text_lower and kind == "sr") or \
               ("상부 sr" in text_lower and kind == "sr") or \
               ("측판" in text_lower and kind == "panel") or \
               ("ep" in text_lower and kind == "ep"):
                selected = comp["id"]
                break

    result = parse_lui(text, selected_component_id=selected, design_context=ctx)

    if should_resolve:
        if isinstance(result, ClarificationNeeded):
            return False, f"Expected resolved, got clarification: {result.reason}"
        if isinstance(result, ParsedCommand):
            actual_intent = result.command.get("intent", "")
            if actual_intent != expected_intent:
                return False, f"Intent mismatch: expected={expected_intent}, got={actual_intent}"
            return True, "ok"
    else:
        if isinstance(result, ParsedCommand):
            return False, f"Expected clarification but got resolved command: {result.command}"
        return True, "ok"

    return False, "unexpected state"


# ──────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────

class TestGoldenCommandSet:
    """Golden set 50개 — accuracy and safety checks."""

    def test_golden_set_accuracy(self):
        """exact intent match >= 90% (45/50), wrong-apply = 0."""
        passed = 0
        failed_items = []
        wrong_applies = 0

        for i, (text, expected_intent, should_resolve, desc) in enumerate(GOLDEN_COMMANDS):
            ok, detail = _run_case(text, expected_intent, should_resolve)
            if ok:
                passed += 1
            else:
                failed_items.append(f"[{i}] {desc!r}: {detail}")
                # wrong-apply check: ambiguous cases must NEVER return ParsedCommand
                if not should_resolve:
                    ctx = _ctx()
                    result = parse_lui(text, selected_component_id=None, design_context=ctx)
                    if isinstance(result, ParsedCommand):
                        wrong_applies += 1

        total = len(GOLDEN_COMMANDS)
        rate = passed / total
        print(f"\nAccuracy: {passed}/{total} = {rate:.1%}")
        if failed_items:
            print("Failed:\n" + "\n".join(failed_items[:10]))

        assert wrong_applies == 0, f"wrong-apply = {wrong_applies}: ambiguous commands must never resolve"
        assert rate >= 0.90, f"Accuracy {rate:.1%} < 90%: {failed_items}"

    def test_wrong_apply_zero(self):
        """All ambiguous/invalid inputs must return ClarificationNeeded."""
        ambiguous_cases = [(t, d) for t, intent, resolve, d in GOLDEN_COMMANDS if not resolve]
        ctx = _ctx()
        for text, desc in ambiguous_cases:
            result = parse_lui(text, selected_component_id=None, design_context=ctx)
            assert isinstance(result, ClarificationNeeded), (
                f"wrong-apply for '{desc}': got ParsedCommand instead of ClarificationNeeded"
            )

    def test_ambiguous_to_clarification_100pct(self):
        """Ambiguous cases always return ClarificationNeeded."""
        ambiguous_cases = [t for t, _, resolve, _ in GOLDEN_COMMANDS if not resolve]
        ctx = _ctx()
        for text in ambiguous_cases:
            result = parse_lui(text, selected_component_id=None, design_context=ctx)
            assert isinstance(result, ClarificationNeeded), f"Expected clarification for: {text!r}"


class TestParserContract:
    """Parser never modifies design_context."""

    def test_parser_does_not_mutate_context(self):
        ctx = _ctx()
        original = copy.deepcopy(ctx)
        parse_lui("선반 50mm 위로", selected_component_id="shelf-001", design_context=ctx)
        assert ctx == original, "Parser must not mutate design_context"

    def test_output_is_design_command_not_mutation(self):
        ctx = _ctx()
        result = parse_lui("선반 50mm 위로", selected_component_id="shelf-001", design_context=ctx)
        assert isinstance(result, ParsedCommand)
        cmd = result.command
        assert "intent" in cmd
        assert "target" in cmd
        assert "operation" in cmd
        assert cmd.get("preview_only") is True, "Parser must produce preview_only=True commands"
        assert "cabinet" not in str(cmd), "Parser must not reference v1 cabinet schema"

    def test_output_has_required_fields(self):
        ctx = _ctx()
        result = parse_lui("3통 균등 배치", selected_component_id=None, design_context=ctx)
        assert isinstance(result, ParsedCommand)
        cmd = result.command
        assert "command_id" in cmd
        assert cmd["source"] == "lui"
        assert cmd["intent"] in ("move_component", "resize_component", "set_property", "generate_layout")


class TestMoveCommands:
    def test_shelf_up(self):
        ctx = _ctx()
        result = parse_lui("선반 50mm 위로", "shelf-001", ctx)
        assert isinstance(result, ParsedCommand)
        assert result.command["intent"] == "move_component"
        assert result.command["operation"]["axis"] == "y"
        assert result.command["operation"]["delta_mm"] == 50

    def test_shelf_down(self):
        ctx = _ctx()
        result = parse_lui("선반 30mm 아래로", "shelf-001", ctx)
        assert isinstance(result, ParsedCommand)
        assert result.command["operation"]["delta_mm"] == -30

    def test_move_axis_notation(self):
        ctx = _ctx()
        result = parse_lui("선반 y +20", "shelf-001", ctx)
        assert isinstance(result, ParsedCommand)
        assert result.command["intent"] == "move_component"

    def test_negative_move(self):
        ctx = _ctx()
        result = parse_lui("선반 y -10", "shelf-001", ctx)
        assert isinstance(result, ParsedCommand)
        assert result.command["operation"]["delta_mm"] == -10


class TestResizeCommands:
    def test_sr_to_mm(self):
        ctx = _ctx()
        result = parse_lui("상부 SR 30mm로", "sr-001", ctx)
        assert isinstance(result, ParsedCommand)
        assert result.command["intent"] == "resize_component"
        assert result.command["operation"]["value_mm"] == 30

    def test_shelf_height(self):
        ctx = _ctx()
        result = parse_lui("선반 높이 300으로", "shelf-001", ctx)
        assert isinstance(result, ParsedCommand)
        assert result.command["operation"]["dimension"] == "height"
        assert result.command["operation"]["value_mm"] == 300

    def test_zero_dimension_clarification(self):
        ctx = _ctx()
        result = parse_lui("선반 높이 0으로", "shelf-001", ctx)
        assert isinstance(result, ClarificationNeeded)

    def test_ep_width(self):
        ctx = _ctx()
        result = parse_lui("ep 폭 50으로", "ep-001", ctx)
        assert isinstance(result, ParsedCommand)
        assert result.command["operation"]["dimension"] == "width"


class TestLayoutCommands:
    def test_3_module_layout(self):
        ctx = _ctx()
        result = parse_lui("3통 균등 배치", None, ctx)
        assert isinstance(result, ParsedCommand)
        assert result.command["intent"] == "generate_layout"
        assert result.command["operation"]["module_count"] == 3

    def test_door_sliding(self):
        ctx = _ctx()
        result = parse_lui("도어를 슬라이딩으로", None, ctx)
        assert isinstance(result, ParsedCommand)
        assert result.command["intent"] == "generate_layout"
        assert result.command["operation"]["door_type"] == "sliding"

    def test_door_swing(self):
        ctx = _ctx()
        result = parse_lui("도어를 여닫이로", None, ctx)
        assert isinstance(result, ParsedCommand)
        assert result.command["operation"]["door_type"] == "swing"

    def test_out_of_range_modules(self):
        ctx = _ctx()
        result = parse_lui("9통 배치", None, ctx)
        assert isinstance(result, ClarificationNeeded)

    def test_zero_modules_clarification(self):
        ctx = _ctx()
        result = parse_lui("0통 배치", None, ctx)
        assert isinstance(result, ClarificationNeeded)


class TestAmbiguousInputs:
    def test_empty_text(self):
        result = parse_lui("", None, None)
        assert isinstance(result, ClarificationNeeded)

    def test_unrelated_text(self):
        result = parse_lui("커피 주문해줘", None, _ctx())
        assert isinstance(result, ClarificationNeeded)

    def test_injection_attempt(self):
        result = parse_lui("DROP TABLE users; 선반 위로", None, _ctx())
        assert isinstance(result, ClarificationNeeded)

    def test_no_design_context_no_selection(self):
        """Without context and selection, target cannot be resolved."""
        result = parse_lui("선반 50mm 위로", None, None)
        # Either clarification (can't resolve target) or uses hint
        # Target resolution without context and selection is ambiguous
        assert isinstance(result, ClarificationNeeded)
