"""Enhancement: monthly self-evaluation snapshot persistence.

Stores monthly self-evaluation snapshots in DB so trend analysis
is possible across months.

Revision ID: designer_eval_snapshots
Revises: designer_active_ontology_unique_index
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "designer_eval_snapshots"
down_revision = "designer_active_ontology_unique_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "designer_eval_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("period", sa.String(10), nullable=False),  # "2026-05"
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("extraction_correction_rate", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("candidate_approval_rate", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("rule_candidate_pass_rate", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("design_cases_accumulated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_archetype_candidates", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_extraction_cost_usd", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("overall_health_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("regression_detected", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("notes_json", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.create_index("ix_eval_snapshots_period", "designer_eval_snapshots", ["period"])
    op.create_index("ix_eval_snapshots_captured_at", "designer_eval_snapshots", ["captured_at"])


def downgrade() -> None:
    op.drop_table("designer_eval_snapshots")
