"""FOMS Brain AX Designer – AI Runs API.

B3: Adds drawing_layout_to_3d_graph endpoints.
  POST /api/designer/ai-runs/drawing-layout   — start drawing layout → 3D run
  POST /api/designer/ai-runs/<id>/resume      — resume (approve/reject) any graph

Checkpoint contract (Phase 1):
  Interrupt state is stored in designer_ai_runs.state_json.
  TTL = 24 hours. Expired interrupts return HTTP 409.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta

from flask import Blueprint, jsonify, request

from foms.web.auth import login_required
from foms.persistence.designer import create_ai_run, get_ai_run
from foms.services.designer.langgraph_workflows import (
    run_design_assist_graph,
    resume_design_assist_graph,
    run_drawing_layout_to_3d_graph,
    resume_drawing_layout_to_3d_graph,
)

designer_ai_runs_bp = Blueprint("designer_ai_runs", __name__, url_prefix="/api/designer")

_INTERRUPT_TTL_HOURS = 24


def _run_to_dict(run) -> dict:
    return {
        "id": run.id,
        "graph_name": run.graph_name,
        "graph_version": run.graph_version,
        "thread_id": run.thread_id,
        "status": run.status,
        "input_json": run.input_json,
        "state_json": run.state_json,
        "output_json": run.output_json,
        "error_text": run.error_text,
        "created_by_user_id": run.created_by_user_id,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "updated_at": run.updated_at.isoformat() if run.updated_at else None,
    }


@designer_ai_runs_bp.route("/ai-runs", methods=["POST"])
@login_required
def create_ai_run_route():
    """POST /api/designer/ai-runs – launch a Design Assist Graph run."""
    from flask import g
    body = request.get_json(force=True, silent=True) or {}
    project_id = body.get("project_id")
    prompt = str(body.get("prompt", "")).strip()
    design_json = body.get("design_json") or {}

    if not prompt:
        return jsonify({"success": False, "data": None, "error": {"code": "MISSING_PROMPT", "message": "prompt는 필수입니다.", "details": {}}}), 400

    user_id = getattr(g, "user_id", None)
    thread_id = str(uuid.uuid4())

    run = create_ai_run(
        graph_name="design_assist_graph",
        thread_id=thread_id,
        input_json={"project_id": project_id, "prompt": prompt, "design_json": design_json},
        user_id=user_id,
    )

    # Run synchronously (MVP – in production this would be async via RQ/Celery)
    run_design_assist_graph(
        run_id=run.id,
        project_id=project_id,
        prompt=prompt,
        design_json=design_json,
    )

    # Re-fetch updated run
    run = get_ai_run(run.id)
    return jsonify({"success": True, "data": _run_to_dict(run), "error": None}), 201


@designer_ai_runs_bp.route("/ai-runs/<int:run_id>", methods=["GET"])
@login_required
def get_ai_run_route(run_id: int):
    """GET /api/designer/ai-runs/<id> – get run status."""
    run = get_ai_run(run_id)
    if not run:
        return jsonify({"success": False, "data": None, "error": {"code": "NOT_FOUND", "message": "AI 실행을 찾을 수 없습니다.", "details": {}}}), 404
    return jsonify({"success": True, "data": _run_to_dict(run), "error": None})


@designer_ai_runs_bp.route("/ai-runs/drawing-layout", methods=["POST"])
@login_required
def create_drawing_layout_run():
    """POST /api/designer/ai-runs/drawing-layout — B3: Start drawing layout → 3D run.

    Body: { candidate_id: int, project_id: int | null }

    Returns run in 'interrupt' status with 3D preview payload in state_json.
    """
    from flask import g
    body = request.get_json(force=True, silent=True) or {}
    candidate_id = body.get("candidate_id")
    project_id = body.get("project_id")

    if not candidate_id:
        return jsonify({
            "success": False, "data": None,
            "error": {"code": "MISSING_CANDIDATE_ID", "message": "candidate_id는 필수입니다.", "details": {}},
        }), 400

    user_id = getattr(g, "user_id", None)
    thread_id = str(uuid.uuid4())
    interrupt_expires_at = (datetime.now(timezone.utc) + timedelta(hours=_INTERRUPT_TTL_HOURS)).isoformat()

    run = create_ai_run(
        graph_name="drawing_layout_to_3d_graph",
        thread_id=thread_id,
        input_json={
            "candidate_id": candidate_id,
            "project_id": project_id,
            "interrupt_expires_at": interrupt_expires_at,
        },
        user_id=user_id,
    )

    run_drawing_layout_to_3d_graph(
        run_id=run.id,
        candidate_id=int(candidate_id),
        project_id=project_id,
    )

    run = get_ai_run(run.id)
    return jsonify({"success": True, "data": _run_to_dict(run), "error": None}), 201


@designer_ai_runs_bp.route("/ai-runs/<int:run_id>/resume", methods=["POST"])
@login_required
def resume_ai_run_route(run_id: int):
    """POST /api/designer/ai-runs/<id>/resume – approve or reject interrupted run.

    B3: Supports both design_assist_graph and drawing_layout_to_3d_graph.
    TTL check: expired interrupts return 409.
    """
    run = get_ai_run(run_id)
    if not run:
        return jsonify({"success": False, "data": None, "error": {"code": "NOT_FOUND", "message": "AI 실행을 찾을 수 없습니다.", "details": {}}}), 404

    if run.status != "interrupt":
        return jsonify({"success": False, "data": None, "error": {"code": "NOT_INTERRUPTED", "message": "interrupt 상태인 실행만 재개할 수 있습니다.", "details": {}}}), 409

    # B3: TTL check
    state = run.state_json or {}
    input_json = run.input_json or {}
    expires_at_str = input_json.get("interrupt_expires_at") or state.get("interrupt_expires_at")
    if expires_at_str:
        try:
            expires_at = datetime.fromisoformat(expires_at_str)
            if datetime.now(timezone.utc) > expires_at:
                return jsonify({
                    "success": False, "data": None,
                    "error": {
                        "code": "INTERRUPT_EXPIRED",
                        "message": "검토 시간이 만료되었습니다. 새 실행을 시작하세요.",
                        "details": {"expired_at": expires_at_str},
                    },
                }), 409
        except (ValueError, TypeError):
            pass

    body = request.get_json(force=True, silent=True) or {}
    decision = str(body.get("decision", "")).strip()
    if decision not in ("approve", "reject"):
        return jsonify({"success": False, "data": None, "error": {"code": "INVALID_DECISION", "message": "decision은 approve 또는 reject이어야 합니다.", "details": {}}}), 400

    # Route to correct resume function based on graph_name
    if run.graph_name == "drawing_layout_to_3d_graph":
        resume_drawing_layout_to_3d_graph(
            run_id=run.id,
            state=state,
            decision=decision,
        )
    else:
        resume_design_assist_graph(
            run_id=run.id,
            state=state,
            decision=decision,
        )

    run = get_ai_run(run_id)
    return jsonify({"success": True, "data": _run_to_dict(run), "error": None})
