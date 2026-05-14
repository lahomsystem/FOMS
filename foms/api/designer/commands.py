"""FOMS Brain AX Designer — Command API endpoints.

DK-B7:
  POST /api/designer/commands/preview
  POST /api/designer/commands/apply
"""

from __future__ import annotations

import uuid
from flask import Blueprint, request, jsonify, g
from foms.web.auth import login_required

from foms.services.designer.command_engine import preview_command, apply_command
from foms.services.designer.ontology_types import DesignCommand, DesignGraph

commands_bp = Blueprint("designer_commands", __name__)


def _parse_command(data: dict) -> DesignCommand | None:
    """Parse DesignCommand from request dict. Returns None if invalid."""
    try:
        if not data.get("command_id"):
            data["command_id"] = str(uuid.uuid4())
        return DesignCommand.from_dict(data)
    except Exception:
        return None


def _load_graph(project_id: int, version_id: int | None = None) -> DesignGraph | None:
    """Load DesignGraph from DB, normalizing v1 → v2 on the fly.

    V1 projects are normalized to schema v2 via defaults.normalize_to_v2 so
    the command engine can operate on them without requiring a prior save.
    """
    from foms.persistence.designer.repositories import get_project_version
    from foms.services.designer.ontology_types import DesignGraph as _DG
    from foms.services.designer.defaults import normalize_to_v2

    try:
        version = get_project_version(project_id, version_id)
        if not version:
            return None
        design_json = version.design_json or {}
        # Normalize v1 → v2 transparently
        design_json = normalize_to_v2(design_json)
        if design_json.get("schema_version") != 2:
            return None
        return _DG.from_dict(design_json)
    except Exception:
        return None


@commands_bp.route("/api/designer/commands/preview", methods=["POST"])
@login_required
def preview():
    """Preview a DesignCommand without applying it.

    Request body:
      {
        "project_id": int,
        "version_id": int (optional),
        "command": DesignCommand dict
      }

    Returns: {success, data: {patches, constraint_result, would_be_valid}, error}
    """
    body = request.get_json(silent=True) or {}

    project_id = body.get("project_id")
    if not project_id:
        return jsonify({"success": False, "error": "project_id 필요"}), 400

    command_data = body.get("command", {})
    command = _parse_command(command_data)
    if not command:
        return jsonify({"success": False, "error": "유효하지 않은 command 형식"}), 400

    graph = _load_graph(project_id, body.get("version_id"))
    if graph is None:
        return jsonify({"success": False, "error": "schema v2 design graph를 로드할 수 없습니다."}), 404

    result = preview_command(command, graph)
    return jsonify({"success": result["success"], "data": result, "error": result.get("error")})


@commands_bp.route("/api/designer/commands/apply", methods=["POST"])
@login_required
def apply():
    """Apply a DesignCommand to the current design version.

    Request body:
      {
        "project_id": int,
        "version_id": int (optional, defaults to current),
        "command": DesignCommand dict
      }

    Returns: {success, data: {patches, constraint_result, correction_delta}, error}

    Saves new version only if the result is valid.
    """
    from foms.persistence.designer.repositories import save_design_version
    from foms.services.designer.corrections import log_correction_delta

    body = request.get_json(silent=True) or {}

    project_id = body.get("project_id")
    if not project_id:
        return jsonify({"success": False, "error": "project_id 필요"}), 400

    command_data = body.get("command", {})
    command = _parse_command(command_data)
    if not command:
        return jsonify({"success": False, "error": "유효하지 않은 command 형식"}), 400

    graph = _load_graph(project_id, body.get("version_id"))
    if graph is None:
        return jsonify({"success": False, "error": "schema v2 design graph를 로드할 수 없습니다."}), 404

    result = apply_command(
        command,
        graph,
        user_id=getattr(g, "user_id", None),
    )

    if not result["success"]:
        return jsonify({"success": False, "data": result, "error": result.get("error")}), 422

    # Save new version
    try:
        user_id = getattr(g, "user_id", None)
        new_version = save_design_version(project_id, graph.to_dict(), user_id=user_id)
    except Exception as e:
        return jsonify({"success": False, "error": f"버전 저장 실패: {e}"}), 500

    # Log correction delta
    delta_data = result.get("correction_delta")
    if delta_data:
        try:
            log_correction_delta(
                delta_data,
                project_id=project_id,
                project_version_id=new_version.id if new_version else None,
                user_id=getattr(g, "user_id", None),
            )
        except Exception:
            pass  # Delta logging failure is non-blocking

    return jsonify({
        "success": True,
        "data": {
            **result,
            "new_version_id": new_version.id if new_version else None,
        },
        "error": None,
    })
