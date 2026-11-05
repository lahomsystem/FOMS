"""CSAGENT-07: 사례 질문 앞 대화 — cs_agent_turns 칸 하나(masked_context)

Revision ID: csagent_07
Revises: ppay_00
Create Date: 2026-11-05

설계 정본: 설계서 2026-10-27-cs-ai-agent 17.2.2 '고친 글은 앞 대화와 함께 배운다'(사장님 11-05 — "수정한 내용은 CS 에이전트가
학습해야 돼, 이전 대화 맥락을 이해하면서").

* ``cs_agent_turns.masked_context`` — 사례를 적을 때(보내기 그대로 · 고침, 직원 직접 답) 그 질문 **앞** 공개 대화를 가린 글. 줄마다
  ``[손님]`` · ``[직원]`` 머리표, 최근 6줄 · 800자까지, 가림 검사를 넘은 줄만(없으면 NULL). 비공개 메모 · AI 메모는 뺀다. 보관 ·
  권한은 가린 질문 칸(``masked_question``)과 같다. 비어 있는 칸만 더해 옛 줄은 그대로다(옛 사례는 앞 대화 없이 쓰인다).

``downgrade()`` 는 칸을 지운다(앞 대화 글이 사라진다 — 무손실 아님, 사례 짝은 그대로). DDL 은 models.py ``CsAgentTurn`` 과
같다(시험이 견준다). 상수 동결 원칙에 따라 models 를 import 하지 않는다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'csagent_07'
down_revision: Union[str, None] = 'ppay_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TURNS = 'cs_agent_turns'
#: 차례 표에 더하는 칸 — (이름, 꼴, NULL 허용, 서버 기본값).
TURN_COLUMNS: tuple[tuple[str, sa.types.TypeEngine, bool, object], ...] = (
    ('masked_context', sa.Text(), True, None),
)


def upgrade() -> None:
    """차례 표 칸."""
    for name, type_, nullable, default in TURN_COLUMNS:
        op.add_column(TURNS, sa.Column(name, type_, nullable=nullable, server_default=default))


def downgrade() -> None:
    """만든 역순 — 차례 표 칸."""
    for name, _type, _nullable, _default in reversed(TURN_COLUMNS):
        op.drop_column(TURNS, name)
