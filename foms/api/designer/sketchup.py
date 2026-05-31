"""B2/B7: SketchUp Intake + Review API.

Endpoints:
  POST /api/designer/sketchup/upload-and-analyze
       Accept .skp/.skb, persist artifact, enqueue parse job (idempotent).
  GET  /api/designer/sketchup/jobs/<job_id>
       Poll job status / surface candidate id when ready.
  POST /api/designer/sketchup/jobs/<job_id>/cancel
       Owner-only cancel for queued / running jobs.
  POST /api/designer/sketchup/jobs/<job_id>/worker-presigned-urls
       Internal worker handshake — issues short-lived storage URLs only
       after `(lease_owner, lease_token)` ownership is verified.
  GET  /api/designer/sketchup/candidates/<candidate_id>
       Surface the DesignGraph + layout + blocking reasons so the
       review UI can load 3D preview and gate approve buttons.
  POST /api/designer/sketchup/candidates/<candidate_id>/preview-ack
       Record an iframe preview-load acknowledgement. The server
       hashes the *current* design_graph_candidate_json so the approval
       gate can later assert the ack matches what is on screen.

Contract notes (plan §3.3, §8.1, §8.2, §11.1):
- Workers never hold long-lived R2 credentials. Presigned URLs are
  re-requested per heartbeat window via the internal endpoint above.
- Upload-and-analyze is idempotent on
  `sha256(project_id|input_sha256|parser_code|contract_version)`. A
  duplicate upload returns the existing job instead of creating a new
  one (acceptance: §B2).
- Feature flag `DESIGNER_SKETCHUP_ENABLED` gates the whole surface: when
  off the endpoints reply 503 with `code='SKETCHUP_DISABLED'` — never
  silent 200.
- Preview ack (plan §4.2.4, §9.4): the server computes the canonical
  hash of the candidate graph at write time. The client never controls
  the hash; that prevents a malicious client from acking a hash that
  doesn't match the data the 3D editor actually rendered.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Blueprint, g, jsonify, request
from werkzeug.utils import secure_filename

from foms.api.designer.security import require_designer_write
from foms.persistence.designer import (
    claim_sketchup_job,  # noqa: F401  (re-exported; worker calls)
    create_sketchup_job,
    finish_sketchup_job,  # noqa: F401
    get_sketchup_job,
    get_sketchup_job_by_idempotency_key,
)
from foms.persistence.designer.models import (
    DesignerDrawingArtifact,
    DesignerDrawingExtraction,
    DesignerExtractionCandidate,
    DesignerSketchUpModelSnapshot,
)
from foms.services.storage import get_storage
from foms.web.auth import login_required
from db import db_session


def canonical_design_graph_hash(graph: dict | None) -> str:
    """SHA256 of the canonical JSON form of a candidate DesignGraph.

    Canonical = `json.dumps(..., sort_keys=True, separators=(',', ':'),
    ensure_ascii=False)`. The same encoding must be used on both write
    (preview-ack) and read (approval gate) sides, so it lives in this
    module rather than being recomputed locally at each call site.
    """
    if not graph:
        return hashlib.sha256(b"null").hexdigest()
    encoded = json.dumps(graph, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


logger = logging.getLogger(__name__)


designer_sketchup_bp = Blueprint(
    "designer_sketchup",
    __name__,
    url_prefix="/api/designer/sketchup",
)


# ──────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────

ALLOWED_SKETCHUP_EXTENSIONS = {".skp", ".skb"}

# Spec §8.1 — plan default 200MB. Override via env.
DEFAULT_MAX_FILE_MB = 200

# Stable string fragments used to derive the idempotency key. Bumping
# `ANALYZER_CONTRACT_VERSION` retires every previously seen job hash so
# a re-run after a parser contract change is treated as a fresh job.
ANALYZER_CONTRACT_VERSION = "v1"


def _feature_enabled() -> bool:
    return os.environ.get("DESIGNER_SKETCHUP_ENABLED", "0") == "1"


def _max_file_mb() -> int:
    try:
        return int(os.environ.get("DESIGNER_SKETCHUP_MAX_FILE_MB", str(DEFAULT_MAX_FILE_MB)))
    except ValueError:
        return DEFAULT_MAX_FILE_MB


def _worker_kind() -> str:
    return os.environ.get("DESIGNER_SKETCHUP_WORKER_KIND", "c_api")


def _parser_code() -> str:
    """Stable parser identifier for the idempotency key.

    Independent from `parser_version` (which is the human-readable build
    string). Pinned per worker_kind so changing the version label without
    changing the parser binary still collapses to the same job.
    """
    return {
        "c_api": "sketchup-capi",
        "desktop_ruby": "sketchup-ruby",
        "fake_contract": "sketchup-fake",
    }.get(_worker_kind(), "sketchup-unknown")


def _parser_version() -> str:
    return os.environ.get("DESIGNER_SKETCHUP_PARSER_VERSION", "sketchup-analyzer-0.1.0")


def _internal_worker_token() -> str:
    return os.environ.get("DESIGNER_SKETCHUP_WORKER_API_TOKEN", "")


def _presigned_ttl() -> int:
    try:
        return int(os.environ.get("DESIGNER_SKETCHUP_STORAGE_URL_TTL_SECONDS", "900"))
    except ValueError:
        return 900


# ──────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────


def _envelope_error(code: str, message: str, http_status: int, details: dict | None = None):
    """Plan §8.3 — unified error envelope. No silent fallback."""
    return (
        jsonify(
            {
                "success": False,
                "data": None,
                "error": {
                    "code": code,
                    "message": message,
                    "details": details or {},
                },
            }
        ),
        http_status,
    )


def _disabled_response():
    return _envelope_error(
        code="SKETCHUP_DISABLED",
        message="SketchUp intake is not enabled in this environment.",
        http_status=503,
    )


def _make_idempotency_key(
    *,
    project_id: int | None,
    sha256: str,
    parser_code: str,
    contract_version: str,
) -> str:
    """Plan §4.2.2 — stable hash of (project, sha, parser, contract).

    Returns a 64-char hex digest. The DB column is VARCHAR(255) so this
    leaves room for future format changes without schema churn.
    """
    raw = f"{project_id or 0}|{sha256}|{parser_code}|{contract_version}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _current_user_id() -> int | None:
    user = getattr(g, "current_user", None)
    return getattr(user, "id", None) if user is not None else None


def _job_to_payload(job, *, include_ui_state: bool = True) -> dict[str, Any]:
    """Stable status envelope (plan §5.1 GET /jobs/<id>).

    B7: surface candidate_id and preview_allowed so the client can poll a
    single endpoint and route to the review workspace without an extra
    candidate lookup. The candidate row is created by the intake
    pipeline (B5/B6) so it exists for any succeeded job.
    """
    snapshot = (
        db_session.query(DesignerSketchUpModelSnapshot)
        .filter(DesignerSketchUpModelSnapshot.parse_job_id == job.id)
        .order_by(DesignerSketchUpModelSnapshot.id.desc())
        .first()
    )
    extraction_id = snapshot.extraction_id if snapshot is not None else None

    candidate: DesignerExtractionCandidate | None = None
    if extraction_id is not None:
        candidate = (
            db_session.query(DesignerExtractionCandidate)
            .filter(DesignerExtractionCandidate.extraction_id == extraction_id)
            .order_by(DesignerExtractionCandidate.id.desc())
            .first()
        )

    blocking: list[str] = []
    if job.status != "succeeded":
        blocking.append(f"parse_status:{job.status}")
    if snapshot is None and job.status == "succeeded":
        blocking.append("snapshot_missing")

    payload: dict[str, Any] = {
        "job_id": job.id,
        "status": job.status,
        "artifact_id": job.artifact_id,
        "snapshot_id": snapshot.id if snapshot else None,
        "extraction_id": extraction_id,
        "candidate_id": candidate.id if candidate else None,
        "attempt_count": job.attempt_count,
        "max_attempts": job.max_attempts,
        "error": (
            {"code": job.error_code, "message": job.error_text}
            if job.error_code or job.error_text
            else None
        ),
    }
    if include_ui_state:
        can_review = job.status == "succeeded" and snapshot is not None
        preview_allowed = bool(candidate and candidate.preview_allowed)
        can_approve, _approval_blockers = (
            _can_approve(candidate) if candidate is not None else (False, [])
        )
        payload["ui_state"] = {
            "can_review": can_review,
            "can_preview_3d": preview_allowed,
            "can_approve": can_approve,
            "can_save_design_case": can_approve,
            "blocking_reasons": blocking,
        }
    return payload


# ──────────────────────────────────────────────────────────
# POST /upload-and-analyze
# ──────────────────────────────────────────────────────────


@designer_sketchup_bp.route("/upload-and-analyze", methods=["POST"])
@login_required
@require_designer_write
def upload_and_analyze():
    if not _feature_enabled():
        return _disabled_response()

    if "file" not in request.files:
        return _envelope_error(
            code="FILE_MISSING",
            message="multipart 'file' 필드가 없습니다.",
            http_status=400,
        )

    upload = request.files["file"]
    if not upload.filename:
        return _envelope_error(
            code="FILE_NAME_EMPTY",
            message="파일명이 비어 있습니다.",
            http_status=400,
        )

    suffix = Path(upload.filename).suffix.lower()
    if suffix not in ALLOWED_SKETCHUP_EXTENSIONS:
        return _envelope_error(
            code="UNSUPPORTED_EXTENSION",
            message=(
                "SketchUp intake는 .skp 또는 .skb 파일만 허용합니다. "
                f"입력: {suffix or '(없음)'}"
            ),
            http_status=400,
            details={"allowed": sorted(ALLOWED_SKETCHUP_EXTENSIONS)},
        )

    # Size + SHA256 calculated by streaming the file once.
    max_bytes = _max_file_mb() * 1024 * 1024
    sha = hashlib.sha256()
    total = 0
    chunks: list[bytes] = []
    while True:
        chunk = upload.stream.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            return _envelope_error(
                code="FILE_TOO_LARGE",
                message=f"파일이 너무 큽니다. 최대 {_max_file_mb()}MB.",
                http_status=400,
                details={"max_mb": _max_file_mb()},
            )
        sha.update(chunk)
        chunks.append(chunk)
    if total == 0:
        return _envelope_error(
            code="FILE_EMPTY",
            message="빈 파일은 허용되지 않습니다.",
            http_status=400,
        )

    sha256_hex = sha.hexdigest()
    project_id_raw = request.form.get("project_id", "").strip()
    project_id: int | None
    try:
        project_id = int(project_id_raw) if project_id_raw else None
    except ValueError:
        return _envelope_error(
            code="PROJECT_ID_INVALID",
            message="project_id는 정수여야 합니다.",
            http_status=400,
        )

    analysis_mode = request.form.get("analysis_mode", "parse_only").strip() or "parse_only"
    if analysis_mode not in {"parse_only", "parse_and_assist"}:
        return _envelope_error(
            code="ANALYSIS_MODE_INVALID",
            message="analysis_mode는 'parse_only' 또는 'parse_and_assist'여야 합니다.",
            http_status=400,
        )

    parser_code = _parser_code()
    idempotency_key = _make_idempotency_key(
        project_id=project_id,
        sha256=sha256_hex,
        parser_code=parser_code,
        contract_version=ANALYZER_CONTRACT_VERSION,
    )

    # Duplicate upload handling. The idempotency_key is unique on the DB,
    # so we never create a second row for the same (project, sha, parser,
    # contract). Behaviour by current status:
    #   - queued/running/succeeded/retryable → return the live job as-is
    #   - failed/cancelled                  → reset the same row back to
    #     queued so the user's retry stays linked to one identity. This
    #     keeps the audit trail (attempt_count, finished_at history) and
    #     avoids the UNIQUE-key collision a naive "create new row" would
    #     produce.
    existing = get_sketchup_job_by_idempotency_key(idempotency_key)
    if existing is not None:
        if existing.status not in {"failed", "cancelled"}:
            return jsonify(
                {
                    "success": True,
                    "data": {
                        "artifact_id": existing.artifact_id,
                        "job_id": existing.id,
                        "status": existing.status,
                        "poll_url": f"/api/designer/sketchup/jobs/{existing.id}",
                        "reused_existing": True,
                    },
                    "error": None,
                }
            )
        # Reset the failed/cancelled row to queued.
        existing.status = "queued"
        existing.error_code = None
        existing.error_text = None
        existing.lease_owner = None
        existing.lease_token = None
        existing.lease_expires_at = None
        existing.last_heartbeat_at = None
        existing.finished_at = None
        db_session.commit()
        db_session.refresh(existing)
        return jsonify(
            {
                "success": True,
                "data": {
                    "artifact_id": existing.artifact_id,
                    "job_id": existing.id,
                    "status": existing.status,
                    "poll_url": f"/api/designer/sketchup/jobs/{existing.id}",
                    "reused_existing": True,
                    "reset_from_terminal": True,
                },
                "error": None,
            }
        )

    # Upload to storage. Workers download via short-lived presigned URLs.
    storage = get_storage()
    job_uuid = uuid.uuid4().hex
    safe_name = secure_filename(upload.filename) or f"upload{suffix}"
    folder = f"designer/sketchup/originals/{job_uuid}"

    # Replay the buffered chunks into a fresh stream for the uploader.
    import io
    body = io.BytesIO(b"".join(chunks))
    upload_result = storage.upload_file(body, safe_name, folder=folder)
    if not upload_result or not upload_result.get("success"):
        return _envelope_error(
            code="STORAGE_UPLOAD_FAILED",
            message="원본 파일을 저장하지 못했습니다.",
            http_status=502,
            details={"storage_error": (upload_result or {}).get("error")},
        )
    storage_key = upload_result.get("key")
    file_url = upload_result.get("url") or storage_key
    mime_type = upload_result.get("content_type") or "application/octet-stream"

    # Insert artifact + job in the same flow. Failures roll back the
    # artifact so we never end up with an orphan row.
    try:
        artifact = DesignerDrawingArtifact(
            project_id=project_id,
            file_url=file_url,
            file_type=suffix.lstrip("."),
            page_count=1,
            source="sketchup_upload",
            status="pending",
            original_filename=upload.filename,
            storage_key=storage_key,
            mime_type=mime_type,
            size_bytes=total,
            sha256=sha256_hex,
            analysis_kind="sketchup_model",
            created_by_user_id=_current_user_id(),
        )
        db_session.add(artifact)
        db_session.flush()

        job = create_sketchup_job(
            artifact_id=artifact.id,
            parser_version=_parser_version(),
            input_sha256=sha256_hex,
            idempotency_key=idempotency_key,
            project_id=project_id,
            worker_kind=_worker_kind(),
            storage_keys_json={
                "input": {"role": "input_skp", "key": storage_key},
            },
            user_id=_current_user_id(),
        )
    except Exception as exc:
        db_session.rollback()
        logger.exception("[SKETCHUP] upload failed: %s", exc)
        return _envelope_error(
            code="JOB_CREATE_FAILED",
            message="SketchUp 분석 job 생성에 실패했습니다.",
            http_status=500,
            details={"reason": str(exc)},
        )

    logger.info(
        "[SKETCHUP] upload artifact=%d job=%d sha=%s size=%d mode=%s",
        artifact.id,
        job.id,
        sha256_hex[:12],
        total,
        analysis_mode,
    )

    return jsonify(
        {
            "success": True,
            "data": {
                "artifact_id": artifact.id,
                "job_id": job.id,
                "status": job.status,
                "poll_url": f"/api/designer/sketchup/jobs/{job.id}",
                "reused_existing": False,
            },
            "error": None,
        }
    )


# ──────────────────────────────────────────────────────────
# GET /jobs/<id>
# ──────────────────────────────────────────────────────────


@designer_sketchup_bp.route("/jobs/<int:job_id>", methods=["GET"])
@login_required
def get_job(job_id: int):
    if not _feature_enabled():
        return _disabled_response()

    job = get_sketchup_job(job_id)
    if job is None:
        return _envelope_error(
            code="JOB_NOT_FOUND",
            message=f"job {job_id}을(를) 찾을 수 없습니다.",
            http_status=404,
        )
    return jsonify({"success": True, "data": _job_to_payload(job), "error": None})


# ──────────────────────────────────────────────────────────
# POST /jobs/<id>/cancel
# ──────────────────────────────────────────────────────────


@designer_sketchup_bp.route("/jobs/<int:job_id>/cancel", methods=["POST"])
@login_required
@require_designer_write
def cancel_job(job_id: int):
    if not _feature_enabled():
        return _disabled_response()

    job = get_sketchup_job(job_id)
    if job is None:
        return _envelope_error(
            code="JOB_NOT_FOUND",
            message=f"job {job_id}을(를) 찾을 수 없습니다.",
            http_status=404,
        )

    if job.status in {"succeeded", "failed", "cancelled"}:
        return _envelope_error(
            code="JOB_NOT_CANCELLABLE",
            message=f"job 상태가 {job.status} 이므로 취소할 수 없습니다.",
            http_status=409,
        )

    # Owner-only — created_by_user_id must match the caller. Admins use
    # the same path (no separate "admin force-cancel" yet); add later if
    # ops needs it.
    user_id = _current_user_id()
    if job.created_by_user_id is not None and user_id != job.created_by_user_id:
        return _envelope_error(
            code="NOT_OWNER",
            message="job 생성자만 취소할 수 있습니다.",
            http_status=403,
        )

    job.status = "cancelled"
    # Drop the lease so an in-flight worker's next heartbeat returns None
    # and the worker exits the job cleanly instead of overwriting state.
    job.lease_owner = None
    job.lease_token = None
    job.lease_expires_at = None
    db_session.commit()
    db_session.refresh(job)

    return jsonify({"success": True, "data": _job_to_payload(job), "error": None})


# ──────────────────────────────────────────────────────────
# POST /jobs/<id>/worker-presigned-urls  (internal)
# ──────────────────────────────────────────────────────────


@designer_sketchup_bp.route(
    "/jobs/<int:job_id>/worker-presigned-urls",
    methods=["POST"],
)
def worker_presigned_urls(job_id: int):
    """Internal worker handshake — exchange lease proof for download URLs.

    Plan §11.1: workers do NOT hold long-lived storage credentials.
    The API verifies (lease_owner, lease_token) before minting a
    short-lived presigned URL. The TTL is configurable via
    `DESIGNER_SKETCHUP_STORAGE_URL_TTL_SECONDS` (default 900s).

    Auth: `X-FOMS-Worker-Token` header must equal
    `DESIGNER_SKETCHUP_WORKER_API_TOKEN`. This is a shared secret between
    the API process and the Windows worker; rotate via Railway env.
    """
    if not _feature_enabled():
        return _disabled_response()

    expected_token = _internal_worker_token()
    if not expected_token:
        return _envelope_error(
            code="WORKER_AUTH_DISABLED",
            message="worker API token이 설정되지 않았습니다.",
            http_status=503,
        )
    provided = request.headers.get("X-FOMS-Worker-Token", "")
    # secrets.compare_digest avoids timing leaks on the shared secret.
    if not secrets.compare_digest(provided, expected_token):
        return _envelope_error(
            code="WORKER_AUTH_FAILED",
            message="worker token이 일치하지 않습니다.",
            http_status=403,
        )

    body = request.get_json(silent=True) or {}
    lease_owner = (body.get("lease_owner") or "").strip()
    lease_token = (body.get("lease_token") or "").strip()
    if not lease_owner or not lease_token:
        return _envelope_error(
            code="LEASE_FIELDS_MISSING",
            message="lease_owner / lease_token이 필요합니다.",
            http_status=400,
        )

    job = get_sketchup_job(job_id)
    if job is None:
        return _envelope_error(
            code="JOB_NOT_FOUND",
            message=f"job {job_id}을(를) 찾을 수 없습니다.",
            http_status=404,
        )
    if job.status != "running":
        return _envelope_error(
            code="JOB_NOT_RUNNING",
            message=f"job 상태가 {job.status} 이므로 presigned URL을 발급하지 않습니다.",
            http_status=409,
        )
    if job.lease_owner != lease_owner or not secrets.compare_digest(
        job.lease_token or "", lease_token
    ):
        return _envelope_error(
            code="LEASE_OWNERSHIP_MISMATCH",
            message="현재 lease 소유자가 아닙니다.",
            http_status=403,
        )

    storage = get_storage()
    ttl = _presigned_ttl()

    urls: dict[str, dict[str, Any]] = {}
    for role_name, payload in (job.storage_keys_json or {}).items():
        key = payload.get("key") if isinstance(payload, dict) else None
        if not key:
            continue
        get_url = storage.get_download_url(key, expires_in=ttl)
        if get_url:
            urls[role_name] = {
                "key": key,
                "method": "GET",
                "url": get_url,
                "expires_in_seconds": ttl,
            }

    # Output upload slots — worker uploads result.json / preview assets
    # under a job-scoped prefix. Keys are deterministic so the API can
    # later find them by convention.
    out_prefix = f"designer/sketchup/results/{job_id}"
    out_targets = {
        "result_json": f"{out_prefix}/result.json",
        "preview_zip": f"{out_prefix}/preview.zip",
    }
    for role_name, key in out_targets.items():
        put_url = storage.generate_presigned_put_url(
            key,
            content_type="application/octet-stream",
            expires_in=ttl,
        )
        urls[role_name] = {
            "key": key,
            "method": "PUT",
            "url": put_url,
            "expires_in_seconds": ttl,
        }

    return jsonify(
        {
            "success": True,
            "data": {
                "job_id": job.id,
                "urls": urls,
                "ttl_seconds": ttl,
            },
            "error": None,
        }
    )


# ──────────────────────────────────────────────────────────
# Review surface — candidate + preview ack
# ──────────────────────────────────────────────────────────


def _candidate_with_provenance(candidate: DesignerExtractionCandidate):
    """Resolve the (snapshot, artifact, parse_job) chain for a candidate.

    Returns `(snapshot, artifact, parse_job)` — any of which may be None
    when the candidate is not a SketchUp candidate (e.g. legacy image
    extraction). The review API treats those as 404 so callers can't
    accidentally treat an image candidate as a SketchUp one.
    """
    extraction = candidate.extraction
    if extraction is None:
        return None, None, None
    snapshot = (
        db_session.query(DesignerSketchUpModelSnapshot)
        .filter(DesignerSketchUpModelSnapshot.extraction_id == extraction.id)
        .order_by(DesignerSketchUpModelSnapshot.id.desc())
        .first()
    )
    if snapshot is None:
        return None, None, None
    artifact = db_session.get(DesignerDrawingArtifact, snapshot.artifact_id)
    parse_job = get_sketchup_job(snapshot.parse_job_id)
    return snapshot, artifact, parse_job


def _can_approve(candidate: DesignerExtractionCandidate) -> tuple[bool, list[str]]:
    """Compute the approve-gate status (plan §9.4).

    The endpoint that *performs* approve lives elsewhere (B9). Here we
    only surface the gate state so the UI can disable buttons; the
    server-side check happens again at approve time.
    """
    blockers: list[str] = list(candidate.blocking_reasons_json or [])
    if candidate.status not in {"pending_review", "corrected"}:
        blockers.append(f"candidate_status:{candidate.status}")
    if not candidate.design_graph_candidate_json:
        blockers.append("no_design_graph")
    elif not (candidate.design_graph_candidate_json.get("components") or []):
        blockers.append("no_components_in_design_graph")
    if not candidate.preview_allowed:
        blockers.append("preview_not_allowed")
    if not candidate.last_preview_ack_at:
        blockers.append("preview_ack_missing")
    elif candidate.last_preview_ack_error:
        blockers.append(f"preview_ack_error:{candidate.last_preview_ack_error[:80]}")
    else:
        current_hash = canonical_design_graph_hash(candidate.design_graph_candidate_json)
        if candidate.last_preview_ack_hash != current_hash:
            blockers.append("preview_ack_hash_mismatch")
    return (not blockers), blockers


@designer_sketchup_bp.route("/candidates/<int:candidate_id>", methods=["GET"])
@login_required
def get_candidate(candidate_id: int):
    """Return the review-time view of a SketchUp candidate."""
    if not _feature_enabled():
        return _disabled_response()

    candidate = db_session.get(DesignerExtractionCandidate, candidate_id)
    if candidate is None:
        return _envelope_error(
            code="CANDIDATE_NOT_FOUND",
            message=f"candidate {candidate_id} not found.",
            http_status=404,
        )

    snapshot, artifact, parse_job = _candidate_with_provenance(candidate)
    if snapshot is None:
        return _envelope_error(
            code="NOT_SKETCHUP_CANDIDATE",
            message="이 candidate는 SketchUp 분석 결과가 아닙니다.",
            http_status=404,
        )

    can_approve, approval_blockers = _can_approve(candidate)
    current_hash = canonical_design_graph_hash(candidate.design_graph_candidate_json)

    return jsonify(
        {
            "success": True,
            "data": {
                "candidate_id": candidate.id,
                "status": candidate.status,
                "approved": candidate.approved,
                "preview_allowed": candidate.preview_allowed,
                "confidence": candidate.confidence,
                "furniture_type": candidate.furniture_type,
                "design_graph_candidate_json": candidate.design_graph_candidate_json,
                "current_design_graph_hash": current_hash,
                "layout_json": snapshot.layout_graph_json,
                "extracted_params": candidate.extracted_params_json,
                "unresolved_fields": candidate.unresolved_fields_json or [],
                "blocking_reasons": candidate.blocking_reasons_json or [],
                "mapping_report": candidate.mapping_report_json,
                "validation": candidate.validation_json,
                "preview_ack": {
                    "at": candidate.last_preview_ack_at.isoformat()
                    if candidate.last_preview_ack_at
                    else None,
                    "hash": candidate.last_preview_ack_hash,
                    "error": candidate.last_preview_ack_error,
                    "matches_current": (
                        candidate.last_preview_ack_hash == current_hash
                        and candidate.last_preview_ack_error is None
                    ),
                },
                "ui_state": {
                    "can_review": True,
                    "can_preview_3d": bool(candidate.preview_allowed),
                    "can_approve": can_approve,
                    "can_save_design_case": can_approve,
                    "approval_blocking_reasons": approval_blockers,
                },
                "provenance": {
                    "artifact_id": artifact.id if artifact else None,
                    "parse_job_id": parse_job.id if parse_job else None,
                    "snapshot_id": snapshot.id,
                    "extractor_version": (
                        candidate.extraction.extractor_version
                        if candidate.extraction is not None
                        else None
                    ),
                    "original_filename": artifact.original_filename if artifact else None,
                },
            },
            "error": None,
        }
    )


@designer_sketchup_bp.route(
    "/candidates/<int:candidate_id>/assist",
    methods=["POST"],
)
@login_required
@require_designer_write
def post_candidate_assist(candidate_id: int):
    """Run Gemini assist against an existing SketchUp candidate (plan §B8).

    Assist output is *advisory* — it is appended to
    `extraction.confidence_json.assist` and `snapshot.warnings_json`, and
    audited in a `DesignerAIRun(graph_name='sketchup_gemini_assist')`.
    It NEVER mutates `design_graph_candidate_json` or the approval gate
    state. The endpoint refuses gracefully when GEMINI_API_KEY is missing
    so the parser path stays usable without a Gemini billing account.

    Body (all optional):
      ``{"model": "gemini-1.5-pro", "similar_cases": [...]}``
    """
    if not _feature_enabled():
        return _disabled_response()

    candidate = db_session.get(DesignerExtractionCandidate, candidate_id)
    if candidate is None:
        return _envelope_error(
            code="CANDIDATE_NOT_FOUND",
            message=f"candidate {candidate_id} not found.",
            http_status=404,
        )
    snapshot, _, _ = _candidate_with_provenance(candidate)
    if snapshot is None:
        return _envelope_error(
            code="NOT_SKETCHUP_CANDIDATE",
            message="이 candidate는 SketchUp 분석 결과가 아닙니다.",
            http_status=404,
        )

    body = request.get_json(silent=True) or {}
    model = (body.get("model") or "").strip() or None
    similar_cases = body.get("similar_cases") or []
    if not isinstance(similar_cases, list):
        return _envelope_error(
            code="SIMILAR_CASES_INVALID",
            message="similar_cases는 배열이어야 합니다.",
            http_status=400,
        )

    # Import here so the API module stays importable in environments
    # that don't have google-genai (worker boxes, CI without keys).
    from foms.services.designer.gemini_provider import (
        GeminiAPIKeyMissing,
        GeminiProviderError,
    )
    from foms.services.designer.sketchup_gemini_assist import (
        AssistSchemaInvalidError,
        attach_assist_to_candidate,
        build_assist_context,
        call_gemini_for_assist,
    )

    try:
        context = build_assist_context(
            candidate=candidate,
            snapshot=snapshot,
            similar_cases=similar_cases,
        )
        assist_payload, latency_ms = call_gemini_for_assist(context, model=model)
        result = attach_assist_to_candidate(
            candidate=candidate,
            snapshot=snapshot,
            assist_payload=assist_payload,
            context=context,
            latency_ms=latency_ms,
            model=model or "default",
            user_id=_current_user_id(),
        )
    except GeminiAPIKeyMissing as exc:
        return _envelope_error(
            code="GEMINI_KEY_MISSING",
            message=str(exc),
            http_status=503,
        )
    except AssistSchemaInvalidError as exc:
        return _envelope_error(
            code="ASSIST_SCHEMA_INVALID",
            message="Gemini assist 응답 스키마가 유효하지 않습니다.",
            http_status=502,
            details={
                "errors": [
                    {"path": e["path"], "message": e["message"]}
                    for e in exc.validation.errors[:5]
                ],
            },
        )
    except GeminiProviderError as exc:
        return _envelope_error(
            code="GEMINI_PROVIDER_ERROR",
            message=str(exc),
            http_status=502,
        )

    # Re-read candidate so approval gate reflects any blocker changes
    # the assist may have surfaced (currently it never blocks, but the
    # shape is forward-compatible).
    db_session.refresh(candidate)
    can_approve, approval_blockers = _can_approve(candidate)
    return jsonify(
        {
            "success": True,
            "data": {
                "candidate_id": candidate.id,
                "ai_run_id": result.ai_run_id,
                "model": result.model,
                "latency_ms": result.latency_ms,
                "context_size_chars": result.context_size_chars,
                "warnings_added": result.warnings_added,
                "assist": result.assist_payload,
                "ui_state": {
                    "can_review": True,
                    "can_preview_3d": bool(candidate.preview_allowed),
                    "can_approve": can_approve,
                    "approval_blocking_reasons": approval_blockers,
                },
            },
            "error": None,
        }
    )


@designer_sketchup_bp.route(
    "/candidates/<int:candidate_id>/approve-and-save",
    methods=["POST"],
)
@login_required
@require_designer_write
def post_candidate_approve_and_save(candidate_id: int):
    """Approve a SketchUp candidate and persist a learning case (plan §B9).

    Behaviour:
      1. Re-run the approval gate (`_can_approve`). Refuses with 422 if
         any blocker remains so the server is the final arbiter — the
         client can have stale gate state.
      2. Create a `DesignerProjectVersion` from the candidate's
         DesignGraph after re-validating it. Create a `DesignerProject`
         on the fly when the candidate isn't tied to one yet (typical
         for one-off SketchUp uploads).
      3. Flip candidate fields: `approved=True`, `status='approved'`.
      4. Insert a `DesignerDesignCase` via `save_design_case()` with
         full SketchUp provenance — `drawing_artifact_id`,
         `approved_extraction_id`, `source_candidate_id` — and an
         `internal_structure_json` snapshot summary so retrieval can
         surface "where this case came from" without re-querying the
         snapshot table.
      5. NEVER auto-promote rule / archetype candidates here. Those gates
         live in their own services and require a 3-case minimum
         (`product_archetype_learning.MIN_CASES = 3`).
    """
    if not _feature_enabled():
        return _disabled_response()

    candidate = db_session.get(DesignerExtractionCandidate, candidate_id)
    if candidate is None:
        return _envelope_error(
            code="CANDIDATE_NOT_FOUND",
            message=f"candidate {candidate_id} not found.",
            http_status=404,
        )
    snapshot, artifact, parse_job = _candidate_with_provenance(candidate)
    if snapshot is None:
        return _envelope_error(
            code="NOT_SKETCHUP_CANDIDATE",
            message="이 candidate는 SketchUp 분석 결과가 아닙니다.",
            http_status=404,
        )

    if candidate.status == "approved" or candidate.approved:
        return _envelope_error(
            code="ALREADY_APPROVED",
            message="이미 승인된 candidate입니다.",
            http_status=409,
        )

    body = request.get_json(silent=True) or {}
    # Reviewers can override the candidate's furniture_type at approve
    # time — `_VALID_FURNITURE_TYPES` in design_case_memory refuses
    # 'unknown', and the layout extractor leaves furniture_type=unknown
    # intentionally for the human to resolve.
    override_furniture_type = (body.get("furniture_type") or "").strip() or None
    _VALID_FT = {"wardrobe", "shoe_rack", "kitchen_base", "kitchen_wall", "custom_storage"}
    if override_furniture_type and override_furniture_type not in _VALID_FT:
        return _envelope_error(
            code="FURNITURE_TYPE_INVALID",
            message=f"furniture_type은 다음 중 하나여야 합니다: {sorted(_VALID_FT)}",
            http_status=400,
        )
    effective_furniture_type = (
        override_furniture_type
        or (candidate.furniture_type if candidate.furniture_type in _VALID_FT else "custom_storage")
    )
    auto_furniture_type = (
        override_furniture_type is None
        and candidate.furniture_type not in _VALID_FT
    )

    # Gate re-check — plan §9.4. Client state can lag; server is the
    # final arbiter so a hash-mismatched ack cannot slip through.
    can_approve, approval_blockers = _can_approve(candidate)
    if not can_approve:
        return _envelope_error(
            code="APPROVE_BLOCKED",
            message="approval gate에 차단된 사유가 있어 승인할 수 없습니다.",
            http_status=422,
            details={"reasons": approval_blockers},
        )

    design_graph = candidate.design_graph_candidate_json or {}

    # Local imports keep this endpoint testable even when the heavy
    # validator/learning modules are slow to import at app boot.
    from foms.persistence.designer import create_project, create_project_version
    from foms.persistence.designer.models import (
        DesignerDesignCase,
        DesignerDrawingExtraction,
        DesignerProject,
    )
    from foms.services.designer.design_case_memory import save_design_case
    from foms.services.designer.product_archetype_learning import extract_tags_from_case
    from foms.services.designer.validator import validate_design

    # Re-validate the DesignGraph immediately before commit. Same
    # contract as the drawing path: empty components or validator errors
    # close the gate even after `_can_approve` was true (which should
    # never happen, but a belt-and-suspenders check costs us nothing).
    components = design_graph.get("components") or []
    if not components:
        return _envelope_error(
            code="APPROVE_BLOCKED",
            message="DesignGraph에 components가 없습니다.",
            http_status=422,
            details={"reasons": ["no_components_in_design_graph"]},
        )
    val_result = validate_design(design_graph)
    if val_result.errors:
        return _envelope_error(
            code="APPROVE_BLOCKED",
            message="DesignGraph validator가 실패했습니다.",
            http_status=422,
            details={
                "reasons": [e.message for e in val_result.errors[:5]],
            },
        )

    user_id = _current_user_id()

    # Ensure a project exists. For one-shot SketchUp uploads
    # (project_id=None), spin up a project named after the artifact so
    # the version has a parent row to attach to.
    project_id = parse_job.project_id if parse_job else None
    project_obj: DesignerProject | None = None
    if project_id is not None:
        project_obj = db_session.get(DesignerProject, project_id)
    if project_obj is None:
        proj_name = (
            artifact.original_filename
            if artifact and artifact.original_filename
            else f"SketchUp Candidate {candidate.id}"
        )
        project_obj = create_project(name=proj_name, user_id=user_id)
        project_id = project_obj.id

    # Project version.
    try:
        version = create_project_version(
            project_id=project_id,
            design_json=design_graph,
            validation_json={"valid": True, "errors": []},
            user_id=user_id,
        )
    except Exception as exc:
        logger.exception("[SKETCHUP] approve project_version failed: %s", exc)
        return _envelope_error(
            code="PROJECT_VERSION_FAILED",
            message=f"project version 생성 실패: {exc}",
            http_status=500,
        )

    # Flip candidate + extraction state.
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    candidate.approved = True
    candidate.status = "approved"
    candidate.approved_by_user_id = user_id
    candidate.approved_at = now
    # Persist the resolved furniture_type so retrieval / future tooling
    # doesn't have to re-derive it from `auto_furniture_type` tags.
    if candidate.furniture_type != effective_furniture_type:
        candidate.furniture_type = effective_furniture_type
    extraction = candidate.extraction
    if extraction is not None and extraction.status != "approved":
        extraction.status = "approved"
        extraction.approved_by_user_id = user_id
        extraction.approved_at = now
    db_session.flush()

    # Design case provenance.
    extraction_payload: dict = {}
    if extraction is not None:
        extraction_payload = dict(extraction.parsed_json or {})
    design_understanding = extraction_payload.get("design_understanding") or {}
    internal_structure = {
        "source_kind": "sketchup_model",
        "design_understanding": design_understanding,
        "mapping_report": dict(candidate.mapping_report_json or {}),
        "sketchup": {
            "snapshot_id": snapshot.id,
            "parse_job_id": parse_job.id if parse_job else None,
            "parser_version": snapshot.parser_version,
            "sketchup_api_version": snapshot.sketchup_api_version,
            "load_status": snapshot.load_status,
            "units": snapshot.units_json,
            "bbox": snapshot.bbox_json,
            "component_index": snapshot.component_index_json,
            "material_index": snapshot.material_index_json,
            "warnings": snapshot.warnings_json,
        },
    }

    product_name = (
        artifact.original_filename
        if artifact and artifact.original_filename
        else None
    )
    learning_tags = extract_tags_from_case(
        {
            "furniture_type": effective_furniture_type,
            "product_name": product_name or "",
            "options_json": {"design_understanding": design_understanding},
            "internal_structure_json": internal_structure,
        }
    )
    # Always emit the source provenance tag so retrieval can filter to
    # SketchUp cases specifically.
    if "source:sketchup_model" not in learning_tags:
        learning_tags.append("source:sketchup_model")
    if auto_furniture_type:
        learning_tags.append("auto_furniture_type:custom_storage")

    design_case_id: int | None = None
    try:
        case_result = save_design_case(
            project_version_id=version.id,
            furniture_type=effective_furniture_type,
            design_graph=design_graph,
            project_id=project_id,
            drawing_artifact_id=artifact.id if artifact else None,
            approved_extraction_id=extraction.id if extraction is not None else None,
            product_name=product_name,
            internal_structure=internal_structure,
            tags=learning_tags,
            source_quality_score=float(candidate.confidence or 1.0),
            approval_user_id=user_id,
        )
        design_case_id = case_result.get("id") if isinstance(case_result, dict) else None
        if design_case_id is not None:
            dc = db_session.get(DesignerDesignCase, design_case_id)
            if dc is not None:
                # `source_candidate_id` is the most-precise provenance —
                # save_design_case() doesn't accept it as a kwarg yet, so
                # set it directly here. Keeps the link 1-1 to the row
                # that actually got reviewed.
                dc.source_candidate_id = candidate.id
                db_session.flush()
    except Exception as exc:
        logger.exception("[SKETCHUP] approve save_design_case failed: %s", exc)
        # Project version already exists; don't roll back the approval
        # (the user explicitly approved). Surface the failure so ops can
        # backfill manually.
        db_session.commit()
        return _envelope_error(
            code="DESIGN_CASE_SAVE_FAILED",
            message=f"design case 저장 실패 (project version은 저장됨): {exc}",
            http_status=500,
            details={"project_version_id": version.id},
        )

    db_session.commit()
    db_session.refresh(candidate)

    logger.info(
        "[SKETCHUP] approve candidate=%d version=%d case=%s",
        candidate.id, version.id, design_case_id,
    )

    return jsonify(
        {
            "success": True,
            "data": {
                "candidate_id": candidate.id,
                "project_id": project_id,
                "project_version_id": version.id,
                "design_case_id": design_case_id,
                "approved_extraction_id": extraction.id if extraction is not None else None,
                "tags": learning_tags,
            },
            "error": None,
        }
    )


@designer_sketchup_bp.route(
    "/candidates/<int:candidate_id>/preview-ack",
    methods=["POST"],
)
@login_required
@require_designer_write
def post_preview_ack(candidate_id: int):
    """Record an iframe preview-load ack against the current graph hash.

    Body: ``{"success": bool, "error": str | null, "component_count": int | null}``.
    The server computes the hash itself — clients cannot ack an
    arbitrary value. A success ack with `component_count == 0` is
    rejected (plan §B7 acceptance: "preview empty graph는 성공으로
    보이지 않는다").
    """
    if not _feature_enabled():
        return _disabled_response()

    candidate = db_session.get(DesignerExtractionCandidate, candidate_id)
    if candidate is None:
        return _envelope_error(
            code="CANDIDATE_NOT_FOUND",
            message=f"candidate {candidate_id} not found.",
            http_status=404,
        )
    snapshot, _, _ = _candidate_with_provenance(candidate)
    if snapshot is None:
        return _envelope_error(
            code="NOT_SKETCHUP_CANDIDATE",
            message="이 candidate는 SketchUp 분석 결과가 아닙니다.",
            http_status=404,
        )

    body = request.get_json(silent=True) or {}
    success = bool(body.get("success"))
    error_text = body.get("error")
    component_count = body.get("component_count")

    current_hash = canonical_design_graph_hash(candidate.design_graph_candidate_json)
    components = (
        (candidate.design_graph_candidate_json or {}).get("components") or []
    )

    if success and not components:
        # "preview empty graph 는 성공으로 보이지 않는다" — server-side
        # backstop in case the iframe ever forgets to suppress the toast.
        success = False
        error_text = error_text or "preview_empty_graph"

    if success and component_count is not None and int(component_count) <= 0:
        success = False
        error_text = error_text or "preview_zero_components"

    candidate.last_preview_ack_at = datetime.now(timezone.utc)
    candidate.last_preview_ack_hash = current_hash if success else None
    candidate.last_preview_ack_error = None if success else (error_text or "preview_ack_failed")
    db_session.commit()
    db_session.refresh(candidate)

    can_approve, approval_blockers = _can_approve(candidate)
    return jsonify(
        {
            "success": True,
            "data": {
                "candidate_id": candidate.id,
                "preview_ack": {
                    "at": candidate.last_preview_ack_at.isoformat(),
                    "hash": candidate.last_preview_ack_hash,
                    "error": candidate.last_preview_ack_error,
                    "matches_current": (
                        candidate.last_preview_ack_hash == current_hash
                        and candidate.last_preview_ack_error is None
                    ),
                },
                "ui_state": {
                    "can_review": True,
                    "can_preview_3d": bool(candidate.preview_allowed),
                    "can_approve": can_approve,
                    "can_save_design_case": can_approve,
                    "approval_blocking_reasons": approval_blockers,
                },
            },
            "error": None,
        }
    )
