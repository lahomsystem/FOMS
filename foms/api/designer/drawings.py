"""FOMS Brain PG-B2/B3 — Drawing Upload & Fixture Registration API.

Endpoints:
  POST /api/designer/drawings/upload-and-extract
       도면 파일을 업로드하고 Gemini로 추출한다.
  GET  /api/designer/drawings/fixtures
       fixture manifest 현황을 반환한다.
  POST /api/designer/drawings/fixtures/<fixture_id>/save-draft
       Gemini 추출 결과를 expected JSON 초안으로 저장한다.
  POST /api/designer/drawings/fixtures/<fixture_id>/approve
       expected JSON 초안을 사용자가 승인한다.
  GET  /api/designer/drawings/fixtures/<fixture_id>/expected
       기존 expected JSON을 반환한다.

Contract:
- 파일은 서버 임시 경로에 저장 후 Gemini 전송, 완료 후 삭제 or R2 업로드.
- approved=false 상태의 데이터는 절대 project version으로 저장되지 않는다.
- PII(고객명/전화/주소)는 expected JSON에만 저장, Gemini 전송 시 redaction 필요 (PG-B3A).
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

from flask import Blueprint, request, jsonify, g

from foms.web.auth import login_required

logger = logging.getLogger(__name__)

drawings_bp = Blueprint("designer_drawings", __name__, url_prefix="/api/designer/drawings")

ROOT = Path(__file__).parent.parent.parent.parent
MANIFEST_PATH = ROOT / "tests" / "fixtures" / "designer" / "drawings" / "manifest.json"
EXPECTED_DIR = MANIFEST_PATH.parent / "expected_extractions"

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf", ".webp"}
MAX_FILE_SIZE_MB = 20


# ──────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────

def _load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        return {"fixtures": [], "corpus_plan": {}}
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save_manifest(data: dict) -> None:
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _get_fixture(fixture_id: str) -> dict | None:
    data = _load_manifest()
    return next((f for f in data.get("fixtures", []) if f["id"] == fixture_id), None)


def _gemini_available() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


# ──────────────────────────────────────────────────────────
# POST /api/designer/drawings/upload-and-extract
# ──────────────────────────────────────────────────────────

@drawings_bp.route("/upload-and-extract", methods=["POST"])
@login_required
def upload_and_extract():
    """도면 파일 업로드 + Gemini 추출.

    Multipart form fields:
      file:       도면 이미지/PDF 파일
      fixture_id: manifest fixture ID (optional, for corpus registration)

    Returns:
      { success, data: { extraction, fixture_id, metrics }, error }
    """
    if "file" not in request.files:
        return jsonify({"success": False, "error": "파일이 없습니다. 'file' 필드를 포함하세요."}), 400

    f = request.files["file"]
    fixture_id = request.form.get("fixture_id", "").strip()

    if not f.filename:
        return jsonify({"success": False, "error": "파일명이 없습니다."}), 400

    suffix = Path(f.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        return jsonify({
            "success": False,
            "error": f"지원하지 않는 파일 형식입니다. 지원: {', '.join(ALLOWED_EXTENSIONS)}"
        }), 400

    # Check file size
    f.seek(0, 2)
    size_mb = f.tell() / (1024 * 1024)
    f.seek(0)
    if size_mb > MAX_FILE_SIZE_MB:
        return jsonify({
            "success": False,
            "error": f"파일 크기가 너무 큽니다. 최대 {MAX_FILE_SIZE_MB}MB."
        }), 400

    if not _gemini_available():
        return jsonify({
            "success": False,
            "error": "GEMINI_API_KEY가 설정되지 않았습니다. Railway 환경변수를 확인하세요.",
            "code": "GEMINI_KEY_MISSING"
        }), 503

    # Save to temp file
    mime_map = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".pdf": "application/pdf",
        ".webp": "image/webp",
    }
    mime_type = mime_map.get(suffix, "image/jpeg")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        f.save(tmp.name)
        tmp_path = tmp.name

    try:
        from foms.services.designer.gemini_provider import (
            extract_from_image_path,
            GeminiProviderError,
            GeminiAPIKeyMissing,
        )
        raw = extract_from_image_path(tmp_path)
    except GeminiAPIKeyMissing as exc:
        return jsonify({"success": False, "error": str(exc), "code": "GEMINI_KEY_MISSING"}), 503
    except Exception as exc:
        logger.error("[DRAWING EXTRACT] error: %s", exc)
        return jsonify({"success": False, "error": f"Gemini 추출 실패: {exc}"}), 500
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    # Build extraction summary for UI
    metrics = raw.pop("_metrics", {})
    extracted_params = raw.get("extracted_params", {})
    parts_table = raw.get("parts_table") or extracted_params.pop("_parts_table", []) or []
    customer_info = raw.get("customer_info") or extracted_params.pop("_customer_info", {}) or {}
    drawing_meta = raw.get("drawing_meta") or extracted_params.pop("_drawing_meta", {}) or {}

    extraction = {
        "furniture_type": raw.get("furniture_type", "wardrobe"),
        "site_size": {
            "width_mm": extracted_params.get("width"),
            "depth_mm": extracted_params.get("depth"),
            "height_mm": extracted_params.get("height"),
        },
        "module_widths_mm": extracted_params.get("module_widths") or [],
        "parts_table": parts_table,
        "customer_info": customer_info,
        "drawing_meta": drawing_meta,
        "unresolved_fields": raw.get("unresolved_fields", []),
        "confidence": raw.get("confidence", 0.0),
    }

    logger.info(
        "[DRAWING EXTRACT] fixture=%s type=%s confidence=%.2f cost=$%.5f",
        fixture_id or "none",
        extraction["furniture_type"],
        extraction["confidence"],
        metrics.get("cost_usd", 0),
    )

    return jsonify({
        "success": True,
        "data": {
            "extraction": extraction,
            "fixture_id": fixture_id or None,
            "metrics": metrics,
            "filename": f.filename,
        },
        "error": None,
    })


# ──────────────────────────────────────────────────────────
# GET /api/designer/drawings/fixtures
# ──────────────────────────────────────────────────────────

@drawings_bp.route("/fixtures", methods=["GET"])
@login_required
def list_fixtures():
    """fixture manifest 현황 반환."""
    data = _load_manifest()
    fixtures = data.get("fixtures", [])
    summary = {
        "total": len(fixtures),
        "pending": sum(1 for f in fixtures if f.get("file_status") == "pending"),
        "available": sum(1 for f in fixtures if f.get("file_status") == "available"),
        "approved": sum(1 for f in fixtures if f.get("approval_status") == "approved"),
    }
    return jsonify({"success": True, "data": {"fixtures": fixtures, "summary": summary}, "error": None})


# ──────────────────────────────────────────────────────────
# GET /api/designer/drawings/fixtures/<id>/expected
# ──────────────────────────────────────────────────────────

@drawings_bp.route("/fixtures/<fixture_id>/expected", methods=["GET"])
@login_required
def get_expected_json(fixture_id: str):
    """기존 expected JSON 반환."""
    fixture = _get_fixture(fixture_id)
    if not fixture:
        return jsonify({"success": False, "error": f"Fixture '{fixture_id}' not found"}), 404

    ej_path = ROOT / fixture.get("expected_json_path", "")
    if not ej_path.exists():
        return jsonify({"success": True, "data": None, "error": None})

    with open(ej_path, encoding="utf-8") as f:
        ej = json.load(f)
    return jsonify({"success": True, "data": ej, "error": None})


# ──────────────────────────────────────────────────────────
# POST /api/designer/drawings/fixtures/<id>/save-draft
# ──────────────────────────────────────────────────────────

@drawings_bp.route("/fixtures/<fixture_id>/save-draft", methods=["POST"])
@login_required
def save_draft(fixture_id: str):
    """Gemini 추출 결과를 expected JSON 초안으로 저장.

    Body: { extraction: {...} }
    """
    fixture = _get_fixture(fixture_id)
    if not fixture:
        return jsonify({"success": False, "error": f"Fixture '{fixture_id}' not found"}), 404

    body = request.get_json(silent=True) or {}
    extraction = body.get("extraction", {})

    if not extraction:
        return jsonify({"success": False, "error": "extraction 데이터가 없습니다."}), 400

    # Build expected JSON
    from datetime import datetime, timezone
    expected_json = {
        "drawing_id": fixture_id,
        "page_no": extraction.get("drawing_meta", {}).get("page_number") or 1,
        "approval_status": "draft",
        "approved_by": None,
        "approved_at": None,
        "_ai_draft_model": body.get("metrics", {}).get("model", "gemini-2.5-flash"),
        "_ai_draft_latency_ms": body.get("metrics", {}).get("latency_ms", 0),
        "_ai_draft_cost_usd": body.get("metrics", {}).get("cost_usd", 0.0),
        "customer_name": extraction.get("customer_info", {}).get("customer_name"),
        "product_name": extraction.get("customer_info", {}).get("product_name"),
        "site_size": extraction.get("site_size", {}),
        "furniture_type": extraction.get("furniture_type", "wardrobe"),
        "module_widths_mm": extraction.get("module_widths_mm", []),
        "parts_table": extraction.get("parts_table", []),
        "dimension_candidates": _build_dimension_candidates(extraction),
        "views": [extraction.get("drawing_meta", {}).get("view_type") or "front"],
        "drawing_style": extraction.get("drawing_meta", {}).get("drawing_style") or "technical",
        "notes": "",
        "color": extraction.get("customer_info", {}).get("color"),
        "hardware": None,
        "unresolved_fields": extraction.get("unresolved_fields", []),
        "confidence": extraction.get("confidence", 0.0),
        "draft_saved_at": datetime.now(timezone.utc).isoformat(),
    }

    # Save expected JSON
    ej_path = ROOT / fixture.get("expected_json_path", "")
    ej_path.parent.mkdir(parents=True, exist_ok=True)
    with open(ej_path, "w", encoding="utf-8") as f:
        json.dump(expected_json, f, ensure_ascii=False, indent=2)

    # Update manifest: mark as pending_approval if was draft
    data = _load_manifest()
    for fix in data["fixtures"]:
        if fix["id"] == fixture_id:
            if fix.get("approval_status") == "draft":
                fix["approval_status"] = "pending_approval"
            break
    _save_manifest(data)

    return jsonify({
        "success": True,
        "data": {"expected_json": expected_json, "path": str(ej_path)},
        "error": None,
    })


def _build_dimension_candidates(extraction: dict) -> list:
    ss = extraction.get("site_size", {})
    candidates = []
    for axis, field in [("width", "width_mm"), ("height", "height_mm"), ("depth", "depth_mm")]:
        val = ss.get(field)
        if val:
            candidates.append({"value_mm": val, "axis": axis, "view": "front", "source": "drawing"})
    return candidates


# ──────────────────────────────────────────────────────────
# POST /api/designer/drawings/fixtures/<id>/approve
# ──────────────────────────────────────────────────────────

@drawings_bp.route("/fixtures/<fixture_id>/approve", methods=["POST"])
@login_required
def approve_fixture(fixture_id: str):
    """Expected JSON 초안을 사용자가 승인.

    Body: { corrections: {...} }  (optional — user edits applied before approval)
    """
    fixture = _get_fixture(fixture_id)
    if not fixture:
        return jsonify({"success": False, "error": f"Fixture '{fixture_id}' not found"}), 404

    ej_path = ROOT / fixture.get("expected_json_path", "")
    if not ej_path.exists():
        return jsonify({
            "success": False,
            "error": "Expected JSON 초안이 없습니다. 먼저 도면을 업로드하고 추출을 완료하세요."
        }), 422

    with open(ej_path, encoding="utf-8") as f:
        ej = json.load(f)

    # Apply user corrections if provided
    body = request.get_json(silent=True) or {}
    corrections = body.get("corrections", {})
    if corrections:
        for key, value in corrections.items():
            ej[key] = value

    # Mark as approved
    from datetime import datetime, timezone
    user_id = getattr(g, "user_id", None)
    ej["approval_status"] = "approved"
    ej["approved_by"] = str(user_id) if user_id else "user"
    ej["approved_at"] = datetime.now(timezone.utc).isoformat()

    with open(ej_path, "w", encoding="utf-8") as f:
        json.dump(ej, f, ensure_ascii=False, indent=2)

    # Update manifest
    data = _load_manifest()
    approved_count = 0
    for fix in data["fixtures"]:
        if fix["id"] == fixture_id:
            fix["approval_status"] = "approved"
        if fix.get("approval_status") == "approved":
            approved_count += 1

    # Update corpus plan approved counts
    if "corpus_plan" in data:
        for v_key in ["v0", "v1"]:
            if v_key in data["corpus_plan"]:
                data["corpus_plan"][v_key]["approved"] = approved_count

    _save_manifest(data)

    logger.info("[FIXTURE APPROVE] fixture=%s total_approved=%d", fixture_id, approved_count)

    return jsonify({
        "success": True,
        "data": {
            "fixture_id": fixture_id,
            "approval_status": "approved",
            "total_approved": approved_count,
            "expected_json": ej,
        },
        "error": None,
    })
