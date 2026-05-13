"""FOMS Brain AX Designer – AI Runs API."""

from __future__ import annotations

import uuid

from flask import Blueprint, jsonify, request

from foms.web.auth import login_required
from foms.persistence.designer import create_ai_run, get_ai_run
from foms.services.designer.langgraph_workflows import (
    run_design_assist_graph,
    resume_design_assist_graph,
)

designer_ai_runs_bp = Blueprint("designer_ai_runs", __name__, url_prefix="/api/designer")


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


@designer_ai_runs_bp.route("/ai-runs/<int:run_id>/resume", methods=["POST"])
@login_required
def resume_ai_run_route(run_id: int):
    """POST /api/designer/ai-runs/<id>/resume – approve or reject interrupted run."""
    run = get_ai_run(run_id)
    if not run:
        return jsonify({"success": False, "data": None, "error": {"code": "NOT_FOUND", "message": "AI 실행을 찾을 수 없습니다.", "details": {}}}), 404

    if run.status != "interrupt":
        return jsonify({"success": False, "data": None, "error": {"code": "NOT_INTERRUPTED", "message": "interrupt 상태인 실행만 재개할 수 있습니다.", "details": {}}}), 409

    body = request.get_json(force=True, silent=True) or {}
    decision = str(body.get("decision", "")).strip()
    if decision not in ("approve", "reject"):
        return jsonify({"success": False, "data": None, "error": {"code": "INVALID_DECISION", "message": "decision은 approve 또는 reject이어야 합니다.", "details": {}}}), 400

    resume_design_assist_graph(
        run_id=run.id,
        state=run.state_json or {},
        decision=decision,
    )

    run = get_ai_run(run_id)
    return jsonify({"success": True, "data": _run_to_dict(run), "error": None})
