"""merge account_self_00 and typedrift_00 Alembic heads

Revision ID: merge_acct_typedrift
Revises: account_self_00, typedrift_00
Create Date: 2026-08-06

"""
from typing import Sequence, Union

revision: str = "merge_acct_typedrift"
down_revision: Union[str, Sequence[str], None] = (
    "account_self_00",
    "typedrift_00",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No-op merge — unifies parallel branches from wiz_pending_00."""


def downgrade() -> None:
    """No-op merge downgrade."""
