"""FOMS Brain Post-V1 — Evolution API.

PV2-B8/B9:
  GET  /api/designer/evolution/candidates
  POST /api/designer/evolution/candidates/from-corrections
  POST /api/designer/evolution/candidates/<id>/replay
  POST /api/designer/evolution/candidates/<id>/set-approved
  POST /api/designer/evolution/candidates/<id>/promote
"""

from __future__ import annotations

from flask import Blueprint, request, jsonify, g

from foms.web.auth import login_required

evolution_bp = Blueprint("designer_evolution", __name__, url_prefix="/api/designer")


@evolution_bp.route("/evolution/candidates", methods=["GET"])
@login_required
def list_candidates():
    """GET /api/designer/evolution/candidates — list rule candidates."""
    from db import db_session
    from foms.persistence.designer.models import DesignerRuleCandidate

    status = request.args.get("status")
    query = db_session.query(DesignerRuleCandidate)
    if status:
        query = query.filter(DesignerRuleCandidate.status == status)
    candidates = query.order_by(DesignerRuleCandidate.created_at.desc()).limit(50).all()

    return jsonify({
        "success": True,
        "data": [
            {
                "id": c.id,
                "status": c.status,
                "candidate_json": c.candidate_json,
                "replay_report_json": c.replay_report_json,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in candidates
        ],
        "error": None,
    })


@evolution_bp.route("/evolution/candidates/from-corrections", methods=["POST"])
@login_required
def create_from_corrections():
    """POST /api/designer/evolution/candidates/from-corrections

    Body: { correction_ids: [int], candidate_json: dict }
    """
    from foms.services.designer.evolution import create_rule_candidate_from_corrections

    body = request.get_json(silent=True) or {}
    correction_ids = body.get("correction_ids", [])
    candidate_json = body.get("candidate_json", {})

    if not correction_ids or not candidate_json:
        return jsonify({"success": False, "error": "correction_ids와 candidate_json 필요"}), 400

    result = create_rule_candidate_from_corrections(correction_ids, candidate_json)
    return jsonify({"success": True, "data": result, "error": None}), 201


@evolution_bp.route("/evolution/candidates/<int:candidate_id>/replay", methods=["POST"])
@login_required
def replay(candidate_id: int):
    """POST /api/designer/evolution/candidates/<id>/replay

    Body (optional): { fixture_designs: [...] }
    """
    from foms.services.designer.evolution import replay_rule_candidate

    body = request.get_json(silent=True) or {}
    fixtures = body.get("fixture_designs") or None

    try:
        report = replay_rule_candidate(candidate_id, fixture_designs=fixtures)
        return jsonify({"success": True, "data": report, "error": None})
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404


@evolution_bp.route("/evolution/candidates/<int:candidate_id>/set-approved", methods=["POST"])
@login_required
def set_approved(candidate_id: int):
    """POST /api/designer/evolution/candidates/<id>/set-approved

    Human approval step (must happen before promote).
    Body: { approved: true }
    """
    from db import db_session
    from foms.persistence.designer.models import DesignerRuleCandidate

    candidate = db_session.get(DesignerRuleCandidate, candidate_id)
    if not candidate:
        return jsonify({"success": False, "error": f"Candidate {candidate_id} not found"}), 404

    body = request.get_json(silent=True) or {}
    approved = body.get("approved", False)
    candidate.status = "approved" if approved else "rejected"
    db_session.commit()

    return jsonify({
        "success": True,
        "data": {"id": candidate.id, "status": candidate.status},
        "error": None,
    })


@evolution_bp.route("/evolution/cluster", methods=["POST"])
@login_required
def run_cluster():
    """POST /api/designer/evolution/cluster — run correction clustering pipeline."""
    from foms.services.designer.correction_clusterer import run_correction_clustering_pipeline
    try:
        created_ids = run_correction_clustering_pipeline()
        return jsonify({"success": True, "data": {"created": len(created_ids), "ids": created_ids}, "error": None})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@evolution_bp.route("/evolution/candidates/<int:candidate_id>/promote", methods=["POST"])
@login_required
def promote(candidate_id: int):
    """POST /api/designer/evolution/candidates/<id>/promote

    Human-gated: requires replay_report + approved status.
    Body: { version_key: str, rules_json: dict }
    """
    from foms.services.designer.evolution import approve_and_promote_candidate

    body = request.get_json(silent=True) or {}
    version_key = body.get("version_key")
    rules_json = body.get("rules_json")
    user_id = getattr(g, "user_id", None)

    if not version_key or not rules_json:
        return jsonify({"success": False, "error": "version_key와 rules_json 필요"}), 400

    try:
        result = approve_and_promote_candidate(
            candidate_id, version_key, rules_json, user_id=user_id,
        )
        return jsonify({"success": True, "data": result, "error": None})
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 422
