"""merge naverbf_00 and sharehist_00 Alembic heads

Revision ID: merge_naverbf_share
Revises: naverbf_00, sharehist_00
Create Date: 2026-09-01

두 세션이 같은 부모(``naverdisp_00``)에서 각각 리비전을 올려 head 가 둘이 됐다.
railway predeploy 의 ``alembic upgrade head`` 는 'Multiple head revisions' 로 빌드를
파산시키므로 no-op 병합 리비전으로 합친다(관례: merge_account_self_typedrift_heads.py).
"""
from typing import Sequence, Union

revision: str = "merge_naverbf_share"
down_revision: Union[str, Sequence[str], None] = (
    "naverbf_00",
    "sharehist_00",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No-op merge — naverdisp_00 에서 갈라진 두 갈래를 합친다."""


def downgrade() -> None:
    """No-op merge downgrade."""
