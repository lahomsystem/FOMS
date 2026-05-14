"""FOMS Brain Design Kernel V1 — Command Engine (Python backend).

DK-B7: deterministic DesignCommand executor.

Supported intents:
- move_component
- resize_component
- set_property
- generate_layout

preview/apply separation:
- preview: validate only, return proposed patches without modifying
- apply: validate + apply + return correction delta
"""

from __future__ import annotations

import uuid
from typing import Any

from foms.services.designer.ontology_types import (
    DesignCommand,
    DesignGraph,
    DesignPatch,
    CorrectionDelta,
)
from foms.services.designer.constraint_engine import validate_design_graph


VALID_INTENTS = {"move_component", "resize_component", "set_property", "generate_layout"}


class CommandError(Exception):
    """Raised when a command cannot be executed."""


# ──────────────────────────────────────────────────────────
# Intent executors (return list of patches without side effects)
# ──────────────────────────────────────────────────────────

def _execute_move_component(command: DesignCommand, graph: DesignGraph) -> list[DesignPatch]:
    """move_component: shift component position.

    operation: {axis: "x"|"y"|"z", delta_mm: number}
         OR    {x: number, y: number, z: number}  (absolute)
    """
    comp = graph.get_component(command.target_component_id)
    if not comp:
        raise CommandError(f"부재를 찾을 수 없습니다: {command.target_component_id!r}")

    op = command.operation
    patches: list[DesignPatch] = []

    if "delta_mm" in op:
        axis = str(op.get("axis", "y"))
        delta = int(op["delta_mm"])
        old_val = getattr(comp.position, axis, None)
        if old_val is None:
            raise CommandError(f"유효하지 않은 축: {axis!r}")
        new_val = old_val + delta
        patches.append(DesignPatch(
            target_id=comp.id,
            prop_path=f"position.{axis}",
            before=old_val,
            after=new_val,
        ))
    else:
        for axis in ("x", "y", "z"):
            if axis in op:
                old_val = getattr(comp.position, axis)
                new_val = int(op[axis])
                if old_val != new_val:
                    patches.append(DesignPatch(
                        target_id=comp.id,
                        prop_path=f"position.{axis}",
                        before=old_val,
                        after=new_val,
                    ))

    return patches


def _execute_resize_component(command: DesignCommand, graph: DesignGraph) -> list[DesignPatch]:
    """resize_component: change component dimensions.

    operation: {dimension: "width"|"height"|"depth", value_mm: number}
         OR    {width: number, height: number, depth: number}  (multi-dim)
    """
    comp = graph.get_component(command.target_component_id)
    if not comp:
        raise CommandError(f"부재를 찾을 수 없습니다: {command.target_component_id!r}")

    op = command.operation
    patches: list[DesignPatch] = []

    if "dimension" in op and "value_mm" in op:
        dim = str(op["dimension"])
        new_val = int(op["value_mm"])
        if new_val <= 0:
            raise CommandError(f"치수는 0보다 커야 합니다: {new_val}")
        old_val = getattr(comp.dimensions, dim, None)
        if old_val is None:
            raise CommandError(f"유효하지 않은 치수: {dim!r}")
        if old_val != new_val:
            patches.append(DesignPatch(
                target_id=comp.id,
                prop_path=f"dimensions.{dim}",
                before=old_val,
                after=new_val,
            ))
    else:
        for dim in ("width", "height", "depth"):
            if dim in op:
                new_val = int(op[dim])
                if new_val <= 0:
                    raise CommandError(f"치수는 0보다 커야 합니다: {new_val}")
                old_val = getattr(comp.dimensions, dim)
                if old_val != new_val:
                    patches.append(DesignPatch(
                        target_id=comp.id,
                        prop_path=f"dimensions.{dim}",
                        before=old_val,
                        after=new_val,
                    ))

    return patches


def _execute_set_property(command: DesignCommand, graph: DesignGraph) -> list[DesignPatch]:
    """set_property: set a custom_props value or material_id.

    operation: {property: "material_id"|"name"|..., value: <any>}
    """
    comp = graph.get_component(command.target_component_id)
    if not comp:
        raise CommandError(f"부재를 찾을 수 없습니다: {command.target_component_id!r}")

    op = command.operation
    prop = str(op.get("property", ""))
    value = op.get("value")

    allowed_props = {"material_id", "name", "door_type", "edge_banding"}
    if prop not in allowed_props and not prop.startswith("custom_props."):
        raise CommandError(f"변경 불가 속성: {prop!r}. 허용: {sorted(allowed_props)}")

    if prop == "material_id":
        old_val = comp.material_id
        return [DesignPatch(target_id=comp.id, prop_path="material_id", before=old_val, after=value)]
    if prop == "name":
        old_val = comp.name
        return [DesignPatch(target_id=comp.id, prop_path="name", before=old_val, after=str(value))]

    # custom_props
    key = prop.replace("custom_props.", "")
    old_val = comp.custom_props.get(key)
    return [DesignPatch(target_id=comp.id, prop_path=prop, before=old_val, after=value)]


def _execute_generate_layout(command: DesignCommand, graph: DesignGraph) -> list[DesignPatch]:
    """generate_layout: regenerate assembly via factory registry.

    PV2-B2: Routes through factory_registry.create_assembly when params changed.

    operation: {module_count: int, door_type: str, width: int, ...}
    Returns assembly-level patches for preview. Actual factory call in apply path.
    """
    op = command.operation
    patches: list[DesignPatch] = []
    asm = graph.assembly

    mappings = [
        ("module_count", "assembly.module_count", asm.module_count),
        ("door_type", "assembly.door_type", asm.door_type),
        ("ep_left", "assembly.ep_left", asm.ep_left),
        ("ep_right", "assembly.ep_right", asm.ep_right),
        ("top_sr", "assembly.top_sr", asm.top_sr),
        ("base_height", "assembly.base_height", asm.base_height),
        ("width", "assembly.dimensions.width", asm.dimensions.width),
        ("height", "assembly.dimensions.height", asm.dimensions.height),
        ("depth", "assembly.dimensions.depth", asm.dimensions.depth),
        ("furniture_type", "assembly.type", asm.type),
    ]

    for op_key, prop_path, old_val in mappings:
        if op_key in op:
            new_val = op[op_key]
            if old_val != new_val:
                patches.append(DesignPatch(
                    target_id=asm.id,
                    prop_path=prop_path,
                    before=old_val,
                    after=new_val,
                ))

    return patches


def regenerate_layout_via_registry(
    graph: DesignGraph,
    furniture_type: str | None = None,
    extra_params: dict | None = None,
) -> DesignGraph:
    """Regenerate assembly graph via factory registry.

    PV2-B2: Used by generate_layout apply path.
    furniture_type defaults to graph.assembly.type.
    """
    from foms.services.designer.factory_registry import create_assembly, default_params
    ftype = furniture_type or graph.assembly.type
    asm = graph.assembly
    params = default_params(ftype)
    params.update({
        "width": asm.dimensions.width,
        "height": asm.dimensions.height,
        "depth": asm.dimensions.depth,
        "module_count": asm.module_count,
        "door_type": asm.door_type,
        "ep_left": asm.ep_left,
        "ep_right": asm.ep_right,
        "base_height": asm.base_height,
        "top_sr": asm.top_sr,
    })
    if extra_params:
        params.update(extra_params)
    return create_assembly(ftype, params)


# ──────────────────────────────────────────────────────────
# Apply patches to graph (mutates in-place)
# ──────────────────────────────────────────────────────────

def _apply_patches(patches: list[DesignPatch], graph: DesignGraph) -> None:
    """Apply patches to the graph in-place."""
    for patch in patches:
        comp = graph.get_component(patch.target_id)
        if comp is None:
            # Could be assembly-level patch
            if patch.prop_path.startswith("assembly."):
                attr = patch.prop_path.replace("assembly.", "")
                if hasattr(graph.assembly, attr):
                    setattr(graph.assembly, attr, patch.after)
            continue

        path = patch.prop_path
        if path.startswith("position."):
            axis = path.replace("position.", "")
            if hasattr(comp.position, axis):
                setattr(comp.position, axis, int(patch.after))
        elif path.startswith("dimensions."):
            dim = path.replace("dimensions.", "")
            if hasattr(comp.dimensions, dim):
                setattr(comp.dimensions, dim, int(patch.after))
        elif path == "material_id":
            comp.material_id = patch.after
        elif path == "name":
            comp.name = str(patch.after)
        elif path.startswith("custom_props."):
            key = path.replace("custom_props.", "")
            comp.custom_props[key] = patch.after


# ──────────────────────────────────────────────────────────
# Public API: preview / apply
# ──────────────────────────────────────────────────────────

def preview_command(
    command: DesignCommand,
    graph: DesignGraph,
) -> dict[str, Any]:
    """Preview a command: validate and return proposed patches without applying.

    Returns: {success, patches, constraint_result, error}
    """
    if not command.target_component_id:
        return {"success": False, "patches": [], "error": "target.component_id 가 없습니다."}
    if command.intent not in VALID_INTENTS:
        return {"success": False, "patches": [], "error": f"알 수 없는 intent: {command.intent!r}"}

    try:
        patches = _get_patches(command, graph)
    except CommandError as e:
        return {"success": False, "patches": [], "error": str(e)}

    # Simulate: apply patches to a copy and validate
    import copy
    graph_copy = copy.deepcopy(graph)
    _apply_patches(patches, graph_copy)
    constraint_result = validate_design_graph(graph_copy)

    return {
        "success": True,
        "patches": [p.to_dict() for p in patches],
        "constraint_result": constraint_result.to_dict(),
        "would_be_valid": constraint_result.valid,
        "error": None,
    }


def apply_command(
    command: DesignCommand,
    graph: DesignGraph,
    user_id: int | None = None,
    project_version_id: int | None = None,
) -> dict[str, Any]:
    """Apply a command to the graph and persist correction delta.

    DOES NOT persist the design itself — caller handles that.
    Returns: {success, patches, constraint_result, correction_delta, error}

    If the result would be invalid, the command is rejected (not applied).
    """
    if not command.target_component_id:
        return {"success": False, "patches": [], "error": "target.component_id 가 없습니다."}
    if command.intent not in VALID_INTENTS:
        return {"success": False, "patches": [], "error": f"알 수 없는 intent: {command.intent!r}"}

    try:
        patches = _get_patches(command, graph)
    except CommandError as e:
        return {"success": False, "patches": [], "error": str(e)}

    # Validate BEFORE applying
    import copy
    graph_copy = copy.deepcopy(graph)
    _apply_patches(patches, graph_copy)
    constraint_result = validate_design_graph(graph_copy)

    if not constraint_result.valid:
        return {
            "success": False,
            "patches": [p.to_dict() for p in patches],
            "constraint_result": constraint_result.to_dict(),
            "error": "Command 적용 결과가 유효하지 않습니다. 저장이 거부됩니다.",
        }

    # Apply to original graph
    _apply_patches(patches, graph)

    # Build correction delta
    delta = _build_correction_delta(patches, command)

    return {
        "success": True,
        "patches": [p.to_dict() for p in patches],
        "constraint_result": constraint_result.to_dict(),
        "correction_delta": delta.to_dict(),
        "error": None,
    }


def _get_patches(command: DesignCommand, graph: DesignGraph) -> list[DesignPatch]:
    """Dispatch to the correct intent executor."""
    dispatch = {
        "move_component": _execute_move_component,
        "resize_component": _execute_resize_component,
        "set_property": _execute_set_property,
        "generate_layout": _execute_generate_layout,
    }
    fn = dispatch.get(command.intent)
    if fn is None:
        raise CommandError(f"Intent 미지원: {command.intent!r}")
    return fn(command, graph)


def _build_correction_delta(patches: list[DesignPatch], command: DesignCommand) -> CorrectionDelta:
    """Build a CorrectionDelta from applied patches."""
    before = {p.prop_path: p.before for p in patches}
    after = {p.prop_path: p.after for p in patches}
    target_id = command.target_component_id or (patches[0].target_id if patches else "unknown")
    return CorrectionDelta(
        correction_id=str(uuid.uuid4()),
        target_id=target_id,
        before=before,
        after=after,
        reason=f"command:{command.intent}:{command.source}",
        source="command_apply",
        validated=True,
        candidate_rule_hint=None,
    )
