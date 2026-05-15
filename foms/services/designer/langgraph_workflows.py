"""FOMS Brain AX Designer – LangGraph Design Assist Graph.

PV2-B0: LangGraph output now routes through DesignCommand preview/apply.
        AI MUST NOT modify design_json directly.

When DESIGNER_AI_FAKE=1, the graph runs deterministically without any
LLM API calls.  All paths still:
 - record a designer_ai_runs row
 - run the constraint validator
 - only persist a project version when valid + approved
 - record a correction log entry

Graph nodes (design_assist_graph):
  START -> load_context -> parse_intent -> propose_command
        -> preview_command_result -> maybe_interrupt_for_review
        -> apply_command_result -> END

Graph nodes (drawing_layout_to_3d_graph) — B3:
  START -> load_run_context -> load_extraction_candidate
        -> retrieve_design_memory -> load_active_ontology
        -> build_layout_mapping_input -> map_layout_to_design_graph_node
        -> validate_design_graph_candidate -> decide_preview_or_block
        -> human_review_interrupt -> persist_approved_design
        -> save_design_case_memory -> propose_learning_candidates -> END

Checkpoint contract (Phase 1):
  designer_ai_runs.thread_id + state_json = checkpoint store
  interrupt TTL = 24 hours
  resume requires status='interrupt' + matching resume_token
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


def run_drawing_layout_to_3d_graph(
    run_id: int,
    candidate_id: int,
    project_id: int | None = None,
) -> "DrawingLayoutState":
    """B3: Execute the Drawing Layout to 3D Graph.

    Orchestrates: candidate load -> memory retrieval -> ontology load ->
    layout mapping -> validation -> interrupt for human review ->
    persist approved design -> save design case -> propose learning candidates.

    Args:
        run_id: DesignerAIRun.id (already created by caller).
        candidate_id: DesignerExtractionCandidate.id.
        project_id: Target project for saving approved design.

    Returns:
        DrawingLayoutState with final graph state.
    """
    import uuid as _uuid
    thread_id = str(_uuid.uuid4())
    state: DrawingLayoutState = {
        "run_id": run_id,
        "thread_id": thread_id,
        "candidate_id": candidate_id,
        "project_id": project_id,
        "source_extraction_id": None,
        "source_candidate_id": candidate_id,
        "similar_cases": [],
        "ontology_rules": {},
        "layout_mapping_input": {},
        "design_graph_candidate": {},
        "mapping_report": {},
        "preview_allowed": False,
        "approval_blocking_reasons": [],
        "needs_interrupt": False,
        "approved": False,
        "persisted_version_id": None,
        "design_case_id": None,
        "learning_candidates": [],
        "error": None,
    }

    update_ai_run(run_id, "running", state_json=dict(state))

    try:
        state = _dlg_load_extraction_candidate(state)
        if state.get("error"):
            update_ai_run(run_id, "failed", state_json=dict(state), error_text=state["error"])
            return state

        state = _dlg_retrieve_design_memory(state)
        state = _dlg_load_active_ontology(state)
        state = _dlg_build_layout_mapping_input(state)

        if state.get("error"):
            update_ai_run(run_id, "failed", state_json=dict(state), error_text=state["error"])
            return state

        state = _dlg_map_layout_to_design_graph(state)
        state = _dlg_validate_design_graph_candidate(state)
        state = _dlg_decide_preview_or_block(state)

        # Always interrupt for human review when preview is possible
        if state.get("preview_allowed") or state.get("design_graph_candidate"):
            state["needs_interrupt"] = True

        if state.get("needs_interrupt"):
            # Save interrupt state with full preview payload
            update_ai_run(run_id, "interrupt", state_json=dict(state))
            return state

        # If no preview and blocking reasons: fail
        if state.get("approval_blocking_reasons"):
            state["error"] = f"cannot_preview: {state['approval_blocking_reasons']}"
            update_ai_run(run_id, "failed", state_json=dict(state), error_text=state["error"])
            return state

    except Exception as exc:
        state["error"] = str(exc)
        update_ai_run(run_id, "failed", state_json=dict(state), error_text=str(exc))

    return state


def resume_drawing_layout_to_3d_graph(
    run_id: int,
    state: dict,
    decision: str,
) -> "DrawingLayoutState":
    """B3: Resume a drawing layout graph after human review.

    decision: 'approve' or 'reject'
    """
    graph_state: DrawingLayoutState = dict(state)  # type: ignore
    graph_state["approved"] = decision == "approve"

    update_ai_run(run_id, "running", state_json=dict(graph_state))

    try:
        if not graph_state["approved"]:
            graph_state["error"] = "사용자가 거부하였습니다."
            update_ai_run(run_id, "cancelled", state_json=dict(graph_state))
            return graph_state

        graph_state = _dlg_persist_approved_design(graph_state)
        if graph_state.get("error"):
            update_ai_run(run_id, "failed", state_json=dict(graph_state), error_text=graph_state["error"])
            return graph_state

        graph_state = _dlg_save_design_case_memory(graph_state)
        graph_state = _dlg_propose_learning_candidates(graph_state)

        update_ai_run(
            run_id, "succeeded",
            state_json=dict(graph_state),
            output_json={
                "persisted_version_id": graph_state.get("persisted_version_id"),
                "design_case_id": graph_state.get("design_case_id"),
                "learning_candidates": graph_state.get("learning_candidates"),
            },
        )

    except Exception as exc:
        graph_state["error"] = str(exc)
        update_ai_run(run_id, "failed", state_json=dict(graph_state), error_text=str(exc))

    return graph_state


# ---------------------------------------------------------------------------
# B3: DrawingLayoutState TypedDict + Node implementations
# ---------------------------------------------------------------------------

class DrawingLayoutState(DesignGraphState, total=False):
    """State for drawing_layout_to_3d_graph."""
    thread_id: str
    candidate_id: int | None
    source_extraction_id: int | None
    source_candidate_id: int | None
    similar_cases: list
    layout_mapping_input: dict
    design_graph_candidate: dict
    mapping_report: dict
    preview_allowed: bool
    approval_blocking_reasons: list
    design_case_id: int | None
    learning_candidates: list


def _dlg_load_extraction_candidate(state: DrawingLayoutState) -> DrawingLayoutState:
    """Load DesignerExtractionCandidate from DB."""
    candidate_id = state.get("candidate_id")
    if not candidate_id:
        state["error"] = "candidate_id_required"
        return state

    try:
        from db import db_session
        from foms.persistence.designer.models import DesignerExtractionCandidate
        row = db_session.get(DesignerExtractionCandidate, candidate_id)
        if row is None:
            state["error"] = f"candidate_not_found:{candidate_id}"
            return state

        # Attach extraction data to state
        state["source_extraction_id"] = row.extraction_id
        state["source_candidate_id"] = row.id

        # If already has graph candidate JSON from intake pipeline, use it
        if row.design_graph_candidate_json:
            state["design_graph_candidate"] = dict(row.design_graph_candidate_json)
            state["mapping_report"] = dict(row.mapping_report_json or {})
            state["preview_allowed"] = bool(row.preview_allowed)
            state["approval_blocking_reasons"] = list(row.blocking_reasons_json or [])

        # Load extraction for layout_mapping_input
        if row.extraction_id:
            from foms.persistence.designer.models import DesignerDrawingExtraction
            extraction_row = db_session.get(DesignerDrawingExtraction, row.extraction_id)
            if extraction_row:
                state["layout_mapping_input"] = dict(extraction_row.parsed_json or {})

    except Exception as exc:
        state["error"] = f"candidate_load_failed:{exc}"

    return state


def _dlg_retrieve_design_memory(state: DrawingLayoutState) -> DrawingLayoutState:
    """Retrieve similar design cases for context."""
    try:
        from foms.services.designer.design_retrieval import retrieve_similar_cases
        extraction = state.get("layout_mapping_input") or {}
        ep = extraction.get("extracted_params") or {}
        ss = extraction.get("site_size") or {}

        width = ep.get("width") or ss.get("width_mm")
        height = ep.get("height") or ss.get("height_mm")
        furniture_type = extraction.get("furniture_type", "custom_storage")

        cases = retrieve_similar_cases(
            furniture_type=furniture_type,
            width_mm=int(width) if width else None,
            height_mm=int(height) if height else None,
            limit=5,
        )
        state["similar_cases"] = [c.to_dict() if hasattr(c, "to_dict") else c for c in cases]
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("[DLG] retrieve_design_memory failed (non-fatal): %s", exc)
        state["similar_cases"] = []

    return state


def _dlg_load_active_ontology(state: DrawingLayoutState) -> DrawingLayoutState:
    """Load active ontology rules."""
    try:
        from foms.persistence.designer import get_or_create_default_ontology
        ontology = get_or_create_default_ontology()
        state["ontology_rules"] = dict(ontology.rules_json or {})
    except Exception:
        state["ontology_rules"] = {}
    return state


def _dlg_build_layout_mapping_input(state: DrawingLayoutState) -> DrawingLayoutState:
    """Validate that layout_mapping_input has required fields."""
    inp = state.get("layout_mapping_input") or {}
    if not inp:
        state["error"] = "layout_mapping_input_empty"
        return state

    ss = inp.get("site_size") or {}
    ep = inp.get("extracted_params") or {}
    has_width = ss.get("width_mm") or ep.get("width")
    has_height = ss.get("height_mm") or ep.get("height")

    if not has_width or not has_height:
        import logging
        logging.getLogger(__name__).warning("[DLG] layout_mapping_input missing required dimensions")
        # Not a hard block — mapper will add to unresolved_fields

    return state


def _dlg_map_layout_to_design_graph(state: DrawingLayoutState) -> DrawingLayoutState:
    """Run layout_graph_mapper if design_graph_candidate not already set."""
    if state.get("design_graph_candidate") and state.get("mapping_report"):
        # Already mapped by intake pipeline, skip re-mapping
        return state

    try:
        from foms.services.designer.layout_graph_mapper import map_extraction_to_design_graph
        extraction = state.get("layout_mapping_input") or {}
        result = map_extraction_to_design_graph(
            extraction,
            source_extraction_id=state.get("source_extraction_id"),
            source_candidate_id=state.get("source_candidate_id"),
            similar_cases=state.get("similar_cases"),
            ontology_rules=state.get("ontology_rules"),
        )
        state["design_graph_candidate"] = result.design_graph
        state["mapping_report"] = result.mapping_report.to_dict()
        state["preview_allowed"] = result.preview_allowed
        state["approval_blocking_reasons"] = result.approval_blocking_reasons
    except Exception as exc:
        state["error"] = f"mapping_failed:{exc}"

    return state


def _dlg_validate_design_graph_candidate(state: DrawingLayoutState) -> DrawingLayoutState:
    """Re-validate the design graph candidate."""
    graph = state.get("design_graph_candidate") or {}
    if not graph:
        return state

    try:
        from foms.services.designer.validator import validate_design
        result = validate_design(graph)
        if result.errors:
            for e in result.errors:
                reason = f"validator_error:{e.code}"
                if reason not in state["approval_blocking_reasons"]:
                    state["approval_blocking_reasons"].append(reason)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("[DLG] validator failed (non-fatal): %s", exc)

    return state


def _dlg_decide_preview_or_block(state: DrawingLayoutState) -> DrawingLayoutState:
    """Determine if preview is allowed and set interrupt state."""
    graph = state.get("design_graph_candidate") or {}
    has_components = bool(graph.get("components"))

    if has_components:
        state["preview_allowed"] = True
    else:
        state["preview_allowed"] = False
        if "no_components_in_design_graph" not in state.get("approval_blocking_reasons", []):
            reasons = list(state.get("approval_blocking_reasons") or [])
            reasons.append("no_components_in_design_graph")
            state["approval_blocking_reasons"] = reasons

    return state


def _dlg_persist_approved_design(state: DrawingLayoutState) -> DrawingLayoutState:
    """Persist approved design as a project version. Blocks on no-op/empty graph."""
    graph = state.get("design_graph_candidate") or {}
    project_id = state.get("project_id")

    # Gate: no-op / empty graph
    if not graph or not graph.get("components"):
        state["error"] = "persist_blocked:empty_design_graph"
        return state

    if not project_id:
        state["error"] = "persist_blocked:project_id_required"
        return state

    try:
        from foms.persistence.designer import create_project_version
        version = create_project_version(
            project_id=int(project_id),
            design_json=graph,
        )
        state["persisted_version_id"] = version.id
    except Exception as exc:
        state["error"] = f"persist_failed:{exc}"

    return state


def _dlg_save_design_case_memory(state: DrawingLayoutState) -> DrawingLayoutState:
    """Save approved design as DesignerDesignCase (learning memory)."""
    version_id = state.get("persisted_version_id")
    graph = state.get("design_graph_candidate") or {}
    project_id = state.get("project_id")

    if not version_id or not graph:
        return state

    try:
        from foms.services.designer.design_case_memory import save_design_case
        from foms.services.designer.product_archetype_learning import extract_tags_from_case

        internal_structure = {
            "design_understanding": (state.get("layout_mapping_input") or {}).get("design_understanding") or {},
            "mapping_report": state.get("mapping_report") or {},
            "similar_cases_used": len(state.get("similar_cases") or []),
        }
        furniture_type = graph.get("metadata", {}).get("furniture_type") or "custom_storage"

        tags = extract_tags_from_case({
            "furniture_type": furniture_type,
            "internal_structure_json": internal_structure,
        })

        result = save_design_case(
            project_version_id=version_id,
            furniture_type=furniture_type,
            design_graph=graph,
            project_id=int(project_id) if project_id else None,
            approved_extraction_id=state.get("source_extraction_id"),
            internal_structure=internal_structure,
            tags=tags,
        )
        state["design_case_id"] = result.get("id")
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error("[DLG] save_design_case_memory failed: %s", exc)
        # Non-fatal: project version already created

    return state


def _dlg_propose_learning_candidates(state: DrawingLayoutState) -> DrawingLayoutState:
    """Propose archetype/rule candidates from approved design (never auto-promotes)."""
    design_case_id = state.get("design_case_id")
    if not design_case_id:
        state["learning_candidates"] = []
        return state

    try:
        from foms.services.designer.product_archetype_learning import propose_archetype_candidates
        candidates = propose_archetype_candidates(design_case_id=design_case_id)
        state["learning_candidates"] = candidates or []
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("[DLG] propose_learning_candidates failed (non-fatal): %s", exc)
        state["learning_candidates"] = []

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
