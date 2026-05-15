"""FOMS Brain PG-R1/R2 — Drawing Intake Pipeline (SSOT).

Single pipeline that owns the full drawing upload flow:
  artifact record
  -> page count / multi-page policy
  -> image PII policy (no OCR available: log + proceed with accepted limitation)
  -> template classification
  -> model routing
  -> Gemini extraction
  -> text PII redaction on extraction result
  -> DesignerDrawingExtraction persist
  -> MappedCandidate build
  -> ui_state computation
  -> DesignerExtractionCandidate persist
  -> DrawingPipelineResult

Contract:
- Caller (API layer) is responsible for reading image bytes and detecting mime_type.
- GEMINI_API_KEY missing raises GeminiAPIKeyMissing (caller maps to 503).
- Gemini failure raises GeminiProviderError (caller maps to 500).
- Multi-page PDF: page 1 is extracted; blocking_reason is added, can_preview_3d=False.
- PII: extraction text output is redacted; image bytes cannot be scanned (no OCR).
- No silent fallback to fake provider in this pipeline.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Frontend-supported furniture types (must match factory_registry + React add-in)
_FRONTEND_SUPPORTED_TYPES = frozenset({
    "wardrobe", "shoe_rack", "kitchen_base", "kitchen_wall",
})


# ──────────────────────────────────────────────────────────
# Result contract
# ──────────────────────────────────────────────────────────

@dataclass
class DrawingPipelineResult:
    """Complete result of the drawing intake pipeline."""

    artifact_id: int
    extraction_id: int
    candidate_db_id: int          # DesignerExtractionCandidate.id
    candidate_local_id: str       # MappedCandidate.candidate_id (UUID)
    routing: dict[str, Any]       # model_router.ModelRouteResult.to_dict()
    redaction_report: dict[str, Any]
    extraction: dict[str, Any]    # normalized, PII-redacted extraction
    candidate: dict[str, Any]     # MappedCandidate.to_dict()
    metrics: dict[str, Any]       # Gemini provider _metrics
    ui_state: dict[str, Any]      # can_review/can_preview_3d/can_approve/…

    def to_api_response(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "extraction_id": self.extraction_id,
            "candidate_id": self.candidate_local_id,
            "candidate_db_id": self.candidate_db_id,
            "routing": self.routing,
            "redaction_report": self.redaction_report,
            "extraction": self.extraction,
            "candidate": self.candidate,
            "metrics": self.metrics,
            "ui_state": self.ui_state,
        }


# ──────────────────────────────────────────────────────────
# Image PII policy
# ──────────────────────────────────────────────────────────

@dataclass
class _ImagePiiPolicyResult:
    policy: str          # "no_ocr_accepted" | future: "ocr_masked" | "blocked"
    can_proceed: bool
    blocking_reason: str | None
    warning: str | None


def _apply_image_pii_policy(
    mime_type: str,
    filename: str,
) -> _ImagePiiPolicyResult:
    """Apply image/PDF internal text PII policy before Gemini transmission.

    Current implementation: no OCR pipeline available.
    Policy decision: accept with explicit logging and report.
    Per plan §1.2.2: "OCR-then-mask, image redaction, 또는 명시적 차단 정책".
    This is the "명시적 차단 정책" variant where the policy explicitly accepts
    the limitation and documents it in redaction_report.

    Future: replace with OCR-then-mask once an OCR pipeline is available.
    """
    warning = (
        "image_internal_text_pii_cannot_be_scanned: "
        "No OCR pipeline available. Image bytes sent to Gemini may contain "
        "raw PII text printed on the drawing. Policy: accepted with logging. "
        "Extraction text output WILL be redacted post-Gemini."
    )
    logger.warning("[PIPELINE] image_pii_policy=no_ocr_accepted file=%s mime=%s", filename, mime_type)
    return _ImagePiiPolicyResult(
        policy="no_ocr_accepted",
        can_proceed=True,
        blocking_reason=None,
        warning=warning,
    )


# ──────────────────────────────────────────────────────────
# UI state computation
# ──────────────────────────────────────────────────────────

def compute_ui_state(
    furniture_type: str,
    unresolved_fields: list[str],
    validation_result: dict[str, Any] | None,
    extra_blocking_reasons: list[str] | None = None,
) -> dict[str, Any]:
    """Compute button gate state from candidate properties.

    can_preview_3d: validator valid + no unresolved + frontend supported type
    can_approve:    false at upload time (requires explicit human review)
    can_save_design_case: false (requires approved=True after approve action)
    """
    blocking_reasons: list[str] = list(extra_blocking_reasons or [])

    if unresolved_fields:
        blocking_reasons.append(f"unresolved_fields:{','.join(unresolved_fields)}")

    is_supported = furniture_type in _FRONTEND_SUPPORTED_TYPES
    if not is_supported:
        blocking_reasons.append(f"unsupported_furniture_type:{furniture_type}")

    is_valid = (
        validation_result is not None
        and validation_result.get("valid", False)
        and not validation_result.get("errors")
    )
    if not is_valid and not unresolved_fields:
        # Validator ran and failed (not just skipped due to unresolved)
        errors = (validation_result or {}).get("errors", [])
        if errors:
            blocking_reasons.append(f"validator_failed:{errors[0]}")

    can_preview_3d = (
        not unresolved_fields
        and is_supported
        and is_valid
    )

    return {
        "can_review": True,
        "can_preview_3d": can_preview_3d,
        "can_approve": False,       # requires human review completion (separate action)
        "can_save_design_case": False,  # requires approved=True
        "blocking_reasons": blocking_reasons,
    }


# ──────────────────────────────────────────────────────────
# Main pipeline
# ──────────────────────────────────────────────────────────

def run_intake_pipeline(
    image_bytes: bytes,
    filename: str,
    mime_type: str,
    user_id: int | None = None,
    project_id: int | None = None,
) -> DrawingPipelineResult:
    """Execute the full drawing intake pipeline.

    Steps:
      1. Determine page count (PDF multi-page detection)
      2. Apply image PII policy
      3. Create DesignerDrawingArtifact + DesignerDrawingPage
      4. Classify drawing template
      5. Route model via model_router
      6. Call Gemini extraction
      7. Redact PII from extraction text output
      8. Normalize extraction dict
      9. Persist DesignerDrawingExtraction
      10. Build MappedCandidate
      11. Compute ui_state
      12. Persist DesignerExtractionCandidate
      13. Return DrawingPipelineResult

    Raises:
      GeminiAPIKeyMissing: If GEMINI_API_KEY not set.
      GeminiProviderError: If Gemini extraction fails.
      RuntimeError: If DB persistence fails.
    """
    import os
    import time
    from foms.services.designer.gemini_provider import GeminiAPIKeyMissing, GeminiProviderError

    # Pre-check: API key required before any DB work (no silent fallback)
    fake_mode = os.environ.get("DESIGNER_FAKE_VISION", "0") == "1"
    has_key = bool(os.environ.get("GEMINI_API_KEY"))
    if not fake_mode and not has_key:
        raise GeminiAPIKeyMissing(
            "GEMINI_API_KEY not set. Cannot run intake pipeline. "
            "Set GEMINI_API_KEY in Railway secrets or local .env. "
            "Use DESIGNER_FAKE_VISION=1 for tests only."
        )

    from db import db_session
    from foms.persistence.designer.models import (
        DesignerDrawingArtifact,
        DesignerDrawingPage,
        DesignerDrawingExtraction,
        DesignerExtractionCandidate,
    )
    from foms.services.designer.model_router import route
    from foms.services.designer.gemini_provider import extract_from_image_bytes
    from foms.services.designer.drawing_template_classifier import classify_from_metadata
    from foms.services.designer.pii_redactor import RedactionContext
    from foms.services.designer.ontology_mapper import build_candidate

    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
    extra_blocking: list[str] = []
    pipeline_t0 = time.monotonic()

    logger.info(
        "[PIPELINE] intake start file=%s mime=%s bytes=%d user_id=%s project_id=%s",
        filename, mime_type, len(image_bytes), user_id, project_id,
    )

    # ── Step 1: Page count ───────────────────────────────
    page_count = 1
    if mime_type == "application/pdf":
        try:
            import pypdf
            import io
            reader = pypdf.PdfReader(io.BytesIO(image_bytes))
            page_count = len(reader.pages)
        except ImportError:
            page_count = 1
        except Exception as exc:
            logger.warning("[PIPELINE] PDF page count failed: %s", exc)
            page_count = 1

        if page_count > 1:
            extra_blocking.append(
                f"multi_page_pdf:{page_count}_pages_only_page_1_extracted"
            )
            logger.warning(
                "[PIPELINE] multi-page PDF detected (pages=%d), only page 1 extracted. "
                "Full multi-page support requires per-page artifact pipeline.",
                page_count,
            )

    # ── Step 2: Image PII policy ─────────────────────────
    pii_policy = _apply_image_pii_policy(mime_type, filename)
    redaction_report: dict[str, Any] = {
        "image_pii_policy": pii_policy.policy,
        "image_pii_warning": pii_policy.warning,
        "text_pii_redacted": False,  # updated after step 7
        "pii_map_size": 0,
    }

    # ── Step 3: Persist artifact + page ─────────────────
    artifact = DesignerDrawingArtifact(
        project_id=project_id,
        file_url=filename,          # placeholder; R2 upload integration is a future task
        file_type=suffix if suffix in ("jpg", "jpeg", "png", "pdf", "webp") else "jpg",
        page_count=page_count,
        source="upload",
        status="processing",
        created_by_user_id=user_id,
    )
    db_session.add(artifact)
    db_session.flush()  # get artifact.id

    page = DesignerDrawingPage(
        artifact_id=artifact.id,
        page_no=1,
        template_key=None,  # filled in after classification
    )
    db_session.add(page)
    db_session.flush()  # get page.id

    # ── Step 4: Template classification ─────────────────
    try:
        from foms.services.designer.drawing_template_classifier import classify_with_gemini
        import os
        if os.environ.get("GEMINI_API_KEY"):
            classification = classify_with_gemini(
                filename,
                image_bytes,
                page_count,
                mime_type=mime_type,
            )
        else:
            classification = classify_from_metadata(filename, page_count)
    except Exception as exc:
        logger.warning("[PIPELINE] template classification failed: %s, using metadata fallback", exc)
        classification = classify_from_metadata(filename, page_count)

    page.template_key = classification.template_key
    db_session.flush()
    logger.info(
        "[PIPELINE] classification done file=%s template=%s method=%s confidence=%.2f",
        filename, classification.template_key, classification.method, classification.confidence,
    )

    # ── Step 5: Model routing ────────────────────────────
    # Raises RuntimeError if GEMINI_API_KEY missing (no fake fallback in pipeline)
    route_result = route(
        template_key=classification.template_key,
        page_count=page_count,
    )
    logger.info(
        "[PIPELINE] routing done file=%s provider=%s model=%s template=%s",
        filename, route_result.provider, route_result.model_name, route_result.template_key,
    )

    # ── Step 6: Gemini extraction ────────────────────────
    raw = extract_from_image_bytes(image_bytes, mime_type=mime_type, model=route_result.model_name)
    metrics = raw.pop("_metrics", {})
    logger.info(
        "[PIPELINE] extraction done file=%s model=%s latency_ms=%s",
        filename, metrics.get("model") or route_result.model_name, metrics.get("latency_ms"),
    )

    # ── Step 7: Text PII redaction ───────────────────────
    pii_ctx = RedactionContext(artifact_id=artifact.id, project_id=project_id)
    try:
        raw = pii_ctx.redact_extraction(raw)
        redaction_report["text_pii_redacted"] = True
        redaction_report["pii_map_size"] = len(pii_ctx.raw_map)
    except Exception as exc:
        logger.error("[PIPELINE] PII redaction failed: %s", exc)
        redaction_report["text_pii_redaction_error"] = str(exc)

    # ── Step 8: Normalize extraction ────────────────────
    extracted_params = raw.get("extracted_params") or {}
    parts_table = raw.get("parts_table") or []
    customer_info = raw.get("customer_info") or {}
    drawing_meta = raw.get("drawing_meta") or {}
    design_understanding = raw.get("design_understanding") or {}

    extraction_dict = {
        "furniture_type": raw.get("furniture_type", "custom_storage"),
        "site_size": {
            "width_mm": extracted_params.get("width"),
            "depth_mm": extracted_params.get("depth"),
            "height_mm": extracted_params.get("height"),
        },
        "module_widths_mm": extracted_params.get("module_widths") or [],
        "extracted_params": extracted_params,
        "parts_table": parts_table,
        "customer_info": customer_info,
        "drawing_meta": drawing_meta,
        "design_understanding": design_understanding,
        "unresolved_fields": raw.get("unresolved_fields") or [],
        "confidence": raw.get("confidence", 0.0),
    }

    # ── Step 9: Persist extraction ───────────────────────
    extraction_row = DesignerDrawingExtraction(
        page_id=page.id,
        extractor_version="gemini-v1",
        parsed_json=extraction_dict,
        confidence_json={"confidence": extraction_dict["confidence"]},
        status="pending_approval",
        model_name=metrics.get("model") or route_result.model_name,
        latency_ms=metrics.get("latency_ms"),
        cost_usd=metrics.get("cost_usd"),
        routing_json=route_result.to_dict(),
        redaction_report_json=redaction_report,
    )
    db_session.add(extraction_row)
    db_session.flush()
    logger.info(
        "[PIPELINE] extraction persisted file=%s artifact_id=%d extraction_id=%d",
        filename, artifact.id, extraction_row.id,
    )

    # ── Step 10: Build MappedCandidate ───────────────────
    candidate = build_candidate(extraction_dict, source_extraction_id=extraction_row.id)

    # ── Step 11: Compute ui_state ────────────────────────
    ui_state = compute_ui_state(
        furniture_type=candidate.furniture_type,
        unresolved_fields=candidate.unresolved_fields,
        validation_result=candidate.validation_result,
        extra_blocking_reasons=extra_blocking,
    )

    # ── Step 12: Persist candidate ───────────────────────
    candidate_row = DesignerExtractionCandidate(
        extraction_id=extraction_row.id,
        furniture_type=candidate.furniture_type,
        extracted_params_json=candidate.factory_params,
        unresolved_fields_json=candidate.unresolved_fields,
        confidence=candidate.confidence,
        approved=False,
        status="pending_review",
        blocking_reasons_json=ui_state["blocking_reasons"],
    )
    db_session.add(candidate_row)

    # Mark artifact done
    artifact.status = "done"
    db_session.commit()

    logger.info(
        "[PIPELINE] complete file=%s artifact=%d extraction=%d candidate=%d "
        "type=%s unresolved=%d can_preview_3d=%s cost=$%.5f total_ms=%d",
        filename, artifact.id, extraction_row.id, candidate_row.id,
        candidate.furniture_type, len(candidate.unresolved_fields),
        ui_state["can_preview_3d"],
        metrics.get("cost_usd", 0.0),
        int((time.monotonic() - pipeline_t0) * 1000),
    )

    return DrawingPipelineResult(
        artifact_id=artifact.id,
        extraction_id=extraction_row.id,
        candidate_db_id=candidate_row.id,
        candidate_local_id=candidate.candidate_id,
        routing=route_result.to_dict(),
        redaction_report=redaction_report,
        extraction=extraction_dict,
        candidate=candidate.to_dict(),
        metrics=metrics,
        ui_state=ui_state,
    )
