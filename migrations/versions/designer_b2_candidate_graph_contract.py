"""B2: DesignerExtractionCandidate — layout_graph_mapper 결과 컬럼 추가.

Adds 4 columns to designer_extraction_candidates:
  design_graph_candidate_json  — mapped DesignGraph (schema v2) JSON
  mapping_report_json          — mapping warnings / unresolved / evidence
  validation_json              — constraint validator result
  preview_allowed              — True if 3D editor can load this candidate

Backfill policy for existing rows (legacy candidates):
  design_graph_candidate_json  = NULL    (forces is_legacy() → True)
  mapping_report_json          = {"warnings": ["legacy_candidate_requires_reextract"]}
  validation_json              = {}
  preview_allowed              = FALSE
  blocking_reasons_json        — if currently [] then set to ["legacy_candidate_requires_reextract"]

Legacy rows will return HTTP 422 + legacy_candidate_requires_reextract from approve API.

Revision ID: designer_b2_graph_contract
Revises: designer_wdplanner_v2_fix
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "designer_b2_graph_contract"
down_revision = "designer_wdplanner_v2_fix"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ADD COLUMN IF NOT EXISTS — safe for partial re-runs
    op.execute(
        "ALTER TABLE designer_extraction_candidates "
        "ADD COLUMN IF NOT EXISTS design_graph_candidate_json JSON"
    )
    op.execute(
        "ALTER TABLE designer_extraction_candidates "
        "ADD COLUMN IF NOT EXISTS mapping_report_json JSON"
    )
    op.execute(
        "ALTER TABLE designer_extraction_candidates "
        "ADD COLUMN IF NOT EXISTS validation_json JSON"
    )
    op.execute(
        "ALTER TABLE designer_extraction_candidates "
        "ADD COLUMN IF NOT EXISTS preview_allowed BOOLEAN NOT NULL DEFAULT FALSE"
    )

    # Backfill existing rows with legacy markers
    op.execute(
        """
        UPDATE designer_extraction_candidates
        SET
            mapping_report_json = '{"warnings": ["legacy_candidate_requires_reextract"]}'::json,
            validation_json = '{}'::json,
            preview_allowed = FALSE,
            blocking_reasons_json = CASE
                WHEN blocking_reasons_json::text = '[]'
                THEN '["legacy_candidate_requires_reextract"]'::json
                ELSE blocking_reasons_json
            END
        WHERE design_graph_candidate_json IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("designer_extraction_candidates", "preview_allowed")
    op.drop_column("designer_extraction_candidates", "validation_json")
    op.drop_column("designer_extraction_candidates", "mapping_report_json")
    op.drop_column("designer_extraction_candidates", "design_graph_candidate_json")
