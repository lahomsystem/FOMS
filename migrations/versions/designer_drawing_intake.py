"""PG-B3: Drawing Intake + Persistent Extraction Data Model.

Adds four new tables:
  designer_drawing_artifacts   — raw drawing file record
  designer_drawing_pages       — per-page breakdown (PDF support)
  designer_drawing_extractions — Gemini extraction result per page
  designer_extraction_candidates — DesignGraphCandidate from extraction

Contract:
- intake does NOT create a project version.
- candidates are never auto-approved.
- approved=False until human review.

Revision ID: designer_drawing_intake
Revises: designer_pgvector
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "designer_drawing_intake"
down_revision = "designer_pgvector"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── designer_drawing_artifacts ──────────────────────────
    op.create_table(
        "designer_drawing_artifacts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("designer_projects.id"), nullable=True),
        sa.Column("attachment_id", sa.Integer(), nullable=True),
        sa.Column("file_url", sa.String(2000), nullable=False),
        sa.Column("file_type", sa.String(20), nullable=False, server_default="jpg"),
        sa.Column("page_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("source", sa.String(50), nullable=False, server_default="upload"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )
    op.create_index("ix_drawing_artifacts_project_id", "designer_drawing_artifacts", ["project_id"])
    op.create_index("ix_drawing_artifacts_status", "designer_drawing_artifacts", ["status"])

    # ── designer_drawing_pages ──────────────────────────────
    op.create_table(
        "designer_drawing_pages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("artifact_id", sa.Integer(),
                  sa.ForeignKey("designer_drawing_artifacts.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("page_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("image_url", sa.String(2000), nullable=True),
        sa.Column("width_px", sa.Integer(), nullable=True),
        sa.Column("height_px", sa.Integer(), nullable=True),
        sa.Column("rotation_deg", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("template_key", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )
    op.create_index("ix_drawing_pages_artifact_id", "designer_drawing_pages", ["artifact_id"])

    # ── designer_drawing_extractions ────────────────────────
    op.create_table(
        "designer_drawing_extractions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("page_id", sa.Integer(),
                  sa.ForeignKey("designer_drawing_pages.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("extractor_version", sa.String(50), nullable=False, server_default="gemini-v1"),
        sa.Column("raw_ocr_json", sa.JSON(), nullable=True),
        sa.Column("layout_json", sa.JSON(), nullable=True),
        sa.Column("parsed_json", sa.JSON(), nullable=True),
        sa.Column("confidence_json", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
        sa.Column("approved_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("model_name", sa.String(100), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )
    op.create_index("ix_drawing_extractions_page_id", "designer_drawing_extractions", ["page_id"])
    op.create_index("ix_drawing_extractions_status", "designer_drawing_extractions", ["status"])

    # ── designer_extraction_candidates ─────────────────────
    op.create_table(
        "designer_extraction_candidates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("extraction_id", sa.Integer(),
                  sa.ForeignKey("designer_drawing_extractions.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("furniture_type", sa.String(50), nullable=False),
        sa.Column("extracted_params_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("unresolved_fields_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("approved", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("approved_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )
    op.create_index("ix_extraction_candidates_extraction_id",
                    "designer_extraction_candidates", ["extraction_id"])
    op.create_index("ix_extraction_candidates_approved",
                    "designer_extraction_candidates", ["approved"])


def downgrade() -> None:
    op.drop_table("designer_extraction_candidates")
    op.drop_table("designer_drawing_extractions")
    op.drop_table("designer_drawing_pages")
    op.drop_table("designer_drawing_artifacts")
