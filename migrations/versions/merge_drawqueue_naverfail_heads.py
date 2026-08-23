"""merge drawqueue_00 and naverfail_00 Alembic heads

Revision ID: merge_drawq_naverfail
Revises: drawqueue_00, naverfail_00
Create Date: 2026-08-23

"""
from typing import Sequence, Union

revision: str = "merge_drawq_naverfail"
down_revision: Union[str, Sequence[str], None] = (
    "drawqueue_00",
    "naverfail_00",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No-op merge — 동시 세션 분기(도면 큐 인덱스 / 네이버 실패 인덱스) 통합."""


def downgrade() -> None:
    """No-op merge downgrade."""
