"""FOMS Brain AX Designer – GET /api/designer/ontology/current."""

from flask import Blueprint, jsonify

from foms.web.auth import login_required
from foms.persistence.designer import get_or_create_default_ontology

designer_ontology_bp = Blueprint("designer_ontology", __name__, url_prefix="/api/designer")


@designer_ontology_bp.route("/ontology/current", methods=["GET"])
@login_required
def get_current_ontology():
    """GET /api/designer/ontology/current – return active ontology rules."""
    try:
        ontology = get_or_create_default_ontology()
        return jsonify({
            "success": True,
            "data": {
                "id": ontology.id,
                "version_key": ontology.version_key,
                "status": ontology.status,
                "rules_json": ontology.rules_json,
                "created_at": ontology.created_at.isoformat() if ontology.created_at else None,
            },
            "error": None,
        })
    except Exception as exc:
        return jsonify({
            "success": False,
            "data": None,
            "error": {"code": "ONTOLOGY_ERROR", "message": str(exc), "details": {}},
        }), 500
