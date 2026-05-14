"""FOMS Brain Post-V1 — Vision API.

PV2-B5/B6/B7:
  POST /api/designer/vision/intake
  POST /api/designer/vision/extract
  POST /api/designer/vision/candidates/<id>/approve
  POST /api/designer/vision/candidates/<id>/reject
"""

from __future__ import annotations

from flask import Blueprint, request, jsonify, g

from foms.web.auth import login_required
from foms.services.designer.vision_types import VisionInput, DesignGraphCandidate

vision_bp = Blueprint("designer_vision", __name__, url_prefix="/api/designer")

# In-memory candidate store (MVP — in production use DB table)
_CANDIDATE_STORE: dict[str, dict] = {}


@vision_bp.route("/vision/intake", methods=["POST"])
@login_required
def intake():
    """POST /api/designer/vision/intake

    Accepts raw image reference. Does NOT create project version.

    Body:
      { image_url, attachment_id, source, calibration, target_furniture_type, project_id }

    Returns:
      { success, data: { vision_input }, error }
    """
    body = request.get_json(silent=True) or {}
    user_id = getattr(g, "user_id", None)

    vision_input = VisionInput.from_dict(body)
    if user_id:
        vision_input.project_id = body.get("project_id") or vision_input.project_id

    errors = vision_input.validate()
    if errors:
        return jsonify({"success": False, "error": "; ".join(errors)}), 400

    return jsonify({
        "success": True,
        "data": {"vision_input": vision_input.to_dict()},
        "error": None,
    })


@vision_bp.route("/vision/extract", methods=["POST"])
@login_required
def extract():
    """POST /api/designer/vision/extract

    Runs extraction on a VisionInput and returns DesignGraphCandidate.
    Does NOT save to project version. Requires human review before apply.

    Body: { vision_input: {...} }

    Returns:
      { success, data: { candidate, can_apply }, error }
    """
    body = request.get_json(silent=True) or {}
    vi_data = body.get("vision_input")
    if not vi_data:
        return jsonify({"success": False, "error": "vision_input 필드가 없습니다."}), 400

    vision_input = VisionInput.from_dict(vi_data)
    errors = vision_input.validate()
    if errors:
        return jsonify({"success": False, "error": "; ".join(errors)}), 400

    try:
        from foms.services.designer.vision_extractor import extract_candidate, VisionProviderUnavailable
        candidate = extract_candidate(vision_input)
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500

    # Store candidate for review
    _CANDIDATE_STORE[candidate.candidate_id] = candidate.to_dict()

    return jsonify({
        "success": True,
        "data": {
            "candidate": candidate.to_dict(),
            "can_apply": candidate.can_apply(),
        },
        "error": None,
    })


@vision_bp.route("/vision/candidates/<candidate_id>/approve", methods=["POST"])
@login_required
def approve_candidate(candidate_id: str):
    """POST /api/designer/vision/candidates/<id>/approve

    Human approval — candidate can now be applied to create a project version.
    Requires unresolved_fields to be empty.
    """
    candidate_data = _CANDIDATE_STORE.get(candidate_id)
    if not candidate_data:
        return jsonify({"success": False, "error": f"Candidate {candidate_id} not found"}), 404

    if candidate_data.get("unresolved_fields"):
        fields = candidate_data["unresolved_fields"]
        return jsonify({
            "success": False,
            "error": f"Cannot approve: unresolved fields: {fields}",
        }), 422

    candidate_data["approved"] = True
    candidate_data["can_apply"] = (
        len(candidate_data.get("unresolved_fields", [])) == 0
        and candidate_data.get("validated", False)
        and candidate_data["approved"]
    )
    _CANDIDATE_STORE[candidate_id] = candidate_data

    return jsonify({
        "success": True,
        "data": {"candidate": candidate_data},
        "error": None,
    })


@vision_bp.route("/vision/candidates/<candidate_id>/reject", methods=["POST"])
@login_required
def reject_candidate(candidate_id: str):
    """POST /api/designer/vision/candidates/<id>/reject"""
    if candidate_id in _CANDIDATE_STORE:
        _CANDIDATE_STORE[candidate_id]["approved"] = False
        _CANDIDATE_STORE[candidate_id]["can_apply"] = False
    return jsonify({"success": True, "data": {"status": "rejected"}, "error": None})
