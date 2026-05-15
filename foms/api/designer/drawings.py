"""FOMS Brain PG-R1/R2/B3/B7/B8 — Drawing Upload, Fixture, Candidate & Correction API.

Endpoints (Upload pipeline — R1/R2):
  POST /api/designer/drawings/upload-and-extract
       Full intake pipeline: artifact -> classify -> route -> Gemini -> persist extraction+candidate -> ui_state

Endpoints (Corpus fixtures — B3):
  GET  /api/designer/drawings/fixtures
  POST /api/designer/drawings/fixtures/<id>/save-draft
  POST /api/designer/drawings/fixtures/<id>/approve
  GET  /api/designer/drawings/fixtures/<id>/expected

Endpoints (Candidate & Correction — B7/B8):
  POST /api/designer/drawings/candidates/build
  POST /api/designer/drawings/candidates/<id>/correct
  POST /api/designer/drawings/candidates/<id>/approve-and-save

Learning:
  POST /api/designer/drawings/save-learning-sample

Async jobs:
  GET  /api/designer/drawings/jobs/<id>/status

Contract:
- upload-and-extract uses drawing_intake_pipeline.run_intake_pipeline() — no direct Gemini calls.
- GEMINI_API_KEY missing → 503. No silent fallback to fake provider.
- CorrectionDelta records all user corrections with before/after/source.
- Candidate validator must pass before approve-and-save.
- approve-and-save creates project version AND DesignerDesignCase.
- save-learning-sample never sets candidate_rule_hint (prevents learning pollution).
- PII redaction happens inside the pipeline (text output only; image bytes have no OCR).
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
# Async job status (legacy RQ path — kept for compatibility)
# ──────────────────────────────────────────────────────────

@drawings_bp.route("/jobs/<job_id>/status", methods=["GET"])
@login_required
def job_status(job_id: str):
    """GET /api/designer/drawings/jobs/<id>/status — poll async extraction job."""
    try:
        from rq.job import Job
        from redis import Redis
        redis = Redis.from_url(os.environ.get("REDIS_URL", ""), socket_connect_timeout=1)
        job = Job.fetch(job_id, connection=redis)
        result = None
        if job.is_finished:
            result = job.result
        return jsonify({
            "success": True,
            "data": {
                "job_id": job_id,
                "status": job.get_status(),
                "result": result,
            },
            "error": None,
        })
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 404


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
# POST /api/designer/drawings/upload-and-extract  (R1/R2 SSOT)
# ──────────────────────────────────────────────────────────

@drawings_bp.route("/upload-and-extract", methods=["POST"])
@login_required
def upload_and_extract():
    """도면 파일 업로드 + 전체 intake pipeline 실행.

    Pipeline: artifact persist -> PII policy -> template classify ->
              model route -> Gemini extract -> text PII redact ->
              extraction persist -> candidate build -> candidate persist -> ui_state

    Multipart form fields:
      file:       도면 이미지/PDF 파일
      fixture_id: manifest fixture ID (optional)

    Returns:
      { success, data: {
          artifact_id, extraction_id, candidate_id, candidate_db_id,
          extraction, candidate, metrics, routing, redaction_report,
          ui_state, fixture_id, filename
        }, error }
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

    mime_map = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".pdf": "application/pdf",
        ".webp": "image/webp",
    }
    mime_type = mime_map.get(suffix, "image/jpeg")
    image_bytes = f.read()

    try:
        from foms.services.designer.drawing_intake_pipeline import run_intake_pipeline
        from foms.services.designer.gemini_provider import GeminiAPIKeyMissing, GeminiProviderError

        result = run_intake_pipeline(
            image_bytes=image_bytes,
            filename=f.filename,
            mime_type=mime_type,
            user_id=getattr(g, "user_id", None),
            project_id=None,
        )

    except GeminiAPIKeyMissing as exc:
        return jsonify({"success": False, "error": str(exc), "code": "GEMINI_KEY_MISSING"}), 503
    except GeminiProviderError as exc:
        logger.error("[UPLOAD] Gemini provider error: %s", exc)
        return jsonify({"success": False, "error": f"Gemini 추출 실패: {exc}"}), 500
    except Exception as exc:
        logger.exception("[UPLOAD] pipeline error: %s", exc)
        return jsonify({"success": False, "error": f"업로드 처리 실패: {exc}"}), 500

    logger.info(
        "[UPLOAD] fixture=%s artifact=%d extraction=%d candidate_db=%d "
        "type=%s can_preview_3d=%s cost=$%.5f",
        fixture_id or "none",
        result.artifact_id, result.extraction_id, result.candidate_db_id,
        result.extraction.get("furniture_type", "?"),
        result.ui_state.get("can_preview_3d"),
        result.metrics.get("cost_usd", 0),
    )

    response_data = result.to_api_response()
    response_data["fixture_id"] = fixture_id or None
    response_data["filename"] = f.filename

    return jsonify({"success": True, "data": response_data, "error": None})


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
    """Gemini 추출 결과를 expected JSON 초안으로 저장."""
    fixture = _get_fixture(fixture_id)
    if not fixture:
        return jsonify({"success": False, "error": f"Fixture '{fixture_id}' not found"}), 404

    body = request.get_json(silent=True) or {}
    extraction = body.get("extraction", {})

    if not extraction:
        return jsonify({"success": False, "error": "extraction 데이터가 없습니다."}), 400

    from datetime import datetime, timezone
    expected_json = {
        "drawing_id": fixture_id,
        "page_no": extraction.get("drawing_meta", {}).get("page_number") or 1,
        "approval_status": "draft",
        "approved_by": None,
        "approved_at": None,
        "_ai_draft_model": body.get("metrics", {}).get("model", "gemini-3.1-pro-preview"),
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

    ej_path = ROOT / fixture.get("expected_json_path", "")
    ej_path.parent.mkdir(parents=True, exist_ok=True)
    with open(ej_path, "w", encoding="utf-8") as f:
        json.dump(expected_json, f, ensure_ascii=False, indent=2)

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
    """Expected JSON 초안을 사용자가 승인 (corpus fixture 전용)."""
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

    body = request.get_json(silent=True) or {}
    corrections = body.get("corrections", {})
    if corrections:
        for key, value in corrections.items():
            ej[key] = value

    from datetime import datetime, timezone
    user_id = getattr(g, "user_id", None)
    ej["approval_status"] = "approved"
    ej["approved_by"] = str(user_id) if user_id else "user"
    ej["approved_at"] = datetime.now(timezone.utc).isoformat()

    with open(ej_path, "w", encoding="utf-8") as f:
        json.dump(ej, f, ensure_ascii=False, indent=2)

    data = _load_manifest()
    approved_count = 0
    for fix in data["fixtures"]:
        if fix["id"] == fixture_id:
            fix["approval_status"] = "approved"
        if fix.get("approval_status") == "approved":
            approved_count += 1

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


# ──────────────────────────────────────────────────────────
# POST /api/designer/drawings/save-learning-sample
# ──────────────────────────────────────────────────────────

@drawings_bp.route("/save-learning-sample", methods=["POST"])
@login_required
def save_learning_sample():
    """POST /api/designer/drawings/save-learning-sample

    학습 샘플 저장. raw learning sample이므로 candidate_rule_hint를 설정하지 않는다.
    hint 없이 저장해야 correction_clusterer가 이 샘플을 rule candidate로 오염하지 않는다.

    Body:
      { extraction: {...}, metrics: {...}, filename: "..." }
    """
    body = request.get_json(silent=True) or {}
    extraction = body.get("extraction", {})
    metrics = body.get("metrics", {})
    filename = body.get("filename", "unknown")

    if not extraction:
        return jsonify({"success": False, "error": "extraction 데이터가 없습니다."}), 400

    notes = []

    # PII redaction before DB storage
    try:
        from foms.services.designer.pii_redactor import RedactionContext
        ctx = RedactionContext()
        redacted_extraction = ctx.redact_extraction(extraction)
    except Exception as exc:
        logger.warning("[SAVE-LEARNING] PII redaction failed: %s", exc)
        redacted_extraction = extraction

    # DB 저장 — raw_learning_sample 소스, hint 없음
    saved_id = None
    try:
        from db import db_session
        from foms.persistence.designer.models import DesignerCorrection
        corr = DesignerCorrection(
            before_json={},
            after_json={
                "source": "raw_learning_sample",
                "filename": filename,
                "furniture_type": extraction.get("furniture_type", "unknown"),
                # candidate_rule_hint intentionally absent — prevents rule clustering pollution
                "extraction_confidence": extraction.get("confidence", 0.0),
                "unresolved_count": len(extraction.get("unresolved_fields") or []),
                "metrics": metrics,
                "redacted_extraction": redacted_extraction,
            },
            reason_text=f"학습 샘플: {filename}",
            created_by_user_id=getattr(g, "user_id", None),
        )
        db_session.add(corr)
        db_session.commit()
        db_session.refresh(corr)
        saved_id = corr.id
    except Exception as exc:
        logger.warning("[SAVE-LEARNING] DB save failed (non-fatal): %s", exc)
        notes.append(f"DB 저장 실패: {exc}")

    logger.info(
        "[SAVE-LEARNING] filename=%s type=%s confidence=%.2f saved_id=%s",
        filename,
        extraction.get("furniture_type", "?"),
        extraction.get("confidence", 0.0),
        saved_id,
    )

    return jsonify({
        "success": True,
        "data": {
            "saved": True,
            "learning_record_id": saved_id,
            "notes": notes,
        },
        "error": None,
    })


# ──────────────────────────────────────────────────────────
# POST /api/designer/drawings/candidates/build
# ──────────────────────────────────────────────────────────

@drawings_bp.route("/candidates/build", methods=["POST"])
@login_required
def build_candidate_route():
    """POST /api/designer/drawings/candidates/build

    추출 결과로부터 MappedCandidate를 빌드하고 DB에 저장한다.
    upload-and-extract 이후 수동으로 candidate를 (재)빌드할 때 사용.

    Body: { extraction: {...}, source_extraction_id: int | null }
    """
    body = request.get_json(silent=True) or {}
    extraction = body.get("extraction")
    if not extraction:
        return jsonify({"success": False, "error": "extraction 필드가 없습니다."}), 400

    source_id = body.get("source_extraction_id")

    try:
        from foms.services.designer.ontology_mapper import build_candidate
        from foms.services.designer.drawing_intake_pipeline import compute_ui_state
        candidate = build_candidate(extraction, source_extraction_id=source_id)
        ui_state = compute_ui_state(
            furniture_type=candidate.furniture_type,
            unresolved_fields=candidate.unresolved_fields,
            validation_result=candidate.validation_result,
        )
    except Exception as exc:
        logger.error("[CANDIDATE BUILD] error: %s", exc)
        return jsonify({"success": False, "error": str(exc)}), 500

    # Persist to DB if source_extraction_id provided
    candidate_db_id = None
    if source_id:
        try:
            from db import db_session
            from foms.persistence.designer.models import DesignerExtractionCandidate
            row = DesignerExtractionCandidate(
                extraction_id=source_id,
                furniture_type=candidate.furniture_type,
                extracted_params_json=candidate.factory_params,
                unresolved_fields_json=candidate.unresolved_fields,
                confidence=candidate.confidence,
                approved=False,
                status="pending_review",
                blocking_reasons_json=ui_state["blocking_reasons"],
            )
            db_session.add(row)
            db_session.commit()
            db_session.refresh(row)
            candidate_db_id = row.id
        except Exception as exc:
            logger.warning("[CANDIDATE BUILD] DB persist failed: %s", exc)

    return jsonify({
        "success": True,
        "data": {
            "candidate": candidate.to_dict(),
            "candidate_db_id": candidate_db_id,
            "ui_state": ui_state,
        },
        "error": None,
    })


# ──────────────────────────────────────────────────────────
# POST /api/designer/drawings/candidates/<id>/correct
# ──────────────────────────────────────────────────────────

@drawings_bp.route("/candidates/<candidate_id>/correct", methods=["POST"])
@login_required
def correct_candidate(candidate_id: str):
    """POST /api/designer/drawings/candidates/<id>/correct

    사용자 수정을 CorrectionDelta로 저장하고 candidate를 rebuild한다.
    candidate_id는 DesignerExtractionCandidate.id (DB integer).
    Project version은 생성하지 않는다.

    Body:
      { corrections: {field: value, ...}, reason: "string" }
    """
    # DB 조회 우선
    candidate_row = _get_candidate_row(candidate_id)
    if candidate_row is None:
        return jsonify({"success": False, "error": f"Candidate {candidate_id} not found"}), 404

    body = request.get_json(silent=True) or {}
    corrections = body.get("corrections", {})
    reason = body.get("reason", "user_manual_edit")

    if not corrections:
        return jsonify({"success": False, "error": "corrections 필드가 없습니다."}), 400

    before_params = dict(candidate_row.extracted_params_json or {})
    before_unresolved = list(candidate_row.unresolved_fields_json or [])

    # Apply corrections to factory_params
    updated_params = dict(before_params)
    updated_unresolved = list(before_unresolved)
    for field_name, value in corrections.items():
        updated_params[field_name] = value
        if field_name in updated_unresolved:
            updated_unresolved.remove(field_name)

    # Rebuild validation
    validation_result = None
    if not updated_unresolved:
        try:
            from foms.services.designer.factory_registry import validate_params
            errors = validate_params(candidate_row.furniture_type, updated_params)
            validation_result = {"valid": len(errors) == 0, "errors": errors, "warnings": []}
        except Exception as exc:
            logger.warning("[CORRECT] validator failed: %s", exc)
            validation_result = {"valid": False, "errors": [str(exc)], "warnings": []}

    # Recompute ui_state
    from foms.services.designer.drawing_intake_pipeline import compute_ui_state
    ui_state = compute_ui_state(
        furniture_type=candidate_row.furniture_type,
        unresolved_fields=updated_unresolved,
        validation_result=validation_result,
    )

    # Persist correction delta
    correction_id = None
    try:
        from db import db_session
        from foms.persistence.designer.models import DesignerCorrection
        corr = DesignerCorrection(
            before_json={
                "factory_params": before_params,
                "unresolved_fields": before_unresolved,
            },
            after_json={
                "factory_params": updated_params,
                "unresolved_fields": updated_unresolved,
                "source": "user_manual_edit",
            },
            reason_text=reason,
            created_by_user_id=getattr(g, "user_id", None),
        )
        db_session.add(corr)

        # Update candidate row
        import copy
        from sqlalchemy.orm.attributes import flag_modified
        candidate_row.extracted_params_json = copy.deepcopy(updated_params)
        candidate_row.unresolved_fields_json = updated_unresolved
        candidate_row.status = "corrected"
        candidate_row.blocking_reasons_json = ui_state["blocking_reasons"]
        flag_modified(candidate_row, "extracted_params_json")
        flag_modified(candidate_row, "unresolved_fields_json")
        flag_modified(candidate_row, "blocking_reasons_json")

        db_session.commit()
        db_session.refresh(corr)
        correction_id = corr.id
    except Exception as exc:
        logger.warning("[CORRECT] DB write failed (non-fatal): %s", exc)

    candidate_dict = {
        "candidate_id": str(candidate_row.id),
        "furniture_type": candidate_row.furniture_type,
        "factory_params": updated_params,
        "unresolved_fields": updated_unresolved,
        "approved": candidate_row.approved,
        "status": "corrected",
        "validation_result": validation_result,
        "can_apply": False,
    }

    return jsonify({
        "success": True,
        "data": {
            "candidate": candidate_dict,
            "correction_id": correction_id,
            "ui_state": ui_state,
        },
        "error": None,
    })


# ──────────────────────────────────────────────────────────
# POST /api/designer/drawings/candidates/<id>/approve-and-save
# ──────────────────────────────────────────────────────────

@drawings_bp.route("/candidates/<candidate_id>/approve-and-save", methods=["POST"])
@login_required
def approve_and_save_candidate(candidate_id: str):
    """POST /api/designer/drawings/candidates/<id>/approve-and-save

    검증 통과 후 project version 생성 + DesignerDesignCase 저장.
    candidate_id는 DesignerExtractionCandidate.id (DB integer).

    B2 계약:
    - legacy candidate → HTTP 422 + legacy_candidate_requires_reextract
    - 이미 approve/promoted → HTTP 409
    - blocking_reasons 있으면 → HTTP 422 + approve_blocked
    - design_graph_candidate_json 우선 사용, fallback factory_params

    Body: { project_id: int }
    """
    from db import db_session
    from foms.persistence.designer.models import DesignerExtractionCandidate

    # Lock candidate row for concurrent approve prevention
    try:
        row_id = int(candidate_id)
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": f"Invalid candidate_id: {candidate_id}"}), 400

    candidate_row = (
        db_session.query(DesignerExtractionCandidate)
        .filter(DesignerExtractionCandidate.id == row_id)
        .with_for_update()
        .first()
    )
    if candidate_row is None:
        return jsonify({"success": False, "error": f"Candidate {candidate_id} not found"}), 404

    # Gate 0: already approved/promoted → 409
    if candidate_row.status in ("approved", "promoted_to_project_version"):
        return jsonify({
            "success": False,
            "error": "approve_blocked",
            "data": {"reasons": [f"already_{candidate_row.status}"]},
        }), 409

    # Gate 1: legacy candidate → 422
    if candidate_row.is_legacy():
        return jsonify({
            "success": False,
            "error": "approve_blocked",
            "data": {"reasons": ["legacy_candidate_requires_reextract"]},
        }), 422

    # Gate 2: blocking reasons → 422
    blocking = list(candidate_row.blocking_reasons_json or [])
    if blocking:
        return jsonify({
            "success": False,
            "error": "approve_blocked",
            "data": {"reasons": blocking},
        }), 422

    # Gate 3: no unresolved fields in legacy path
    unresolved = list(candidate_row.unresolved_fields_json or [])
    if unresolved:
        return jsonify({
            "success": False,
            "error": "approve_blocked",
            "data": {"reasons": [f"unresolved_field:{u}" for u in unresolved]},
        }), 422

    body = request.get_json(silent=True) or {}
    project_id = body.get("project_id")
    if not project_id:
        return jsonify({"success": False, "error": "project_id가 필요합니다."}), 400

    furniture_type = candidate_row.furniture_type

    # B2: Prefer design_graph_candidate_json, fallback to factory_params
    design_dict: dict | None = None

    if candidate_row.design_graph_candidate_json:
        design_dict = dict(candidate_row.design_graph_candidate_json)
        logger.info("[APPROVE-SAVE] using graph-first design_graph_candidate_json candidate=%s", candidate_id)
    else:
        # Legacy fallback: factory_params path (for backwards compat during migration window)
        factory_params = dict(candidate_row.extracted_params_json or {})
        try:
            from foms.services.designer.factory_registry import create_design
            design_graph = create_design(furniture_type, factory_params)
            design_dict = design_graph if isinstance(design_graph, dict) else design_graph.to_dict()
            logger.info("[APPROVE-SAVE] using factory fallback candidate=%s", candidate_id)
        except Exception as exc:
            logger.error("[APPROVE-SAVE] factory create failed: %s", exc)
            return jsonify({"success": False, "error": f"설계 생성 실패: {exc}"}), 500

    # Gate 4: no-op / empty graph rejection
    if not design_dict:
        return jsonify({
            "success": False,
            "error": "approve_blocked",
            "data": {"reasons": ["empty_design_graph"]},
        }), 422

    components = design_dict.get("components", [])
    if not components:
        return jsonify({
            "success": False,
            "error": "approve_blocked",
            "data": {"reasons": ["no_components_in_design_graph"]},
        }), 422

    # Gate 5: validator must pass
    try:
        from foms.services.designer.validator import validate_design
        val_result = validate_design(design_dict)
        if val_result.errors:
            reasons = [e.message for e in val_result.errors[:5]]
            return jsonify({
                "success": False,
                "error": "approve_blocked",
                "data": {"reasons": reasons},
            }), 422
    except Exception as exc:
        return jsonify({"success": False, "error": f"검증 실패: {exc}"}), 500

    # Create project version (atomic: check current_version → create → update)
    try:
        from foms.persistence.designer import create_project_version
        version = create_project_version(
            project_id=int(project_id),
            design_json=design_dict,
            user_id=getattr(g, "user_id", None),
        )
    except Exception as exc:
        logger.error("[APPROVE-SAVE] version create failed: %s", exc)
        return jsonify({"success": False, "error": f"버전 저장 실패: {exc}"}), 500

    # Mark candidate approved + create DesignerDesignCase
    design_case_id = None
    try:
        from datetime import datetime, timezone
        user_id = getattr(g, "user_id", None)
        candidate_row.approved = True
        candidate_row.status = "approved"
        candidate_row.approved_by_user_id = user_id
        candidate_row.approved_at = datetime.now(timezone.utc)
        db_session.flush()

        try:
            from foms.services.designer.design_case_memory import save_design_case
            from foms.services.designer.product_archetype_learning import extract_tags_from_case
            from foms.persistence.designer.models import DesignerDrawingExtraction

            extraction_id = candidate_row.extraction_id
            extraction_payload: dict = {}
            if extraction_id:
                extraction_row = db_session.get(DesignerDrawingExtraction, extraction_id)
                if extraction_row is not None:
                    extraction_payload = dict(extraction_row.parsed_json or {})

            design_understanding = extraction_payload.get("design_understanding") or {}
            # B5: store mapping_report alongside design_understanding in internal_structure_json
            internal_structure = {
                "design_understanding": design_understanding,
                "mapping_report": dict(candidate_row.mapping_report_json or {}),
            }
            customer_info = extraction_payload.get("customer_info") or {}
            product_name = customer_info.get("product_name") or extraction_payload.get("product_name")
            learning_tags = extract_tags_from_case({
                "furniture_type": furniture_type,
                "product_name": product_name or "",
                "options_json": {"design_understanding": design_understanding},
                "internal_structure_json": internal_structure,
            })

            case_result = save_design_case(
                project_version_id=version.id,
                furniture_type=furniture_type,
                design_graph=design_dict,
                project_id=int(project_id),
                approved_extraction_id=extraction_id,
                product_name=product_name,
                internal_structure=internal_structure,
                tags=learning_tags,
                source_quality_score=float(candidate_row.confidence or 1.0),
                approval_user_id=user_id,
            )
            design_case_id = case_result.get("id")

            if design_case_id:
                from foms.persistence.designer.models import DesignerDesignCase
                dc = db_session.get(DesignerDesignCase, design_case_id)
                if dc is not None:
                    dc.source_candidate_id = candidate_row.id
        except Exception as exc:
            logger.error("[APPROVE-SAVE] design case creation failed (non-fatal): %s", exc)

        db_session.commit()
    except Exception as exc:
        logger.error("[APPROVE-SAVE] DB update failed: %s", exc)
        return jsonify({"success": False, "error": f"후보 승인 저장 실패: {exc}"}), 500

    logger.info(
        "[APPROVE-SAVE] project_version_id=%d candidate_db=%s design_case_id=%s",
        version.id, candidate_id, design_case_id,
    )

    return jsonify({
        "success": True,
        "data": {
            "project_version_id": version.id,
            "design_case_id": design_case_id,
            "candidate_id": candidate_id,
        },
        "error": None,
    })


# ──────────────────────────────────────────────────────────
# DB lookup helper
# ──────────────────────────────────────────────────────────

def _get_candidate_row(candidate_id: str):
    """Look up DesignerExtractionCandidate by integer id. Returns None if not found."""
    try:
        row_id = int(candidate_id)
    except (ValueError, TypeError):
        return None
    try:
        from db import db_session
        from foms.persistence.designer.models import DesignerExtractionCandidate
        return db_session.get(DesignerExtractionCandidate, row_id)
    except Exception as exc:
        logger.warning("[LOOKUP] candidate %s fetch failed: %s", candidate_id, exc)
        return None
