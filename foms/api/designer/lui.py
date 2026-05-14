"""FOMS Brain Post-V1 — LUI Parser API.

POST /api/designer/lui/parse
  Korean natural language → DesignCommand (preview_only=True)
  Returns clarification state when ambiguous.

PV2-B1: parser NEVER modifies design_json directly.
"""

from __future__ import annotations

from flask import Blueprint, request, jsonify, g

from foms.web.auth import login_required
from foms.services.designer.lui_parser import parse_lui, ParsedCommand, ClarificationNeeded

lui_bp = Blueprint("designer_lui", __name__, url_prefix="/api/designer")


@lui_bp.route("/lui/parse", methods=["POST"])
@login_required
def parse_route():
    """POST /api/designer/lui/parse

    Request body:
      {
        "text": "왼쪽 선반 50mm 위로",
        "selected_component_id": "uuid-optional",
        "design_context": { ...DesignGraph dict... }   # optional
      }

    Returns:
      {
        "success": true,
        "data": {
          "status": "resolved" | "clarification_needed",
          "command": { ...DesignCommand... },       # only when resolved
          "clarification_reason": "...",            # only when needed
          "clarification_candidates": [...],
          "confidence": 0.0–1.0,
          "matched_rule": "..."
        },
        "error": null
      }
    """
    body = request.get_json(silent=True) or {}
    text = str(body.get("text", "")).strip()
    selected_id = body.get("selected_component_id") or None
    design_context = body.get("design_context") or None

    if not text:
        return jsonify({"success": False, "error": "text 필드가 비어 있습니다."}), 400

    result = parse_lui(text, selected_component_id=selected_id, design_context=design_context)

    if isinstance(result, ParsedCommand):
        return jsonify({
            "success": True,
            "data": {
                "status": "resolved",
                "command": result.command,
                "confidence": result.confidence,
                "matched_rule": result.matched_rule,
                "clarification_reason": None,
                "clarification_candidates": [],
            },
            "error": None,
        })

    # ClarificationNeeded — apply must be refused
    return jsonify({
        "success": True,
        "data": {
            "status": "clarification_needed",
            "command": None,
            "confidence": 0.0,
            "matched_rule": None,
            "clarification_reason": result.reason,
            "clarification_candidates": result.candidates,
        },
        "error": None,
    })
