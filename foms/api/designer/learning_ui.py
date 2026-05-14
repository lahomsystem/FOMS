"""FOMS Brain Enhancement — Learning UI API.

ProductArchetype + Design Case endpoints for the UI panels.

  GET  /api/designer/archetypes/summary
  POST /api/designer/archetypes/discover
  GET  /api/designer/cases
"""

from __future__ import annotations

import logging

from flask import Blueprint, request, jsonify

from foms.web.auth import login_required

import os
from pathlib import Path
logger = logging.getLogger(__name__)

learning_ui_bp = Blueprint("designer_learning_ui", __name__, url_prefix="/api/designer")


# ── Archetype ──────────────────────────────────────────────

@learning_ui_bp.route("/archetypes/summary", methods=["GET"])
@login_required
def archetype_summary():
    """GET /api/designer/archetypes/summary"""
    try:
        from foms.services.designer.product_archetype_learning import get_archetype_summary
        summary = get_archetype_summary()
        return jsonify({"success": True, "data": summary, "error": None})
    except Exception as exc:
        logger.error("[ARCHETYPE API] summary failed: %s", exc)
        return jsonify({"success": False, "error": str(exc)}), 500


@learning_ui_bp.route("/archetypes/discover", methods=["POST"])
@login_required
def archetype_discover():
    """POST /api/designer/archetypes/discover — run pipeline."""
    try:
        from foms.services.designer.product_archetype_learning import run_archetype_discovery_pipeline
        candidates = run_archetype_discovery_pipeline()
        return jsonify({"success": True, "data": {"candidates": len(candidates), "results": candidates}, "error": None})
    except Exception as exc:
        logger.error("[ARCHETYPE API] discover failed: %s", exc)
        return jsonify({"success": False, "error": str(exc)}), 500


# ── Template Calibration ───────────────────────────────────

@learning_ui_bp.route("/calibration/status", methods=["GET"])
@login_required
def calibration_status():
    """GET /api/designer/calibration/status — fixture coverage stats."""
    try:
        from pathlib import Path
        import json
        manifest_path = Path(__file__).parent.parent.parent.parent / "tests" / "fixtures" / "designer" / "drawings" / "manifest.json"
        if not manifest_path.exists():
            return jsonify({"success": True, "data": {"total": 0, "available": 0, "approved": 0}, "error": None})
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
        fixtures = manifest.get("fixtures", [])
        available = [f for f in fixtures if f.get("file_status") == "available"]
        approved = [f for f in fixtures if f.get("approval_status") == "approved"]
        return jsonify({
            "success": True,
            "data": {
                "total": len(fixtures),
                "available": len(available),
                "approved": len(approved),
                "pending": len(fixtures) - len(available),
            },
            "error": None,
        })
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@learning_ui_bp.route("/calibration/run", methods=["POST"])
@login_required
def run_calibration():
    """POST /api/designer/calibration/run — trigger calibration run (async via RQ if available)."""
    try:
        # Try async via RQ
        try:
            from rq import Queue
            from redis import Redis
            from tools.designer.run_calibration import run_calibration as _run
            redis = Redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379"))
            q = Queue("default", connection=redis)
            job = q.enqueue(_run, job_timeout=300)
            return jsonify({"success": True, "data": {"mode": "async", "job_id": job.id}, "error": None})
        except Exception:
            # Fallback: dry-run summary only
            from tools.designer.run_calibration import run_calibration as _run
            import sys; sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
            result = _run(dry_run=True)
            return jsonify({"success": True, "data": {"mode": "dry_run", "result": result}, "error": None})
    except Exception as exc:
        logger.error("[CALIB API] %s", exc)
        return jsonify({"success": False, "error": str(exc)}), 500


# ── Design Cases ───────────────────────────────────────────

@learning_ui_bp.route("/cases", methods=["GET"])
@login_required
def list_design_cases():
    """GET /api/designer/cases?furniture_type=&width_mm_min=&width_mm_max=&limit="""
    furniture_type = request.args.get("furniture_type") or None
    width_min = request.args.get("width_mm_min", type=int)
    width_max = request.args.get("width_mm_max", type=int)
    limit = min(int(request.args.get("limit", 20)), 50)

    try:
        from foms.services.designer.design_case_memory import list_design_cases
        cases = list_design_cases(
            furniture_type=furniture_type,
            width_mm_min=width_min,
            width_mm_max=width_max,
            limit=limit,
        )
        # Strip heavy payloads for list view
        slim = []
        for c in cases:
            slim.append({
                "id": c.get("id"),
                "furniture_type": c.get("furniture_type"),
                "product_name": c.get("product_name"),
                "width_mm": c.get("width_mm"),
                "height_mm": c.get("height_mm"),
                "depth_mm": c.get("depth_mm"),
                "module_count": c.get("module_count"),
                "tags": c.get("tags", []),
                "approved_at": c.get("approved_at"),
            })
        return jsonify({"success": True, "data": {"cases": slim, "total": len(slim)}, "error": None})
    except Exception as exc:
        logger.warning("[CASES API] list failed: %s", exc)
        return jsonify({"success": True, "data": {"cases": [], "total": 0}, "error": None})
