"""WDPlanner V2 Remediation — candidate status, blocking_reasons, routing metadata, design case source link.

Adds:
- designer_drawing_extractions.routing_json: routing metadata from model_router
- designer_drawing_extractions.redaction_report_json: PII policy report
- designer_extraction_candidates.status: lifecycle enum
- designer_extraction_candidates.blocking_reasons_json: computed gate reasons
- designer_design_cases.source_candidate_id: FK to originating candidate

Revision ID: designer_wdplanner_v2_remediation
Revises: designer_eval_snapshots
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "designer_wdplanner_v2_remediation"
down_revision = "designer_eval_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # designer_drawing_extractions: routing + redaction report
    op.add_column(
        "designer_drawing_extractions",
        sa.Column("routing_json", sa.JSON(), nullable=True),
    )
    op.add_column(
        "designer_drawing_extractions",
        sa.Column("redaction_report_json", sa.JSON(), nullable=True),
    )

    # designer_extraction_candidates: status lifecycle + blocking reasons
    op.add_column(
        "designer_extraction_candidates",
        sa.Column(
            "status",
            sa.Enum(
                "pending_review", "corrected", "rejected", "approved",
                name="designer_candidate_status",
                native_enum=False,
            ),
            nullable=False,
            server_default="pending_review",
        ),
    )
    op.add_column(
        "designer_extraction_candidates",
        sa.Column("blocking_reasons_json", sa.JSON(), nullable=False, server_default="[]"),
    )

    # designer_design_cases: source candidate provenance
    op.add_column(
        "designer_design_cases",
        sa.Column(
            "source_candidate_id",
            sa.Integer(),
            sa.ForeignKey("designer_extraction_candidates.id"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("designer_design_cases", "source_candidate_id")
    op.drop_column("designer_extraction_candidates", "blocking_reasons_json")
    op.drop_column("designer_extraction_candidates", "status")
    op.drop_column("designer_drawing_extractions", "redaction_report_json")
    op.drop_column("designer_drawing_extractions", "routing_json")
