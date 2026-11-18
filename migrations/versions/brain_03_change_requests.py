"""BRAIN-03: 문장으로 고치기 — 고침 묶음 표 하나 + brain_changes.request_id 칸 하나

Revision ID: brain_03
Revises: graft_00
Create Date: 2026-11-18

설계 정본: ``docs/specs/2026-11-18-brain-sentence-change_SPEC.md`` 3절 · 11절(사장님 결정 D246 ~ D249 승인).

* ``brain_change_requests`` — 문장 하나가 만든 고침 묶음 한 줄. 넣은 사람 번호 · 고칠 수 있는 층 · **가린 문장만**(원문 없음) ·
  묶음(JSON — 3절 꼴 + 줄마다 검사 결과 · 설정 고침의 전 → 후) · 상태 · 실패 코드 · 돈 · 걸린 시간 · 만든 때 · 결정한 때.
  사람 번호 칸에 FK 가 없다(계정을 지워도 기록이 남는다 — 다른 brain 표와 같다).
* ``brain_changes.request_id`` — 그 묶음이 만든 제안 줄(빈 값 허용 · 색인). 지금 줄은 빈 값 그대로다.

**빈 표 하나와 빈 칸 하나를 더하기만** 한다(데이터를 바꾸지 않는다 · 빈 표 · 빈 칸이라 CONCURRENTLY · advisory lock 이
필요 없다 — 색인도 빈 칸 위라 바로 끝난다). ``downgrade()`` 는 칸 · 표를 지운다(그 사이 쌓인 묶음 기록과 제안 줄의 묶음 번호가
사라진다 — 제안 · 판 · 감사 줄은 그대로). DDL 은 ``foms/persistence/brain/models.py`` 와 같다(시험이 견준다). models 를
import 하지 않는다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'brain_03'
down_revision: Union[str, None] = 'graft_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_JSON = sa.JSON().with_variant(postgresql.JSONB(), 'postgresql')

TABLE = 'brain_change_requests'
#: 묶음 상태 여덟(작성 시점 스냅샷 — 모델 · 서비스와 같은 글자인지는 시험이 본다).
REQUEST_STATUSES = ('analyzing', 'ready', 'asked', 'applied', 'partial', 'reverted', 'discarded', 'failed')
#: 칸 — (이름, 꼴, NULL 허용, 서버 기본값). 순서 = 표 칸 순서(``id`` 다음).
COLUMNS: tuple[tuple[str, sa.types.TypeEngine, bool, object], ...] = (
    ('created_by', sa.Integer(), False, None),
    ('layer_scope', sa.String(16), False, None),
    ('masked_text', sa.String(1000), False, None),
    ('bundle', _JSON, True, None),
    ('status', sa.String(16), False, None),
    ('error_code', sa.String(48), True, None),
    ('cost_usd', sa.Numeric(12, 6), True, None),
    ('latency_ms', sa.Integer(), True, None),
    ('created_at', sa.DateTime(), False, sa.func.now()),
    ('decided_at', sa.DateTime(), True, None),
)
CHECK_NAME = 'ck_brain_change_requests_status'
#: 색인 — (이름, 칸들). 순서 = upgrade 순서.
INDEXES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ('ix_brain_change_requests_creator_created', ('created_by', 'created_at')),
    ('ix_brain_change_requests_status_created', ('status', 'created_at')),
)
#: brain_changes 에 더하는 칸 · 색인.
CHANGE_TABLE = 'brain_changes'
CHANGE_COLUMN = ('request_id', sa.Integer(), True)
CHANGE_INDEX = ('ix_brain_changes_request_id', ('request_id',))


def in_check(column: str, values: Sequence[str]) -> str:
    """값 목록 검사 제약 식 — ``column IN ('a','b')``(모델 ``CheckConstraint`` 와 같은 글자)."""
    return f"{column} IN (" + ",".join(f"'{value}'" for value in values) + ")"


def upgrade() -> None:
    """빈 표 하나(칸 · 검사 제약 → 색인) → brain_changes 빈 칸 하나 + 색인."""
    op.create_table(
        TABLE,
        sa.Column('id', sa.Integer(), primary_key=True),
        *(sa.Column(name, type_, nullable=nullable, server_default=default)
          for name, type_, nullable, default in COLUMNS),
        sa.CheckConstraint(in_check('status', REQUEST_STATUSES), name=CHECK_NAME),
    )
    for name, columns in INDEXES:
        op.create_index(name, TABLE, list(columns))
    name, type_, nullable = CHANGE_COLUMN
    op.add_column(CHANGE_TABLE, sa.Column(name, type_, nullable=nullable))
    op.create_index(CHANGE_INDEX[0], CHANGE_TABLE, list(CHANGE_INDEX[1]))


def downgrade() -> None:
    """만든 역순 — brain_changes 색인 · 칸 → 표 색인 → 표."""
    op.drop_index(CHANGE_INDEX[0], table_name=CHANGE_TABLE)
    op.drop_column(CHANGE_TABLE, CHANGE_COLUMN[0])
    for name, _columns in reversed(INDEXES):
        op.drop_index(name, table_name=TABLE)
    op.drop_table(TABLE)

