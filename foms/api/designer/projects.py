"""FOMS Brain AX Designer – Project API: GET/POST /api/designer/projects."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from foms.web.auth import login_required
from foms.persistence.designer import (
    create_project,
    create_project_version,
    get_project,
    list_projects,
)
from foms.services.designer.defaults import default_design_json
from foms.services.designer.validator import validate_design

designer_projects_bp = Blueprint("designer_projects", __name__, url_prefix="/api/designer")


def _project_to_dict(p) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "order_id": p.order_id,
        "current_version_id": p.current_version_id,
        "created_by_user_id": p.created_by_user_id,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


def _version_to_dict(v) -> dict:
    return {
        "id": v.id,
        "project_id": v.project_id,
        "version_no": v.version_no,
        "design_json": v.design_json,
        "validation_json": v.validation_json,
        "bom_json": v.bom_json,
        "created_at": v.created_at.isoformat() if v.created_at else None,
    }


@designer_projects_bp.route("/projects", methods=["GET"])
@login_required
def list_projects_route():
    """GET /api/designer/projects – list all projects for current user."""
    from flask import g
    user_id = getattr(g, "user_id", None)
    projects = list_projects(user_id=user_id)
    return jsonify({"success": True, "data": [_project_to_dict(p) for p in projects], "error": None})


@designer_projects_bp.route("/projects", methods=["POST"])
@login_required
def create_project_route():
    """POST /api/designer/projects – create a new project with default design."""
    from flask import g
    body = request.get_json(force=True, silent=True) or {}
    name = str(body.get("name", "새 설계 프로젝트")).strip()
    if not name:
        return jsonify({"success": False, "data": None, "error": {"code": "INVALID_NAME", "message": "프로젝트 이름은 필수입니다.", "details": {}}}), 400

    order_id = body.get("order_id")
    user_id = getattr(g, "user_id", None)

    project = create_project(name=name, order_id=order_id, user_id=user_id)

    # Create initial version with default design
    default = default_design_json()
    vr = validate_design(default)
    create_project_version(
        project_id=project.id,
        design_json=default,
        validation_json={"valid": vr.valid, "errors": [e.model_dump() for e in vr.errors], "warnings": [w.model_dump() for w in vr.warnings]},
        user_id=user_id,
    )

    # Refresh to get current_version_id
    project = get_project(project.id)
    return jsonify({"success": True, "data": _project_to_dict(project), "error": None}), 201


@designer_projects_bp.route("/projects/<int:project_id>", methods=["GET"])
@login_required
def get_project_route(project_id: int):
    """GET /api/designer/projects/<id> – get project detail."""
    project = get_project(project_id)
    if not project:
        return jsonify({"success": False, "data": None, "error": {"code": "NOT_FOUND", "message": "프로젝트를 찾을 수 없습니다.", "details": {}}}), 404
    return jsonify({"success": True, "data": _project_to_dict(project), "error": None})


@designer_projects_bp.route("/projects/<int:project_id>/versions", methods=["POST"])
@login_required
def create_version_route(project_id: int):
    """POST /api/designer/projects/<id>/versions – save a new version (validator gated)."""
    from flask import g
    project = get_project(project_id)
    if not project:
        return jsonify({"success": False, "data": None, "error": {"code": "NOT_FOUND", "message": "프로젝트를 찾을 수 없습니다.", "details": {}}}), 404

    body = request.get_json(force=True, silent=True) or {}
    design_json = body.get("design_json")
    if not design_json:
        return jsonify({"success": False, "data": None, "error": {"code": "MISSING_DESIGN", "message": "design_json은 필수입니다.", "details": {}}}), 400

    # Validator gate – invalid designs must not be saved
    vr = validate_design(design_json)
    validation_payload = {"valid": vr.valid, "errors": [e.model_dump() for e in vr.errors], "warnings": [w.model_dump() for w in vr.warnings]}
    if not vr.valid:
        return jsonify({
            "success": False,
            "data": None,
            "error": {
                "code": "VALIDATION_FAILED",
                "message": "설계 규칙 검증 실패 – 저장이 차단되었습니다.",
                "details": validation_payload,
            },
        }), 422

    user_id = getattr(g, "user_id", None)
    version = create_project_version(
        project_id=project_id,
        design_json=design_json,
        validation_json=validation_payload,
        user_id=user_id,
    )
    return jsonify({"success": True, "data": _version_to_dict(version), "error": None}), 201
