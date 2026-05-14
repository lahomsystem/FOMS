"""FOMS Brain AX Designer – SQLAlchemy ORM models.

Uses JSON type for cross-DB compatibility (PostgreSQL uses JSONB via dialect
type coercion; SQLite uses JSON for tests).
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class DesignerProject(Base):
    """Top-level design project – may be linked to an ERP order."""

    __tablename__ = "designer_projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("orders.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    current_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    versions: Mapped[list[DesignerProjectVersion]] = relationship(
        "DesignerProjectVersion", back_populates="project", cascade="all, delete-orphan"
    )


class DesignerProjectVersion(Base):
    """Immutable snapshot of a design at a point in time."""

    __tablename__ = "designer_project_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("designer_projects.id"), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    ontology_version_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("designer_ontology_versions.id"), nullable=True)
    design_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    validation_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    bom_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    project: Mapped[DesignerProject] = relationship("DesignerProject", back_populates="versions")
    ontology_version: Mapped[DesignerOntologyVersion | None] = relationship("DesignerOntologyVersion")


class DesignerOntologyVersion(Base):
    """Versioned design rule ontology – AI may NOT promote directly to active."""

    __tablename__ = "designer_ontology_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(
        Enum("active", "draft", "retired", name="designer_ontology_status", native_enum=False),
        nullable=False,
        default="draft",
    )
    rules_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class DesignerAIRunStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    interrupt = "interrupt"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class DesignerAIRun(Base):
    """Record of a LangGraph workflow execution."""

    __tablename__ = "designer_ai_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    graph_name: Mapped[str] = mapped_column(String(100), nullable=False)
    graph_version: Mapped[str] = mapped_column(String(50), nullable=False, default="0.1.0")
    thread_id: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(
            "queued", "running", "interrupt", "succeeded", "failed", "cancelled",
            name="designer_ai_run_status",
            native_enum=False,
        ),
        nullable=False,
        default="queued",
    )
    input_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    state_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    output_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)


class DesignerCorrection(Base):
    """Audit log of AI-proposed and human-approved design changes."""

    __tablename__ = "designer_corrections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("designer_projects.id"), nullable=True)
    project_version_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("designer_project_versions.id"), nullable=True)
    ai_run_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("designer_ai_runs.id"), nullable=True)
    before_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    after_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    reason_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class DesignerRuleCandidate(Base):
    """AI-extracted rule upgrade candidate – must be human-approved before promotion."""

    __tablename__ = "designer_rule_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_correction_ids: Mapped[dict] = mapped_column(JSON, nullable=False, default=list)
    candidate_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    replay_report_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum("draft", "approved", "rejected", "promoted", name="designer_rule_candidate_status", native_enum=False),
        nullable=False,
        default="draft",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class DesignerEmbedding(Base):
    """Vector embedding store for design memory (text + optional vector)."""

    __tablename__ = "designer_embeddings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_type: Mapped[str] = mapped_column(String(100), nullable=False)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # embedding column added in separate pgvector migration (B7)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


# ──────────────────────────────────────────────────────────
# PG-B3: Drawing Intake Data Models
# ──────────────────────────────────────────────────────────

class DesignerDrawingArtifact(Base):
    """Raw drawing file attached to a project. Intake does NOT create a project version.

    A drawing artifact is immutable — the original file is never modified.
    Extraction results are stored in DesignerDrawingExtraction separately.
    """

    __tablename__ = "designer_drawing_artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("designer_projects.id"), nullable=True
    )
    attachment_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # FOMS attachment
    file_url: Mapped[str] = mapped_column(String(2000), nullable=False)
    file_type: Mapped[str] = mapped_column(
        Enum("jpg", "jpeg", "png", "pdf", "webp", name="designer_drawing_file_type", native_enum=False),
        nullable=False, default="jpg",
    )
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    source: Mapped[str] = mapped_column(
        Enum("upload", "erp_attachment", "manual", name="designer_drawing_source", native_enum=False),
        nullable=False, default="upload",
    )
    status: Mapped[str] = mapped_column(
        Enum("pending", "processing", "done", "error",
             name="designer_drawing_artifact_status", native_enum=False),
        nullable=False, default="pending",
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    pages: Mapped[list["DesignerDrawingPage"]] = relationship(
        "DesignerDrawingPage", back_populates="artifact", cascade="all, delete-orphan"
    )


class DesignerDrawingPage(Base):
    """Single page of a drawing artifact (PDF may have multiple pages)."""

    __tablename__ = "designer_drawing_pages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    artifact_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("designer_drawing_artifacts.id"), nullable=False
    )
    page_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    image_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    width_px: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height_px: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rotation_deg: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    template_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    artifact: Mapped[DesignerDrawingArtifact] = relationship("DesignerDrawingArtifact", back_populates="pages")
    extractions: Mapped[list["DesignerDrawingExtraction"]] = relationship(
        "DesignerDrawingExtraction", back_populates="page", cascade="all, delete-orphan"
    )


class DesignerDrawingExtraction(Base):
    """Extraction run result for one drawing page. Never auto-approved.

    Includes raw model output, parsed structured data, and confidence.
    Human review required before project version creation.
    """

    __tablename__ = "designer_drawing_extractions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    page_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("designer_drawing_pages.id"), nullable=False
    )
    extractor_version: Mapped[str] = mapped_column(String(50), nullable=False, default="gemini-v1")
    raw_ocr_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    layout_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    parsed_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    confidence_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum("draft", "pending_approval", "approved", "rejected",
             name="designer_extraction_status", native_enum=False),
        nullable=False, default="draft",
    )
    approved_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    page: Mapped[DesignerDrawingPage] = relationship("DesignerDrawingPage", back_populates="extractions")
    candidates: Mapped[list["DesignerExtractionCandidate"]] = relationship(
        "DesignerExtractionCandidate", back_populates="extraction", cascade="all, delete-orphan"
    )


class DesignerExtractionCandidate(Base):
    """Design graph candidate generated from a drawing extraction.

    Never auto-applied. Requires human approval before project version creation.
    unresolved_fields must be empty before approval is permitted.
    """

    __tablename__ = "designer_extraction_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    extraction_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("designer_drawing_extractions.id"), nullable=False
    )
    furniture_type: Mapped[str] = mapped_column(String(50), nullable=False)
    extracted_params_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    unresolved_fields_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    confidence: Mapped[float] = mapped_column(nullable=False, default=0.0)
    approved: Mapped[bool] = mapped_column(nullable=False, default=False)
    approved_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # correction_deltas stored in DesignerCorrection linked to this candidate
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    extraction: Mapped[DesignerDrawingExtraction] = relationship(
        "DesignerDrawingExtraction", back_populates="candidates"
    )
