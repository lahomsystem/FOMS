"""FOMS Brain AX Designer – POST /api/designer/validate."""

from flask import Blueprint, jsonify, request

from foms.web.auth import login_required
from foms.services.designer.validator import validate_design

designer_validation_bp = Blueprint("designer_validation", __name__, url_prefix="/api/designer")


@designer_validation_bp.route("/validate", methods=["POST"])
@login_required
def validate_route():
    """POST /api/designer/validate – validate design_json without persisting."""
    body = request.get_json(force=True, silent=True) or {}
    design_json = body.get("design_json")
    if design_json is None:
        return jsonify({"success": False, "data": None, "error": {"code": "MISSING_DESIGN", "message": "design_json은 필수입니다.", "details": {}}}), 400

    result = validate_design(design_json)
    return jsonify({"success": True, "data": result.to_dict(), "error": None})
