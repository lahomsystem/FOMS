"""BRAIN-01: brain_changes — 액션 이름 칸 둘 · 기준 판 바뀜 표시 칸

Revision ID: brain_01
Revises: notice_02
Create Date: 2026-11-02

설계 정본: 설계서 2026-11-02-haud-master-brain 7.7(사장님 결정 D104 — 이름 있는 액션 유형 · ``expired``) · 7.5 승인 흐름.

* ``action`` — 그 제안을 만든 액션 이름(``propose_edit`` · ``propose_retire`` · ``item_rollback`` · ``recheck`` ·
  ``release_rollback`` · ``import`` …). 정본 목록은 ``foms/services/brain/actions.py``.
* ``decided_action`` — 그 제안을 닫은 액션 이름(``apply`` · ``edit_apply`` · ``reject`` · ``bulk_apply`` · ``recheck`` ·
  ``release_rollback`` · ``expire`` · ``import``).
* ``base_changed_at`` — 열린 제안의 기준 판이 바뀐 때(같은 항목 · 링크에 다른 반영이 들어간 순간 반영 동작이 적는다).

빈 칸 더하기만 한다(데이터를 바꾸지 않는다 — 앞 제안은 칸이 비어 있다). 이름 목록이 늘 수 있어 검사 제약은 걸지 않는다(코드
목록이 정본). ``downgrade()`` 는 칸을 지운다(액션 이름 · 바뀜 표시가 사라진다 — 제안 · 결정 자체는 남는다).
DDL 은 ``foms/persistence/brain/models.py`` ``BrainChange`` 와 같다(시험이 견준다). models 를 import 하지 않는다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'brain_01'
down_revision: Union[str, None] = 'notice_02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'brain_changes'
#: 더하는 칸 — (이름, 꼴, NULL 허용). 순서 = 표 칸 순서(brain_00 칸 뒤).
COLUMNS: tuple[tuple[str, sa.types.TypeEngine, bool], ...] = (
    ('action', sa.String(32), True),
    ('decided_action', sa.String(32), True),
    ('base_changed_at', sa.DateTime(), True),
)


def upgrade() -> None:
    """칸 셋을 더한다(빈 칸)."""
    for name, type_, nullable in COLUMNS:
        op.add_column(TABLE, sa.Column(name, type_, nullable=nullable))


def downgrade() -> None:
    """칸 셋을 지운다(거꾸로)."""
    for name, _type, _nullable in reversed(COLUMNS):
        op.drop_column(TABLE, name)
