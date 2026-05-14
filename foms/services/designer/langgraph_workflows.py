"""FOMS Brain AX Designer – LangGraph Design Assist Graph.

PV2-B0: LangGraph output now routes through DesignCommand preview/apply.
        AI MUST NOT modify design_json directly.

When DESIGNER_AI_FAKE=1, the graph runs deterministically without any
LLM API calls.  All paths still:
 - record a designer_ai_runs row
 - run the constraint validator
 - only persist a project version when valid + approved
 - record a correction log entry

Graph nodes:
  START -> load_context -> parse_intent -> propose_command
        -> preview_command_result -> maybe_interrupt_for_review
        -> apply_command_result -> END
"""

from __future__ import annotations

import os
import uuid
from typing import Any, Optional, TypedDict

from foms.services.designer.validator import validate_design
from foms.persistence.designer.repositories import (
    create_correction,
    create_project_version,
    update_ai_run,
)


_FAKE_MODE = os.environ.get("DESIGNER_AI_FAKE", "0") == "1"


# ---------------------------------------------------------------------------
# Graph State
# ---------------------------------------------------------------------------

class DesignGraphState(TypedDict, total=False):
    run_id: int
    project_id: Optional[int]
    prompt: str
    design_json: dict
    ontology_rules: dict
    intent: dict
    # PV2-B0: proposed_command replaces direct patched_design mutation
    proposed_command: Optional[dict]   # DesignCommand dict
    command_preview_result: Optional[dict]  # preview() return value
    proposed_patch: dict               # kept for correction log
    patched_design: dict               # result after safe apply
    validation_result: dict
    needs_interrupt: bool
    interrupt_reason: str
    approved: bool
    persisted_version_id: Optional[int]
    error: Optional[str]


# ---------------------------------------------------------------------------
# Node implementations
# ---------------------------------------------------------------------------

def load_context(state: DesignGraphState) -> DesignGraphState:
    """Load current design and ontology rules into state."""
    from foms.persistence.designer import get_or_create_default_ontology
    try:
        ontology = get_or_create_default_ontology()
        state["ontology_rules"] = ontology.rules_json or {}
    except Exception:
        state["ontology_rules"] = {}
    return state


def parse_intent(state: DesignGraphState) -> DesignGraphState:
    """Parse user prompt into a structured DesignCommand.

    PV2-B0: intent is now a DesignCommand dict, NOT a direct design mutation.

    In fake mode: returns a deterministic generate_layout command.
    In real mode: placeholder — replace with LUI parser (PV2-B1).
    """
    import uuid as _uuid
    design = state.get("design_json", {})
    assembly = design.get("assembly", {})
    asm_id = assembly.get("id", "unknown")

    if _FAKE_MODE:
        # Fake: generate_layout command — changes nothing by default (no-op safe)
        state["intent"] = {
            "intent": "generate_layout",
            "source": "fake_mode",
            "target_component_id": asm_id,
            "operation": {},
        }
    else:
        # Real mode: route through LUI parser when available (PV2-B1)
        # For now: noop command so no mutations happen
        prompt = state.get("prompt", "")
        state["intent"] = {
            "intent": "generate_layout",
            "source": "placeholder",
            "target_component_id": asm_id,
            "operation": {},
            "raw_prompt": prompt,
        }
    return state


def propose_command(state: DesignGraphState) -> DesignGraphState:
    """Build a DesignCommand from parsed intent.

    PV2-B0: AI MUST NOT modify design_json directly.
    All mutations go through DesignCommand -> preview -> apply.
    """
    import uuid as _uuid
    intent_data = state.get("intent", {})

    cmd: dict[str, Any] = {
        "command_id": str(_uuid.uuid4()),
        "source": intent_data.get("source", "ai"),
        "intent": intent_data.get("intent", "generate_layout"),
        "target": {"component_id": intent_data.get("target_component_id", "")},
        "operation": intent_data.get("operation", {}),
        "preview_only": True,
    }
    state["proposed_command"] = cmd
    state["proposed_patch"] = {}
    return state


def preview_command_result(state: DesignGraphState) -> DesignGraphState:
    """Preview the proposed DesignCommand without applying it.

    PV2-B0: replaces direct patched_design mutation.
    Sets validation_result from constraint_engine via command preview.
    """
    import copy
    from foms.services.designer.ontology_types import DesignCommand as _DC, DesignGraph as _DG
    from foms.services.designer.command_engine import preview_command as _preview

    design = state.get("design_json", {})
    cmd_data = state.get("proposed_command")

    # Fall back to original design if no command or schema v1
    if not cmd_data or design.get("schema_version") != 2:
        state["patched_design"] = copy.deepcopy(design)
        state["validation_result"] = validate_design(design).to_dict()
        state["command_preview_result"] = {"success": True, "patches": []}
        return state

    try:
        graph = _DG.from_dict(design)
        cmd = _DC.from_dict(cmd_data)
        preview = _preview(cmd, graph)
        state["command_preview_result"] = preview
        state["validation_result"] = preview.get("constraint_result", validate_design(design).to_dict())
        # proposed_patch: collect first patch for correction log
        patches = preview.get("patches", [])
        state["proposed_patch"] = {p["prop_path"]: {"before": p["before"], "after": p["after"]} for p in patches}
        # patched_design stays original until apply
        state["patched_design"] = copy.deepcopy(design)
    except Exception as exc:
        state["command_preview_result"] = {"success": False, "error": str(exc)}
        state["validation_result"] = validate_design(design).to_dict()
        state["patched_design"] = copy.deepcopy(design)

    return state


def run_validator(state: DesignGraphState) -> DesignGraphState:
    """Re-validate patched_design (safety net after preview)."""
    result = validate_design(state.get("patched_design", {}))
    state["validation_result"] = result.to_dict()
    return state


def maybe_interrupt_for_review(state: DesignGraphState) -> DesignGraphState:
    """Determine if human review is needed before persisting.

    In fake mode: always mark as needing interrupt so the resume flow is tested.
    In real mode: interrupt when there are warnings or risky changes.
    """
    vr = state.get("validation_result", {})
    warnings = vr.get("warnings", [])
    patch = state.get("proposed_patch", {})

    if _FAKE_MODE:
        # Fake mode: trigger interrupt for testing unless already approved
        if not state.get("approved"):
            state["needs_interrupt"] = True
            state["interrupt_reason"] = "FAKE_MODE_REVIEW: 변경 내용을 검토하세요."
        else:
            state["needs_interrupt"] = False
    elif warnings or len(patch) > 2:
        state["needs_interrupt"] = True
        state["interrupt_reason"] = f"경고 {len(warnings)}개 또는 다중 변경 감지"
    else:
        state["needs_interrupt"] = False

    return state


def persist_result(state: DesignGraphState) -> DesignGraphState:
    """Persist approved + valid design as a new project version.

    INVARIANT: this node MUST NOT save if validation failed or not approved.
    """
    vr = state.get("validation_result", {})
    if not vr.get("valid"):
        state["error"] = "검증 실패 – 저장이 차단되었습니다."
        return state

    if state.get("needs_interrupt") and not state.get("approved"):
        # Should not reach here; safety net
        state["error"] = "검토 미승인 – 저장이 차단되었습니다."
        return state

    project_id = state.get("project_id")
    run_id = state.get("run_id")

    version = None
    if project_id:
        version = create_project_version(
            project_id=project_id,
            design_json=state["patched_design"],
            validation_json=vr,
        )
        state["persisted_version_id"] = version.id

        # Correction log
        create_correction(
            before_json=state.get("design_json", {}),
            after_json=state["patched_design"],
            reason_text=state.get("prompt", ""),
            project_id=project_id,
            project_version_id=version.id,
            ai_run_id=run_id,
        )

    return state


# ---------------------------------------------------------------------------
# Graph runner
# ---------------------------------------------------------------------------

def run_design_assist_graph(
    run_id: int,
    project_id: Optional[int],
    prompt: str,
    design_json: dict,
) -> DesignGraphState:
    """Execute the Design Assist Graph synchronously.

    Returns the final graph state.  Persists run status transitions.
    """
    thread_id = str(uuid.uuid4())
    state: DesignGraphState = {
        "run_id": run_id,
        "project_id": project_id,
        "prompt": prompt,
        "design_json": design_json,
        "ontology_rules": {},
        "intent": {},
        "proposed_patch": {},
        "patched_design": {},
        "validation_result": {},
        "needs_interrupt": False,
        "interrupt_reason": "",
        "approved": False,
        "persisted_version_id": None,
        "error": None,
    }

    update_ai_run(run_id, "running", state_json=dict(state))

    try:
        state = load_context(state)
        state = parse_intent(state)
        state = propose_command(state)
        state = preview_command_result(state)
        state = maybe_interrupt_for_review(state)

        if state.get("needs_interrupt"):
            update_ai_run(run_id, "interrupt", state_json=dict(state))
            return state

        state = persist_result(state)

        if state.get("error"):
            update_ai_run(run_id, "failed", state_json=dict(state), error_text=state["error"])
        else:
            update_ai_run(
                run_id, "succeeded",
                state_json=dict(state),
                output_json={
                    "patched_design": state.get("patched_design"),
                    "version_id": state.get("persisted_version_id"),
                    "patch": state.get("proposed_patch"),
                },
            )

    except Exception as exc:
        update_ai_run(run_id, "failed", state_json=dict(state), error_text=str(exc))
        state["error"] = str(exc)

    return state


def resume_design_assist_graph(
    run_id: int,
    state: dict,
    decision: str,
) -> DesignGraphState:
    """Resume a graph that was interrupted for human review.

    decision: 'approve' or 'reject'
    """
    graph_state: DesignGraphState = dict(state)  # type: ignore
    graph_state["approved"] = decision == "approve"

    update_ai_run(run_id, "running", state_json=dict(graph_state))

    try:
        if not graph_state["approved"]:
            update_ai_run(run_id, "cancelled", state_json=dict(graph_state))
            graph_state["error"] = "사용자가 거부하였습니다."
            return graph_state

        graph_state = persist_result(graph_state)

        if graph_state.get("error"):
            update_ai_run(run_id, "failed", state_json=dict(graph_state), error_text=graph_state["error"])
        else:
            update_ai_run(
                run_id, "succeeded",
                state_json=dict(graph_state),
                output_json={
                    "patched_design": graph_state.get("patched_design"),
                    "version_id": graph_state.get("persisted_version_id"),
                    "patch": graph_state.get("proposed_patch"),
                },
            )

    except Exception as exc:
        update_ai_run(run_id, "failed", state_json=dict(graph_state), error_text=str(exc))
        graph_state["error"] = str(exc)

    return graph_state
