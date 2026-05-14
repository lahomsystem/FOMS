"""FOMS Brain Design Kernel Post-V1 — LUI (Language-UI) Parser.

PV2-B1: Korean natural language → deterministic DesignCommand.

Design contract:
- Parser NEVER modifies design_json directly.
- Output is always DesignCommand dict (or ClarificationNeeded).
- ambiguous / multi-target → ClarificationNeeded (apply forbidden).
- wrong-apply = 0: only fully-resolved commands reach apply.

Supported intents (V1):
  move_component       : "왼쪽 선반 50mm 위로" / "선반 y +50"
  resize_component     : "상부 SR 30mm로" / "선반 높이 300"
  set_property         : "도어를 슬라이딩으로" / "자재를 MDF로"
  generate_layout      : "3통 균등 배치" / "2통 여닫이"
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional


# ──────────────────────────────────────────────────────────
# Result types
# ──────────────────────────────────────────────────────────

@dataclass
class ParsedCommand:
    """Successfully parsed, fully-resolved command."""
    command: dict[str, Any]
    confidence: float          # 0.0–1.0
    matched_rule: str          # which grammar rule matched


@dataclass
class ClarificationNeeded:
    """Ambiguous or unresolvable input — apply is forbidden."""
    reason: str
    candidates: list[str] = field(default_factory=list)
    original_text: str = ""


ParseResult = ParsedCommand | ClarificationNeeded


# ──────────────────────────────────────────────────────────
# Grammar rules
# ──────────────────────────────────────────────────────────

# Each rule: (regex, handler_name, intent)
# Patterns capture named groups used by handlers.

_MOVE_PATTERNS = [
    # "선반 50mm 위로" / "선반을 50 위로" / "선반 y +50"
    (r"(?P<target_hint>[가-힣a-zA-Z0-9_\-]+)\s*(?:을|를)?\s*(?P<delta>\d+)\s*(?:mm)?\s*(?P<dir>위로|아래로|왼쪽으로|오른쪽으로|앞으로|뒤로)", "move_direction"),
    (r"(?P<target_hint>[가-힣a-zA-Z0-9_\-]+)\s*(?P<axis>[xyz])\s*(?P<sign>[+\-])?\s*(?P<delta>\d+)", "move_axis"),
    (r"(?P<target_hint>[가-힣a-zA-Z0-9_\-]+)\s*(?:을|를)?\s*(?P<axis>y|x|z)\s*축?\s*(?P<delta>\d+)\s*(?:mm)?", "move_axis"),
]

_RESIZE_PATTERNS = [
    # "상부 SR 30mm로" / "선반 높이 300으로" / "선반 폭 500"
    (r"(?P<target_hint>[가-힣a-zA-Z0-9_\-]+)\s*(?:의|을|를)?\s*(?P<dim>높이|폭|깊이|width|height|depth)\s*(?:을|를)?\s*(?P<value>\d+)\s*(?:mm)?(?:로|으로)?", "resize_dim"),
    (r"(?P<target_hint>[가-힣a-zA-Z0-9_\-]+)\s*(?:을|를)?\s*(?P<value>\d+)\s*(?:mm)?(?:로|으로)\s*(?:변경|수정|설정)?", "resize_bare"),
]

_PROPERTY_PATTERNS = [
    # "도어를 슬라이딩으로" / "자재를 MDF로"
    (r"(?:도어|문)\s*(?:를|을)?\s*(?P<door_type>슬라이딩|여닫이|오픈|sliding|swing|open)(?:으로|로)?", "set_door_type"),
    (r"(?P<target_hint>[가-힣a-zA-Z0-9_\-]+)\s*(?:의|을|를)?\s*(?:자재|material)\s*(?:를|을)?\s*(?P<material>[A-Za-z0-9_]+)(?:으로|로)?", "set_material"),
]

_LAYOUT_PATTERNS = [
    # "3통 균등 배치" / "2통 여닫이" / "4통 슬라이딩"
    (r"(?P<count>\d+)\s*통\s*(?P<door_type>균등|슬라이딩|여닫이|오픈|sliding|swing|open)?\s*(?:배치|구성|분할)?", "generate_layout_count"),
    # "통 수를 3으로" / "모듈 3개"
    (r"(?:통\s*수|모듈)\s*(?:를|을)?\s*(?P<count>\d+)(?:개|통)?(?:로|으로)?", "generate_layout_count"),
]


# ──────────────────────────────────────────────────────────
# Direction / dimension mapping
# ──────────────────────────────────────────────────────────

_DIR_TO_AXIS: dict[str, tuple[str, int]] = {
    "위로": ("y", 1),
    "아래로": ("y", -1),
    "왼쪽으로": ("x", -1),
    "오른쪽으로": ("x", 1),
    "앞으로": ("z", -1),
    "뒤로": ("z", 1),
}

_DIM_KO: dict[str, str] = {
    "높이": "height",
    "폭": "width",
    "깊이": "depth",
    "width": "width",
    "height": "height",
    "depth": "depth",
}

_DOOR_TYPE_KO: dict[str, str] = {
    "슬라이딩": "sliding",
    "여닫이": "swing",
    "오픈": "open",
    "sliding": "sliding",
    "swing": "swing",
    "open": "open",
    "균등": "open",  # "균등 배치" defaults to open in this context
}

# Component kind / role hint → role/kind search term
_TARGET_HINT_MAP: dict[str, dict] = {
    "선반": {"kind": "shelf"},
    "도어": {"kind": "door"},
    "문": {"kind": "door"},
    "서랍": {"kind": "drawer"},
    "ep": {"kind": "ep"},
    "엔드패널": {"kind": "ep"},
    "sr": {"kind": "sr"},
    "스카이레일": {"kind": "sr"},
    "상부sr": {"role": "top_sr"},
    "상부 sr": {"role": "top_sr"},
    "받침대": {"kind": "base"},
    "후판": {"role": "back_panel"},
    "측판": {"role": "left_side"},
    "좌측판": {"role": "left_side"},
    "우측판": {"role": "right_side"},
}


# ──────────────────────────────────────────────────────────
# Component resolver
# ──────────────────────────────────────────────────────────

def _resolve_component(
    hint: str,
    selected_id: Optional[str],
    design_context: Optional[dict],
) -> tuple[Optional[str], bool]:
    """Resolve component UUID from hint + selection context.

    Returns (uuid_or_none, is_ambiguous).
    - If selected_id is set and hint matches it → use selected_id.
    - If unique match found in design_context → return uuid.
    - If multiple matches → ambiguous.
    """
    hint_lower = hint.lower().strip()

    if not design_context or "components" not in design_context:
        # No context: must rely on selected_id
        if selected_id:
            return selected_id, False
        return None, True

    components: list[dict] = design_context.get("components", [])
    hint_meta = _TARGET_HINT_MAP.get(hint_lower, {})

    # Score components
    matches: list[str] = []
    for comp in components:
        comp_id = comp.get("id", "")
        if selected_id and comp_id == selected_id:
            return selected_id, False
        # kind match
        if hint_meta.get("kind") and comp.get("kind") == hint_meta["kind"]:
            matches.append(comp_id)
        elif hint_meta.get("role") and comp.get("role") == hint_meta["role"]:
            matches.append(comp_id)
        elif hint_lower in comp.get("name", "").lower():
            matches.append(comp_id)

    if len(matches) == 1:
        return matches[0], False
    if len(matches) > 1:
        return None, True  # ambiguous
    # No match
    if selected_id:
        return selected_id, False
    return None, True


# ──────────────────────────────────────────────────────────
# Handler implementations
# ──────────────────────────────────────────────────────────

def _handle_move_direction(m: re.Match, selected_id: Optional[str], design_context: Optional[dict]) -> ParseResult:
    hint = m.group("target_hint")
    delta = int(m.group("delta"))
    direction = m.group("dir")
    axis, sign = _DIR_TO_AXIS.get(direction, ("y", 1))
    comp_id, ambiguous = _resolve_component(hint, selected_id, design_context)
    if ambiguous or not comp_id:
        return ClarificationNeeded(
            reason=f"'{hint}'에 해당하는 부재가 여러 개이거나 선택되지 않았습니다.",
            candidates=[hint],
            original_text=m.group(0),
        )
    return ParsedCommand(
        command=_make_cmd("move_component", comp_id, {"axis": axis, "delta_mm": sign * delta}),
        confidence=0.9,
        matched_rule="move_direction",
    )


def _handle_move_axis(m: re.Match, selected_id: Optional[str], design_context: Optional[dict]) -> ParseResult:
    hint = m.group("target_hint")
    axis = m.group("axis")
    delta = int(m.group("delta"))
    sign_str = m.groupdict().get("sign") or "+"
    sign = -1 if sign_str == "-" else 1
    comp_id, ambiguous = _resolve_component(hint, selected_id, design_context)
    if ambiguous or not comp_id:
        return ClarificationNeeded(
            reason=f"'{hint}'에 해당하는 부재가 특정되지 않습니다.",
            candidates=[hint],
            original_text=m.group(0),
        )
    return ParsedCommand(
        command=_make_cmd("move_component", comp_id, {"axis": axis, "delta_mm": sign * delta}),
        confidence=0.9,
        matched_rule="move_axis",
    )


def _handle_resize_dim(m: re.Match, selected_id: Optional[str], design_context: Optional[dict]) -> ParseResult:
    hint = m.group("target_hint")
    dim_ko = m.group("dim")
    dim = _DIM_KO.get(dim_ko, "height")
    value = int(m.group("value"))
    if value <= 0:
        return ClarificationNeeded(reason="치수는 0보다 커야 합니다.", original_text=m.group(0))
    comp_id, ambiguous = _resolve_component(hint, selected_id, design_context)
    if ambiguous or not comp_id:
        return ClarificationNeeded(
            reason=f"'{hint}'에 해당하는 부재가 특정되지 않습니다.",
            candidates=[hint],
            original_text=m.group(0),
        )
    return ParsedCommand(
        command=_make_cmd("resize_component", comp_id, {"dimension": dim, "value_mm": value}),
        confidence=0.85,
        matched_rule="resize_dim",
    )


def _handle_resize_bare(m: re.Match, selected_id: Optional[str], design_context: Optional[dict]) -> ParseResult:
    hint = m.group("target_hint")
    value = int(m.group("value"))
    if value <= 0:
        return ClarificationNeeded(reason="치수는 0보다 커야 합니다.", original_text=m.group(0))
    comp_id, ambiguous = _resolve_component(hint, selected_id, design_context)
    if ambiguous or not comp_id:
        return ClarificationNeeded(
            reason=f"'{hint}'의 대상 부재가 특정되지 않습니다. 부재를 먼저 선택하세요.",
            candidates=[hint],
            original_text=m.group(0),
        )
    # bare resize: treat as height (most common semantic)
    return ParsedCommand(
        command=_make_cmd("resize_component", comp_id, {"dimension": "height", "value_mm": value}),
        confidence=0.65,
        matched_rule="resize_bare",
    )


def _handle_set_door_type(m: re.Match, selected_id: Optional[str], design_context: Optional[dict]) -> ParseResult:
    door_type_ko = m.group("door_type")
    door_type = _DOOR_TYPE_KO.get(door_type_ko, door_type_ko)
    # generate_layout with door_type
    asm_id = _get_assembly_id(design_context)
    return ParsedCommand(
        command=_make_cmd("generate_layout", asm_id or "", {"door_type": door_type}),
        confidence=0.95,
        matched_rule="set_door_type",
    )


def _handle_set_material(m: re.Match, selected_id: Optional[str], design_context: Optional[dict]) -> ParseResult:
    hint = m.group("target_hint")
    material = m.group("material").upper()
    comp_id, ambiguous = _resolve_component(hint, selected_id, design_context)
    if ambiguous or not comp_id:
        return ClarificationNeeded(
            reason=f"'{hint}'에 해당하는 부재가 특정되지 않습니다.",
            candidates=[hint],
            original_text=m.group(0),
        )
    return ParsedCommand(
        command=_make_cmd("set_property", comp_id, {"property": "material_id", "value": material}),
        confidence=0.85,
        matched_rule="set_material",
    )


def _handle_generate_layout_count(m: re.Match, selected_id: Optional[str], design_context: Optional[dict]) -> ParseResult:
    count = int(m.group("count"))
    if count < 1 or count > 8:
        return ClarificationNeeded(
            reason=f"모듈 수는 1~8 사이여야 합니다 (입력값: {count}).",
            original_text=m.group(0),
        )
    door_type_ko = (m.groupdict().get("door_type") or "").strip()
    door_type = _DOOR_TYPE_KO.get(door_type_ko) if door_type_ko and door_type_ko != "균등" else None
    asm_id = _get_assembly_id(design_context)
    op: dict[str, Any] = {"module_count": count}
    if door_type:
        op["door_type"] = door_type
    return ParsedCommand(
        command=_make_cmd("generate_layout", asm_id or "", op),
        confidence=0.95,
        matched_rule="generate_layout_count",
    )


# ──────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────

def _make_cmd(intent: str, component_id: str, operation: dict[str, Any]) -> dict[str, Any]:
    return {
        "command_id": str(uuid.uuid4()),
        "source": "lui",
        "intent": intent,
        "target": {"component_id": component_id},
        "operation": operation,
        "preview_only": True,
    }


def _get_assembly_id(design_context: Optional[dict]) -> Optional[str]:
    if design_context:
        asm = design_context.get("assembly", {})
        return asm.get("id")
    return None


# ──────────────────────────────────────────────────────────
# Main parser
# ──────────────────────────────────────────────────────────

_ALL_RULES: list[tuple[str, str, Any]] = (
    [(p, "move_direction", _handle_move_direction) for p, _ in _MOVE_PATTERNS[:1]]
    + [(p, "move_axis", _handle_move_axis) for p, _ in _MOVE_PATTERNS[1:]]
    + [(p, "resize_dim", _handle_resize_dim) for p, _ in _RESIZE_PATTERNS[:1]]
    + [(p, "resize_bare", _handle_resize_bare) for p, _ in _RESIZE_PATTERNS[1:]]
    + [(p, "set_door_type", _handle_set_door_type) for p, _ in _PROPERTY_PATTERNS[:1]]
    + [(p, "set_material", _handle_set_material) for p, _ in _PROPERTY_PATTERNS[1:]]
    + [(p, "generate_layout_count", _handle_generate_layout_count) for p, _ in _LAYOUT_PATTERNS]
)


def parse_lui(
    text: str,
    selected_component_id: Optional[str] = None,
    design_context: Optional[dict] = None,
) -> ParseResult:
    """Parse Korean natural language into a deterministic DesignCommand.

    Args:
        text: Korean command string
        selected_component_id: currently selected component UUID (from frontend)
        design_context: full DesignGraph dict for component resolution

    Returns:
        ParsedCommand — fully resolved, ready for preview/apply
        ClarificationNeeded — ambiguous/invalid, apply must be refused

    Contract:
        This function NEVER modifies design_context.
        Output is always a DesignCommand dict (not a direct design mutation).
    """
    if not text or not text.strip():
        return ClarificationNeeded(reason="입력이 비어 있습니다.", original_text=text)

    text_norm = text.strip()

    handler_map = {
        "move_direction": _handle_move_direction,
        "move_axis": _handle_move_axis,
        "resize_dim": _handle_resize_dim,
        "resize_bare": _handle_resize_bare,
        "set_door_type": _handle_set_door_type,
        "set_material": _handle_set_material,
        "generate_layout_count": _handle_generate_layout_count,
    }

    candidates: list[ParsedCommand] = []

    for pattern, rule_name, handler in _ALL_RULES:
        try:
            m = re.search(pattern, text_norm, re.IGNORECASE)
        except re.error:
            continue
        if m:
            fn = handler_map.get(rule_name)
            if fn is None:
                continue
            result = fn(m, selected_component_id, design_context)
            if isinstance(result, ClarificationNeeded):
                return result
            candidates.append(result)

    if not candidates:
        return ClarificationNeeded(
            reason=(
                "명령을 이해할 수 없습니다. "
                "예: '선반 50mm 위로', '상부 SR 30mm로', '3통 균등 배치', '도어를 슬라이딩으로'"
            ),
            original_text=text_norm,
        )

    # Return highest confidence candidate
    candidates.sort(key=lambda c: c.confidence, reverse=True)
    return candidates[0]
