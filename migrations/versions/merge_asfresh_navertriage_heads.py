"""merge asfresh_00 and naver_triage_00 Alembic heads

Revision ID: merge_asfresh_naver
Revises: asfresh_00, naver_triage_00
Create Date: 2026-08-13

동시 세션 마이그레이션 레이스(AS-FRESH-01 · NAVER-INGEST-01)로 deploy 에 head 가
2개가 됐다 — railway predeploy(alembic upgrade head) 파산 방지 no-op 병합.
"""
from typing import Sequence, Union

revision: str = "merge_asfresh_naver"
down_revision: Union[str, Sequence[str], None] = (
    "asfresh_00",
    "naver_triage_00",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No-op merge — unifies parallel branches."""


def downgrade() -> None:
    """No-op merge downgrade."""
