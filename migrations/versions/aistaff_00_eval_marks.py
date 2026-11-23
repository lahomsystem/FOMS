"""AISTAFF-00: ai_staff_eval_marks — 'AI 시험' 지난 상담 차례마다 AI 초안(가린 글)과 사장님 채점

Revision ID: aistaff_00
Revises: csagent_08
Create Date: 2026-11-23

설계 정본: ``docs/specs/2026-11-23-brain-learning-upgrade_SPEC.md`` 4.1(자 세우기 — 사장님 채점).

* ``ai_staff_eval_marks`` — 'AI 시험'이 지난 상담 차례 하나를 모델까지 보냈을 때 한 줄. 시험 번호 · 차례 번호 · 브랜드 · AI 초안
  (가림 관문을 지난 글만 — 넘겼으면 빈 글, 90일 지나면 빈 글로 비운다) · 채점 코드 · 넘긴 까닭 · 사장님 답(채점 전 NULL) · 틀린
  종류 · 누가 · 언제 · 만든 때. 시험 번호 · 차례 번호는 하나씩만(유일 제약). 손님 글 · 직원 답은 싣지 않는다.
  사람 · 차례 번호 칸에 FK 가 없다(차례 줄 · 계정을 지워도 기록이 남는다 — 다른 접목판 표와 같다).

**빈 표 하나를 더하기만** 한다(데이터를 바꾸지 않는다 · 빈 표라 CONCURRENTLY · advisory lock 이 필요 없다). ``downgrade()`` 는
색인 · 표를 지운다(그 사이 모은 초안 · 사장님 채점이 사라진다 — 결과 줄 · 지식은 그대로). DDL 은
``foms/persistence/graft/models.py`` ``AiStaffEvalMark`` 와 같다(시험이 견준다). 상수 동결 원칙에 따라 models 를 import 하지 않는다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'aistaff_00'
down_revision: Union[str, None] = 'csagent_08'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'ai_staff_eval_marks'
#: 사장님 답 넷 · 틀린 종류 셋(작성 시점 스냅샷 — 모델 · 서비스와 같은 글자인지는 시험이 본다).
ANSWERS = ('ok', 'bad', 'handoff_right', 'should_answer')
FAIL_KINDS = ('wrong_fact', 'no_basis', 'tone')
UNIQUE = ('uq_ai_staff_eval_marks_run_turn', ('run_id', 'turn_id'))
#: (제약 이름, 칸, 값들).
CHECKS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ('ck_ai_staff_eval_marks_answer', 'owner_answer', ANSWERS),
    ('ck_ai_staff_eval_marks_fail_kind', 'fail_kind', FAIL_KINDS),
)
#: (색인 이름, 칸들) — 순서 = upgrade 순서.
INDEXES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ('ix_ai_staff_eval_marks_graded', ('graded_by', 'graded_at')),
    ('ix_ai_staff_eval_marks_graded_at', ('graded_at',)),
    ('ix_ai_staff_eval_marks_created', ('created_at',)),
)
#: 칸 — (이름, 꼴, NULL 허용, 서버 기본값). 순서 = 표 칸 순서(``id`` 다음).
COLUMNS: tuple[tuple[str, sa.types.TypeEngine, bool, object], ...] = (
    ('run_id', sa.Integer(), False, None),
    ('turn_id', sa.Integer(), False, None),
    ('brand', sa.String(8), False, None),
    ('draft', sa.Text(), False, sa.text("''")),
    ('judge_code', sa.String(32), False, None),
    ('handoff_reason', sa.String(24), True, None),
    ('owner_answer', sa.String(16), True, None),
    ('fail_kind', sa.String(16), True, None),
    ('graded_by', sa.Integer(), True, None),
    ('graded_at', sa.DateTime(), True, None),
    ('created_at', sa.DateTime(), False, sa.func.now()),
)


def in_check(column: str, values: Sequence[str]) -> str:
    """값 목록 검사 제약 식 — ``column IN ('a','b')``(모델 ``CheckConstraint`` 와 같은 글자)."""
    return f"{column} IN (" + ",".join(f"'{value}'" for value in values) + ")"


def upgrade() -> None:
    """표 · 유일 · 검사 제약 → 색인."""
    op.create_table(
        TABLE,
        sa.Column('id', sa.Integer(), primary_key=True),
        *(sa.Column(name, type_, nullable=nullable, server_default=default)
          for name, type_, nullable, default in COLUMNS),
        sa.UniqueConstraint(*UNIQUE[1], name=UNIQUE[0]),
        *(sa.CheckConstraint(in_check(column, values), name=name) for name, column, values in CHECKS),
    )
    for name, columns in INDEXES:
        op.create_index(name, TABLE, list(columns))


def downgrade() -> None:
    """만든 역순 — 색인 → 표."""
    for name, _columns in reversed(INDEXES):
        op.drop_index(name, table_name=TABLE)
    op.drop_table(TABLE)
