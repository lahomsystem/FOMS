"""merge order_drafts and designer_sketchup_intake Alembic heads

Revision ID: merge_p0_order_drafts_sketchup
Revises: add_order_drafts_table, designer_sketchup_intake
Create Date: 2026-05-30

"""
from typing import Sequence, Union

revision: str = "merge_p0_order_drafts_sketchup"
down_revision: Union[str, Sequence[str], None] = (
    "add_order_drafts_table",
    "designer_sketchup_intake",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No-op merge — unifies parallel branches from designer_c0_lego_ontology."""


def downgrade() -> None:
    """No-op merge downgrade."""
