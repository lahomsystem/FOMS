"""FOMS Brain AX Designer – LangGraph Design Assist Graph (MVP).

When DESIGNER_AI_FAKE=1, the graph runs deterministically without any
LLM API calls.  All paths still:
 - record a designer_ai_runs row
 - run the validator
 - only persist a project version when valid + approved
 - record a correction log entry

Graph nodes:
  START -> load_context -> parse_intent -> propose_design_patch
        -> run_validator -> maybe_interrupt_for_review -> persist_result -> END
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
    proposed_patch: dict
    patched_design: dict
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
    """Parse user prompt into a structured intent command.

    In fake mode: returns a deterministic width-change intent.
    In real mode: calls LLM (placeholder – extend with actual LLM call).
    """
    if _FAKE_MODE:
        state["intent"] = {
            "action": "update_dimensions",
            "target": "cabinet",
            "changes": {"width": state["design_json"].get("cabinet", {}).get("width", 2400)},
            "source": "fake_mode",
        }
        return state

    # Real mode placeholder (extend with actual LLM call)
    prompt = state.get("prompt", "")
    state["intent"] = {"action": "noop", "prompt": prompt, "source": "placeholder"}
    return state


def propose_design_patch(state: DesignGraphState) -> DesignGraphState:
    """Generate a design_json patch from the intent.

    MVP: only width/height/depth changes are allowed.
    """
    import copy
    intent = state.get("intent", {})
    design = state.get("design_json", {})

    patched = copy.deepcopy(design)
    state["proposed_patch"] = {}

    if intent.get("action") == "update_dimensions":
        changes: dict[str, Any] = intent.get("changes", {})
        for key in ("width", "height", "depth"):
            if key in changes:
                old_val = patched.get("cabinet", {}).get(key)
                new_val = changes[key]
                if old_val != new_val:
                    patched.setdefault("cabinet", {})[key] = new_val
                    state["proposed_patch"][key] = {"before": old_val, "after": new_val}

    state["patched_design"] = patched
    return state


def run_validator(state: DesignGraphState) -> DesignGraphState:
    """Run the hard-rule validator against the proposed patched design."""
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
        state = propose_design_patch(state)
        state = run_validator(state)
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
