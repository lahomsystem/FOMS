"""PG-L1: Design Case Memory — designer_design_cases table.

Stores human-approved, validator-passed design cases as the core
learning asset for Retrieval-Augmented Design Brain (PG-L2).

Contract:
- Only rows created after project_version_id exists (validator passed).
- No raw PII fields stored (customer_name/phone/address stay in extraction).
- design_graph_json/bom_json/options_json are PII-free retrieval payloads.
- Dimensions (width_mm/height_mm/depth_mm) enable fast similarity queries.

Revision ID: designer_design_case_memory
Revises: designer_drawing_intake
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "designer_design_case_memory"
down_revision = "designer_drawing_intake"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "designer_design_cases",
        sa.Column("id", sa.Integer(), primary_key=True),

        # Provenance
        sa.Column("project_id", sa.Integer(),
                  sa.ForeignKey("designer_projects.id"), nullable=True),
        sa.Column("project_version_id", sa.Integer(),
                  sa.ForeignKey("designer_project_versions.id"), nullable=True),
        sa.Column("drawing_artifact_id", sa.Integer(),
                  sa.ForeignKey("designer_drawing_artifacts.id"), nullable=True),
        sa.Column("approved_extraction_id", sa.Integer(),
                  sa.ForeignKey("designer_drawing_extractions.id"), nullable=True),

        # Classification (PII-free)
        sa.Column("furniture_type", sa.String(50), nullable=False),
        sa.Column("product_name", sa.String(200), nullable=True),

        # Design payload (PII-free)
        sa.Column("design_graph_json", sa.JSON(), nullable=False,
                  server_default="{}"),
        sa.Column("bom_json", sa.JSON(), nullable=True),
        sa.Column("options_json", sa.JSON(), nullable=True),
        sa.Column("internal_structure_json", sa.JSON(), nullable=True),
        sa.Column("tags_json", sa.JSON(), nullable=False, server_default="[]"),

        # Fast similarity dimensions
        sa.Column("width_mm", sa.Integer(), nullable=True),
        sa.Column("height_mm", sa.Integer(), nullable=True),
        sa.Column("depth_mm", sa.Integer(), nullable=True),
        sa.Column("module_count", sa.Integer(), nullable=True),

        # Quality
        sa.Column("source_quality_score", sa.Float(), nullable=False,
                  server_default="1.0"),

        # Approval
        sa.Column("approval_user_id", sa.Integer(),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )

    # Indexes for similarity retrieval
    op.create_index("ix_design_cases_furniture_type",
                    "designer_design_cases", ["furniture_type"])
    op.create_index("ix_design_cases_project_id",
                    "designer_design_cases", ["project_id"])
    op.create_index("ix_design_cases_width_mm",
                    "designer_design_cases", ["width_mm"])
    op.create_index("ix_design_cases_created_at",
                    "designer_design_cases", ["created_at"])


def downgrade() -> None:
    op.drop_table("designer_design_cases")
