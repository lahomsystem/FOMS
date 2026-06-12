"""FOMS Brain AX Designer – repository helpers."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import text

from db import db_session
from foms.persistence.designer.models import (
    DesignerAIRun,
    DesignerCorrection,
    DesignerOntologyVersion,
    DesignerProject,
    DesignerProjectVersion,
    DesignerSketchUpModelSnapshot,
    DesignerSketchUpParseJob,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Normalize a datetime to UTC for safe comparisons.

    Why: SQLite (used by the test fixture) drops timezone info on read,
    so a freshly refreshed `lease_expires_at` comes back naive even though
    we stored a tz-aware value. PostgreSQL keeps the tz, so naive vs.
    aware comparisons would otherwise raise `TypeError`. Treat naive
    datetimes as UTC since that's what `_utcnow()` always writes.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

def list_projects(user_id: Optional[int] = None, limit: int = 50) -> list[DesignerProject]:
    q = db_session.query(DesignerProject)
    if user_id is not None:
        q = q.filter(DesignerProject.created_by_user_id == user_id)
    return q.order_by(DesignerProject.updated_at.desc()).limit(limit).all()


def get_project(project_id: int) -> Optional[DesignerProject]:
    return db_session.get(DesignerProject, project_id)


def create_project(name: str, order_id: Optional[int] = None, user_id: Optional[int] = None) -> DesignerProject:
    project = DesignerProject(name=name, order_id=order_id, created_by_user_id=user_id)
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    return project


# ---------------------------------------------------------------------------
# Versions
# ---------------------------------------------------------------------------

def get_next_version_no(project_id: int) -> int:
    latest = (
        db_session.query(DesignerProjectVersion)
        .filter(DesignerProjectVersion.project_id == project_id)
        .order_by(DesignerProjectVersion.version_no.desc())
        .first()
    )
    return (latest.version_no + 1) if latest else 1


def create_project_version(
    project_id: int,
    design_json: dict,
    validation_json: Optional[dict] = None,
    ontology_version_id: Optional[int] = None,
    user_id: Optional[int] = None,
) -> DesignerProjectVersion:
    version_no = get_next_version_no(project_id)
    version = DesignerProjectVersion(
        project_id=project_id,
        version_no=version_no,
        design_json=design_json,
        validation_json=validation_json,
        ontology_version_id=ontology_version_id,
        created_by_user_id=user_id,
    )
    db_session.add(version)
    db_session.flush()  # get version.id before updating project

    # Update project.current_version_id
    project = db_session.get(DesignerProject, project_id)
    if project:
        project.current_version_id = version.id

    db_session.commit()
    db_session.refresh(version)
    return version


# ---------------------------------------------------------------------------
# Ontology
# ---------------------------------------------------------------------------

def get_active_ontology() -> Optional[DesignerOntologyVersion]:
    """Return the single active ontology version.

    Invariant: at most ONE active ontology row exists.
    If multiple active rows are found (data corruption), returns the most recent
    and logs a critical warning — callers should investigate.
    """
    import logging
    rows = (
        db_session.query(DesignerOntologyVersion)
        .filter(DesignerOntologyVersion.status == "active")
        .order_by(DesignerOntologyVersion.created_at.desc())
        .all()
    )
    if len(rows) > 1:
        logging.getLogger(__name__).critical(
            "[DESIGNER] INVARIANT VIOLATION: %d active ontology rows found. "
            "Expected exactly 1. Run de-duplication immediately.",
            len(rows),
        )
    return rows[0] if rows else None


def promote_ontology_version(
    candidate_id: int,
    user_id: Optional[int] = None,
) -> DesignerOntologyVersion:
    """Promote a draft ontology to active.

    PV2-B0 / PV2-B9: DB-level invariant:
    - Retires ALL existing active rows inside one transaction.
    - Sets candidate to active.
    - AI MUST NOT call this directly — human approval required.

    Raises ValueError if candidate is not found or not in draft status.
    """
    candidate = db_session.get(DesignerOntologyVersion, candidate_id)
    if not candidate:
        raise ValueError(f"Ontology candidate {candidate_id} not found")
    if candidate.status != "draft":
        raise ValueError(
            f"Cannot promote ontology {candidate_id}: status is {candidate.status!r}, expected 'draft'"
        )

    try:
        # Retire all currently active rows in one transaction
        active_rows = (
            db_session.query(DesignerOntologyVersion)
            .filter(DesignerOntologyVersion.status == "active")
            .all()
        )
        for row in active_rows:
            row.status = "retired"
        db_session.flush()

        # Promote candidate
        candidate.status = "active"
        db_session.commit()
        db_session.refresh(candidate)
        return candidate
    except Exception:
        db_session.rollback()
        raise


def rollback_to_previous_active(
    retired_ontology_id: int,
) -> DesignerOntologyVersion:
    """Reactivate a previously retired ontology version.

    PV2-B9: rollback path after a failed or unwanted promotion.
    Requires no other active row to exist.

    Raises ValueError if the target is not in retired status.
    """
    target = db_session.get(DesignerOntologyVersion, retired_ontology_id)
    if not target:
        raise ValueError(f"Ontology {retired_ontology_id} not found")
    if target.status != "retired":
        raise ValueError(
            f"Cannot rollback ontology {retired_ontology_id}: status is {target.status!r}, expected 'retired'"
        )

    try:
        # Retire current active
        active_rows = (
            db_session.query(DesignerOntologyVersion)
            .filter(DesignerOntologyVersion.status == "active")
            .all()
        )
        for row in active_rows:
            row.status = "retired"
        db_session.flush()

        target.status = "active"
        db_session.commit()
        db_session.refresh(target)
        return target
    except Exception:
        db_session.rollback()
        raise


def assert_single_active_ontology() -> None:
    """Repository-level invariant check: raises if active count != 1.

    Use in tests and integration checks.
    """
    count = (
        db_session.query(DesignerOntologyVersion)
        .filter(DesignerOntologyVersion.status == "active")
        .count()
    )
    if count > 1:
        raise RuntimeError(
            f"INVARIANT VIOLATION: {count} active ontology rows found. Expected at most 1."
        )


def get_or_create_default_ontology() -> DesignerOntologyVersion:
    existing = get_active_ontology()
    if existing:
        return existing
    ontology = DesignerOntologyVersion(
        version_key="v1.0.0-default",
        status="active",
        rules_json={
            "version": "1.0.0",
            "constraints": {
                "cabinet.width.min": 1,
                "cabinet.width.max": 10000,
                "cabinet.height.min": 1,
                "cabinet.height.max": 4000,
                "cabinet.depth.min": 1,
                "cabinet.depth.max": 1200,
                "panel.thickness.min": 1,
            },
        },
    )
    db_session.add(ontology)
    db_session.commit()
    db_session.refresh(ontology)
    return ontology


# ---------------------------------------------------------------------------
# AI Runs
# ---------------------------------------------------------------------------

def create_ai_run(
    graph_name: str,
    thread_id: str,
    input_json: dict,
    user_id: Optional[int] = None,
    graph_version: str = "0.1.0",
) -> DesignerAIRun:
    run = DesignerAIRun(
        graph_name=graph_name,
        graph_version=graph_version,
        thread_id=thread_id,
        input_json=input_json,
        created_by_user_id=user_id,
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    return run


def get_ai_run(run_id: int) -> Optional[DesignerAIRun]:
    return db_session.get(DesignerAIRun, run_id)


def update_ai_run(
    run_id: int,
    status: str,
    state_json: Optional[dict] = None,
    output_json: Optional[dict] = None,
    error_text: Optional[str] = None,
) -> Optional[DesignerAIRun]:
    run = db_session.get(DesignerAIRun, run_id)
    if not run:
        return None
    run.status = status
    if state_json is not None:
        run.state_json = state_json
    if output_json is not None:
        run.output_json = output_json
    if error_text is not None:
        run.error_text = error_text
    db_session.commit()
    db_session.refresh(run)
    return run


# ---------------------------------------------------------------------------
# Version helpers (DK-B7/B9)
# ---------------------------------------------------------------------------

def get_project_version(
    project_id: int,
    version_id: Optional[int] = None,
) -> Optional[DesignerProjectVersion]:
    """Get a specific project version, or the current version if version_id is None."""
    if version_id is not None:
        version = db_session.get(DesignerProjectVersion, version_id)
        if version and version.project_id == project_id:
            return version
        return None
    # Get current version via project
    project = db_session.get(DesignerProject, project_id)
    if not project or not project.current_version_id:
        return None
    return db_session.get(DesignerProjectVersion, project.current_version_id)


def save_design_version(
    project_id: int,
    design_json: dict,
    user_id: Optional[int] = None,
) -> Optional[DesignerProjectVersion]:
    """Save a new design version after hard validator passes.

    DK-B9: version save only after validator v2 gate.
    Returns None if validation fails.
    """
    from foms.services.designer.validator import validate_design
    result = validate_design(design_json)
    if not result.valid:
        return None
    return create_project_version(
        project_id=project_id,
        design_json=design_json,
        validation_json=result.to_dict(),
        user_id=user_id,
    )


# ---------------------------------------------------------------------------
# Corrections
# ---------------------------------------------------------------------------

def create_correction(
    before_json: dict,
    after_json: dict,
    reason_text: Optional[str] = None,
    project_id: Optional[int] = None,
    project_version_id: Optional[int] = None,
    ai_run_id: Optional[int] = None,
    user_id: Optional[int] = None,
) -> DesignerCorrection:
    correction = DesignerCorrection(
        project_id=project_id,
        project_version_id=project_version_id,
        ai_run_id=ai_run_id,
        before_json=before_json,
        after_json=after_json,
        reason_text=reason_text,
        created_by_user_id=user_id,
    )
    db_session.add(correction)
    db_session.commit()
    db_session.refresh(correction)
    return correction


# ---------------------------------------------------------------------------
# SketchUp Parse Jobs (B1)
# ---------------------------------------------------------------------------

# Worker queue contract (plan §3.3, §8.2):
# - Workers claim rows with `SELECT ... FOR UPDATE SKIP LOCKED` on the
#   (status, lease_expires_at, created_at) index.
# - Lease ownership (lease_owner, lease_token) must match on every mutation —
#   stale workers cannot smuggle in late results.
# - Presigned URLs are NEVER stored here; storage_keys_json carries opaque
#   storage object keys only.


def create_sketchup_job(
    *,
    artifact_id: int,
    parser_version: str,
    input_sha256: str,
    idempotency_key: str,
    project_id: Optional[int] = None,
    worker_kind: Optional[str] = None,
    storage_keys_json: Optional[dict] = None,
    user_id: Optional[int] = None,
    max_attempts: int = 3,
) -> DesignerSketchUpParseJob:
    """Insert a queued SketchUp parse job.

    `idempotency_key` is required and must be a stable hash of
    `(project_id, input_sha256, parser_code, analyzer_contract_version)`.
    The DB unique index will reject duplicates.
    """
    job = DesignerSketchUpParseJob(
        artifact_id=artifact_id,
        project_id=project_id,
        worker_kind=worker_kind,
        parser_version=parser_version,
        input_sha256=input_sha256,
        idempotency_key=idempotency_key,
        storage_keys_json=storage_keys_json or {},
        max_attempts=max_attempts,
        created_by_user_id=user_id,
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job


def get_sketchup_job(job_id: int) -> Optional[DesignerSketchUpParseJob]:
    return db_session.get(DesignerSketchUpParseJob, job_id)


def get_sketchup_job_by_idempotency_key(
    idempotency_key: str,
) -> Optional[DesignerSketchUpParseJob]:
    return (
        db_session.query(DesignerSketchUpParseJob)
        .filter(DesignerSketchUpParseJob.idempotency_key == idempotency_key)
        .one_or_none()
    )


def claim_sketchup_job(
    *,
    worker_id: str,
    initial_lease_seconds: int,
) -> Optional[DesignerSketchUpParseJob]:
    """Claim the next available job using PostgreSQL row-locking.

    Implements the §8.2 contract: pick the oldest `queued`/`retryable`
    row whose lease is null or expired, set status='running', stamp
    a fresh (lease_owner, lease_token), bump attempt_count.

    SQLite (used by unit tests) does not support `FOR UPDATE SKIP LOCKED`,
    so the helper falls back to a plain ORM query in that dialect — the
    serialized in-memory test DB makes contention impossible.
    """
    now = _utcnow()
    dialect = db_session.bind.dialect.name if db_session.bind else "postgresql"

    try:
        if dialect == "postgresql":
            row = db_session.execute(
                text(
                    """
                    SELECT id
                    FROM designer_sketchup_parse_jobs
                    WHERE status IN ('queued', 'retryable')
                      AND (lease_expires_at IS NULL OR lease_expires_at < :now)
                    ORDER BY created_at ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                    """
                ),
                {"now": now},
            ).first()
            if row is None:
                db_session.commit()
                return None
            job = db_session.get(DesignerSketchUpParseJob, row[0])
        else:
            job = (
                db_session.query(DesignerSketchUpParseJob)
                .filter(DesignerSketchUpParseJob.status.in_(("queued", "retryable")))
                .filter(
                    (DesignerSketchUpParseJob.lease_expires_at.is_(None))
                    | (DesignerSketchUpParseJob.lease_expires_at < now)
                )
                .order_by(DesignerSketchUpParseJob.created_at.asc())
                .first()
            )
            if job is None:
                db_session.commit()
                return None

        job.status = "running"
        job.lease_owner = worker_id
        job.lease_token = secrets.token_hex(32)
        job.lease_expires_at = now + timedelta(seconds=initial_lease_seconds)
        job.last_heartbeat_at = now
        job.attempt_count = (job.attempt_count or 0) + 1
        if job.started_at is None:
            job.started_at = now
        db_session.commit()
        db_session.refresh(job)
        return job
    except Exception:
        db_session.rollback()
        raise


def heartbeat_sketchup_job(
    *,
    job_id: int,
    lease_owner: str,
    lease_token: str,
    extension_seconds: int,
) -> Optional[DesignerSketchUpParseJob]:
    """Extend the lease on a running job. Returns None if ownership is stale.

    Stale-ownership returns None instead of raising so the worker can
    short-circuit gracefully (e.g. exit the loop) without provoking a
    rollback storm.
    """
    job = db_session.get(DesignerSketchUpParseJob, job_id)
    if job is None:
        return None
    if job.status != "running":
        return None
    if job.lease_owner != lease_owner or job.lease_token != lease_token:
        return None

    now = _utcnow()
    job.last_heartbeat_at = now
    job.lease_expires_at = now + timedelta(seconds=extension_seconds)
    db_session.commit()
    db_session.refresh(job)
    return job


def finish_sketchup_job(
    *,
    job_id: int,
    lease_owner: str,
    lease_token: str,
    status: str,
    finish_overrun_seconds: int,
    error_code: Optional[str] = None,
    error_text: Optional[str] = None,
    metrics_json: Optional[dict] = None,
    storage_keys_json: Optional[dict] = None,
) -> tuple[Optional[DesignerSketchUpParseJob], Optional[str]]:
    """Transition a running job to a terminal status with lease validation.

    Returns `(job_or_none, discard_reason_or_none)`. `discard_reason` is set
    when the worker's lease is stale or expired beyond the finish overrun;
    the job is forced to `retryable` and the worker payload is discarded
    (plan §3.3 fake-result discard policy).
    """
    if status not in {"succeeded", "failed", "cancelled", "retryable"}:
        raise ValueError(f"invalid finish status: {status!r}")

    job = db_session.get(DesignerSketchUpParseJob, job_id)
    if job is None:
        return None, "job_not_found"

    if job.lease_owner != lease_owner or job.lease_token != lease_token:
        # The result belongs to a worker that no longer owns this job.
        # Do not flip status here — another worker may legitimately be
        # processing it.
        return job, "stale_lease_owner"

    now = _utcnow()
    lease_expires = _as_utc(job.lease_expires_at)
    overrun_deadline = (
        lease_expires + timedelta(seconds=finish_overrun_seconds)
        if lease_expires is not None
        else None
    )
    if overrun_deadline is not None and now > overrun_deadline:
        # Worker came back after the allowed overrun — discard payload.
        job.status = "retryable"
        job.lease_owner = None
        job.lease_token = None
        job.lease_expires_at = None
        db_session.commit()
        db_session.refresh(job)
        return job, "lease_expired_overrun"

    job.status = status
    job.error_code = error_code
    job.error_text = error_text
    if metrics_json is not None:
        job.metrics_json = metrics_json
    if storage_keys_json is not None:
        job.storage_keys_json = storage_keys_json
    job.finished_at = now
    job.lease_owner = None
    job.lease_token = None
    job.lease_expires_at = None
    db_session.commit()
    db_session.refresh(job)
    return job, None


def create_sketchup_model_snapshot(
    *,
    artifact_id: int,
    parse_job_id: int,
    parser_version: str,
    units_json: dict,
    bbox_json: dict,
    raw_model_json: dict,
    layout_graph_json: dict,
    component_index_json: dict,
    material_index_json: dict,
    extraction_id: Optional[int] = None,
    sketchup_api_version: Optional[str] = None,
    sketchup_model_version: Optional[str] = None,
    load_status: Optional[str] = None,
    preview_assets_json: Optional[dict] = None,
    warnings_json: Optional[list[Any]] = None,
) -> DesignerSketchUpModelSnapshot:
    """Insert an immutable parse-time snapshot.

    Callers must validate `raw_model_json` against the
    `foms-sketchup-raw-v1` schema *before* invoking this helper; the
    intake pipeline rejects schema-invalid payloads and never produces a
    snapshot row in that case.
    """
    snapshot = DesignerSketchUpModelSnapshot(
        artifact_id=artifact_id,
        parse_job_id=parse_job_id,
        extraction_id=extraction_id,
        parser_version=parser_version,
        sketchup_api_version=sketchup_api_version,
        sketchup_model_version=sketchup_model_version,
        load_status=load_status,
        units_json=units_json,
        bbox_json=bbox_json,
        raw_model_json=raw_model_json,
        layout_graph_json=layout_graph_json,
        component_index_json=component_index_json,
        material_index_json=material_index_json,
        preview_assets_json=preview_assets_json,
        warnings_json=warnings_json or [],
    )
    db_session.add(snapshot)
    db_session.commit()
    db_session.refresh(snapshot)
    return snapshot
