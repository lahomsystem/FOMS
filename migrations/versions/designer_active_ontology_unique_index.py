"""Enhancement: active ontology partial unique index.

Ensures at most one row has status='active' in designer_ontology_versions.
This is a DB-level enforcement of the active ontology invariant.

Revision ID: designer_active_ontology_uq
Revises: designer_design_case_memory
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "designer_active_ontology_uq"
down_revision = "designer_design_case_memory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Partial unique index: only one row can have status='active'
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS
          uq_designer_ontology_single_active
        ON designer_ontology_versions (status)
        WHERE status = 'active'
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP INDEX IF EXISTS uq_designer_ontology_single_active"
    )
