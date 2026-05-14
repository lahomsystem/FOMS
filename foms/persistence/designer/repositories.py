"""FOMS Brain AX Designer – repository helpers."""

from __future__ import annotations

from typing import Optional

from db import db_session
from foms.persistence.designer.models import (
    DesignerAIRun,
    DesignerCorrection,
    DesignerOntologyVersion,
    DesignerProject,
    DesignerProjectVersion,
)


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
