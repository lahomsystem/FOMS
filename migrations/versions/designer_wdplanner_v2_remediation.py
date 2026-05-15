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
    # IF NOT EXISTS 사용 — 이전 배포에서 부분 적용된 경우에도 안전하게 재실행 가능
    op.execute(
        "ALTER TABLE designer_drawing_extractions "
        "ADD COLUMN IF NOT EXISTS routing_json JSON"
    )
    op.execute(
        "ALTER TABLE designer_drawing_extractions "
        "ADD COLUMN IF NOT EXISTS redaction_report_json JSON"
    )
    op.execute(
        "ALTER TABLE designer_extraction_candidates "
        "ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'pending_review'"
    )
    op.execute(
        "ALTER TABLE designer_extraction_candidates "
        "ADD COLUMN IF NOT EXISTS blocking_reasons_json JSON NOT NULL DEFAULT '[]'"
    )
    op.execute(
        "ALTER TABLE designer_design_cases "
        "ADD COLUMN IF NOT EXISTS source_candidate_id INTEGER "
        "REFERENCES designer_extraction_candidates(id)"
    )


def downgrade() -> None:
    op.drop_column("designer_design_cases", "source_candidate_id")
    op.drop_column("designer_extraction_candidates", "blocking_reasons_json")
    op.drop_column("designer_extraction_candidates", "status")
    op.drop_column("designer_drawing_extractions", "redaction_report_json")
    op.drop_column("designer_drawing_extractions", "routing_json")
