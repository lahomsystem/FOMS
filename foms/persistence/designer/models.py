"""FOMS Brain AX Designer – SQLAlchemy ORM models.

Uses JSON type for cross-DB compatibility (PostgreSQL uses JSONB via dialect
type coercion; SQLite uses JSON for tests).
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
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

    SketchUp note: `.skp`/`.skb` uploads reuse this artifact table via
    `file_type` ∈ {"skp", "skb"} and `source` ∈ {"sketchup_upload"}. The
    underlying parse job lives in `designer_sketchup_parse_jobs` and the
    resulting model snapshot in `designer_sketchup_model_snapshots`.
    `analysis_kind` distinguishes drawing image vs. sketchup model so the
    intake pipeline can branch without sniffing extensions at runtime.
    """

    __tablename__ = "designer_drawing_artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("designer_projects.id"), nullable=True
    )
    attachment_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # FOMS attachment
    file_url: Mapped[str] = mapped_column(String(2000), nullable=False)
    file_type: Mapped[str] = mapped_column(
        Enum(
            "jpg", "jpeg", "png", "pdf", "webp", "skp", "skb",
            name="designer_drawing_file_type",
            native_enum=False,
        ),
        nullable=False, default="jpg",
    )
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    source: Mapped[str] = mapped_column(
        Enum(
            "upload", "erp_attachment", "manual", "sketchup_upload", "sketchup_worker",
            name="designer_drawing_source",
            native_enum=False,
        ),
        nullable=False, default="upload",
    )
    status: Mapped[str] = mapped_column(
        Enum("pending", "processing", "done", "error",
             name="designer_drawing_artifact_status", native_enum=False),
        nullable=False, default="pending",
    )
    # SketchUp intake extension (also useful as audit metadata for legacy
    # drawing uploads). Nullable so existing rows stay valid.
    original_filename: Mapped[str | None] = mapped_column(String(500), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(200), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    analysis_kind: Mapped[str | None] = mapped_column(String(50), nullable=True)

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
    routing_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    redaction_report_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
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
    status: Mapped[str] = mapped_column(
        Enum(
            "pending_review", "corrected", "rejected", "approved",
            name="designer_candidate_status",
            native_enum=False,
        ),
        nullable=False,
        default="pending_review",
    )
    blocking_reasons_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # B2: layout_graph_mapper result — 3D preview contract
    # NULL on legacy rows (pre-B2) → use review_status='legacy_requires_reextract'
    design_graph_candidate_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    mapping_report_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    validation_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    preview_allowed: Mapped[bool] = mapped_column(nullable=False, default=False)

    # Preview ack ledger — source of truth for the approval gate.
    # The 3D editor must post-ack a load and the API records the canonical
    # SHA256 of design_graph_candidate_json at that moment. Approval is
    # rejected if the current candidate hash diverges from last_preview_ack_hash
    # or if last_preview_ack_error is non-null.
    last_preview_ack_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_preview_ack_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_preview_ack_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # correction_deltas stored in DesignerCorrection linked to this candidate
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    extraction: Mapped[DesignerDrawingExtraction] = relationship(
        "DesignerDrawingExtraction", back_populates="candidates"
    )

    def is_legacy(self) -> bool:
        """True if this candidate was created before B2 and lacks graph payload."""
        return self.design_graph_candidate_json is None

    def can_preview(self) -> bool:
        """True if 3D editor can load this candidate."""
        return self.preview_allowed and not self.is_legacy()

    def can_approve(self) -> bool:
        """True if approve-and-save is permitted (not legacy, no blocking reasons)."""
        return (
            not self.is_legacy()
            and self.status not in ("rejected", "approved", "promoted_to_project_version")
            and not self.blocking_reasons_json
            and self.preview_allowed
        )


# ──────────────────────────────────────────────────────────
# PG-L1: Design Case Memory
# ──────────────────────────────────────────────────────────

class DesignerDesignCase(Base):
    """PG-L1: Approved design case — the core learning asset.

    Stores every human-approved, validator-passed design together with its
    provenance so future requests can retrieve similar cases.

    Contract:
    - Only created after project_version_id exists (validator passed).
    - Only created after an approved extraction or direct approval action.
    - raw PII fields (customer_name, phone, address) are NOT stored here;
      they remain in DesignerDrawingExtraction / DesignerDrawingArtifact.
    - design_graph_json, bom_json, options_json, internal_structure_json are
      safe to include in retrieval payloads (no PII).
    - AI MUST NOT create DesignerDesignCase directly; service layer only.
    """

    __tablename__ = "designer_design_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Provenance
    project_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("designer_projects.id"), nullable=True
    )
    project_version_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("designer_project_versions.id"), nullable=True
    )
    drawing_artifact_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("designer_drawing_artifacts.id"), nullable=True
    )
    approved_extraction_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("designer_drawing_extractions.id"), nullable=True
    )
    source_candidate_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("designer_extraction_candidates.id"), nullable=True
    )

    # Classification — safe for retrieval / no PII
    furniture_type: Mapped[str] = mapped_column(String(50), nullable=False)
    product_name: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Design payload — PII-free
    design_graph_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    bom_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    options_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    internal_structure_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    tags_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # Dimensions — for similarity search without opening the full graph
    width_mm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height_mm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    depth_mm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    module_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Quality signal
    source_quality_score: Mapped[float] = mapped_column(
        Float, nullable=False, default=1.0
    )

    # Approval metadata
    approval_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )


# ──────────────────────────────────────────────────────────
# C0: Contract Freeze — Lego Ontology & Reusable Block Schema
# ──────────────────────────────────────────────────────────


class DesignerReusableBlock(Base):
    """C0: Reusable geometry block — the Lego brick of the design system.

    A block encapsulates a geometry subset (components + relations) that
    can be stamped into any design graph. Blocks must be human-approved
    before use (status='approved').

    Contract:
    - block_key is the stable identifier referenced by ontology relations.
    - geometry_json stores a components+relations subset conforming to
      geometry_schema_version (currently "v2").
    - parameters_json defines the adjustable variables (width_range, etc.)
      that the stamper resolves at call time.
    - auto_generated=True blocks are AI-proposed and require approval.
    - AI MUST NOT auto-promote blocks to approved; service layer only.
    """

    __tablename__ = "designer_reusable_blocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    block_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    label_ko: Mapped[str] = mapped_column(String(200), nullable=False)
    label_en: Mapped[str | None] = mapped_column(String(200), nullable=True)
    category: Mapped[str] = mapped_column(
        Enum("panel", "module", "assembly", "hardware", "other",
             name="designer_block_category", native_enum=False),
        nullable=False,
        default="panel",
    )
    geometry_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    parameters_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    geometry_schema_version: Mapped[str] = mapped_column(String(20), nullable=False, default="v2")
    status: Mapped[str] = mapped_column(
        Enum("draft", "approved", "rejected", "retired",
             name="designer_block_status", native_enum=False),
        nullable=False,
        default="draft",
    )
    auto_generated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    usage_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tags_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    source_design_case_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("designer_design_cases.id"), nullable=True
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    approved_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )


class DesignerBlockOntologyVersion(Base):
    """C0: Versioned snapshot of the block relation ontology.

    Each version captures a coherent set of block-to-block relations
    (DesignerBlockOntologyRelation). Only one version may be 'active'
    at a time. AI MUST NOT promote a version to active; service layer only.
    """

    __tablename__ = "designer_block_ontology_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(
        Enum("draft", "active", "retired",
             name="designer_block_ontology_version_status", native_enum=False),
        nullable=False,
        default="draft",
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    approved_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    relations: Mapped[list["DesignerBlockOntologyRelation"]] = relationship(
        "DesignerBlockOntologyRelation",
        back_populates="ontology_version",
        cascade="all, delete-orphan",
    )


class DesignerBlockOntologyRelation(Base):
    """C0: A single block-to-block relation within an ontology version.

    Captures how one block connects to another (contains, attaches_to, etc.)
    and the evidence cases that support the relation.

    Status lifecycle: candidate → approved / rejected → promoted
    AI MUST NOT set status='approved' directly; service layer only.
    """

    __tablename__ = "designer_block_ontology_relations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ontology_version_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("designer_block_ontology_versions.id"), nullable=False
    )
    relation_key: Mapped[str] = mapped_column(String(200), nullable=False)
    from_block_key: Mapped[str] = mapped_column(String(100), nullable=False)
    to_block_key: Mapped[str] = mapped_column(String(100), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(50), nullable=False)
    params_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    evidence_case_ids_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    replay_report_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum("candidate", "approved", "rejected", "promoted",
             name="designer_block_relation_status", native_enum=False),
        nullable=False,
        default="candidate",
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    approved_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    ontology_version: Mapped[DesignerBlockOntologyVersion] = relationship(
        "DesignerBlockOntologyVersion", back_populates="relations"
    )


class DesignerComponentExplanation(Base):
    """C0: Human-readable rationale for a single graph component.

    Stores PII-redacted explanation text and the rationale category so
    retrieval can surface 'why this component exists' alongside the design.

    embedding_id links to a pre-computed vector for semantic search.
    AI MUST NOT approve explanations directly; service layer only.
    """

    __tablename__ = "designer_component_explanations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    design_case_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("designer_design_cases.id"), nullable=True
    )
    component_id_in_graph: Mapped[str] = mapped_column(String(200), nullable=False)
    explanation_text: Mapped[str] = mapped_column(Text, nullable=False)
    rationale_category: Mapped[str] = mapped_column(
        Enum("constraint", "preference", "customer_request", "codified_rule", "other",
             name="designer_explanation_rationale", native_enum=False),
        nullable=False,
        default="other",
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    usage_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(
        Enum("draft", "approved", "rejected", "retired",
             name="designer_explanation_status", native_enum=False),
        nullable=False,
        default="draft",
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    approved_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    embedding_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("designer_embeddings.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )


class DesignerOutlinePolygon(Base):
    """C0: Outline polygon extracted from a drawing for a given view.

    Captures the silhouette of a furniture piece in front/side/top view
    as an ordered vertex list in millimetres. Used by the Lego stamper to
    validate that assembled blocks match the client drawing.

    Validation (is_valid) confirms the polygon is closed and self-intersection-free.
    AI MUST NOT set is_valid=True without calling the geometry validator service.
    """

    __tablename__ = "designer_outline_polygons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    extraction_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("designer_drawing_extractions.id"), nullable=False
    )
    view: Mapped[str] = mapped_column(String(20), nullable=False, default="front")
    vertices_mm_json: Mapped[list] = mapped_column(JSON, nullable=False)
    shape_type: Mapped[str] = mapped_column(String(50), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    area_mm2: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    validation_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum("pending", "validated", "rejected",
             name="designer_polygon_status", native_enum=False),
        nullable=False,
        default="pending",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


# ──────────────────────────────────────────────────────────
# B1: SketchUp Intake — parse job + raw model snapshot
# ──────────────────────────────────────────────────────────


class DesignerSketchUpParseJob(Base):
    """SketchUp parse job — PostgreSQL row-locking queue contract.

    Workers claim jobs with `SELECT ... FOR UPDATE SKIP LOCKED` keyed on
    `(status, lease_expires_at, created_at)`. Lease ownership is asserted
    on every status mutation via (`lease_owner`, `lease_token`) so an
    expired worker cannot smuggle in a stale `succeeded` payload — late
    results are discarded and the job is moved to `retryable`.

    `idempotency_key` is a stable hash of
    `(project_id, input_sha256, parser_code, analyzer_contract_version)`.
    The DB enforces uniqueness so reuploading the same model on the same
    parser version returns the existing job instead of creating a new one.

    Presigned storage URLs are NEVER persisted here. `storage_keys_json`
    only carries opaque storage object keys + their artifact role. Workers
    re-request short-lived presigned URLs from the API endpoint guarded by
    lease ownership.
    """

    __tablename__ = "designer_sketchup_parse_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    artifact_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("designer_drawing_artifacts.id"), nullable=False
    )
    project_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("designer_projects.id"), nullable=True
    )

    status: Mapped[str] = mapped_column(
        Enum(
            "queued", "running", "succeeded", "failed", "cancelled", "retryable",
            name="designer_sketchup_job_status",
            native_enum=False,
        ),
        nullable=False,
        default="queued",
    )
    worker_kind: Mapped[str | None] = mapped_column(
        Enum(
            "c_api", "desktop_ruby", "fake_contract",
            name="designer_sketchup_worker_kind",
            native_enum=False,
        ),
        nullable=True,
    )

    parser_version: Mapped[str] = mapped_column(String(100), nullable=False)
    input_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    # 255 chars accommodates future parser code + analyzer_contract_version
    # combinations. Plan §4.2.2 invariant: idempotency_key is a hash, not
    # the raw parser version string.
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)

    lease_owner: Mapped[str | None] = mapped_column(String(120), nullable=True)
    lease_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)

    storage_keys_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    metrics_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DesignerSketchUpModelSnapshot(Base):
    """Immutable parse-time snapshot for a successful SketchUp parse job.

    Stores the canonical `SketchUpRawModelJson` payload alongside derived
    indexes (component, material, preview asset references) that the
    intake pipeline consumes when building a `DesignerExtractionCandidate`.

    A snapshot is only inserted after schema validation succeeds. Schema
    invalid analyzer output causes the parse job to transition to
    `failed`/`retryable` without leaving partial snapshot rows behind.
    """

    __tablename__ = "designer_sketchup_model_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    artifact_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("designer_drawing_artifacts.id"), nullable=False
    )
    parse_job_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("designer_sketchup_parse_jobs.id"), nullable=False
    )
    extraction_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("designer_drawing_extractions.id"), nullable=True
    )

    parser_version: Mapped[str] = mapped_column(String(100), nullable=False)
    sketchup_api_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sketchup_model_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    load_status: Mapped[str | None] = mapped_column(String(100), nullable=True)

    units_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    bbox_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    raw_model_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    layout_graph_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    component_index_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    material_index_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    preview_assets_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    warnings_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
