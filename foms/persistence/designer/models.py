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
