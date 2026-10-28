"""CSAGENT-01: cs_agent_turns — AI 상담팀원 초안 차례 기록(선점 · 상태 · 코드 · 숫자, 글은 가린 칸만)

Revision ID: csagent_01
Revises: csagent_00
Create Date: 2026-10-28

설계 정본: 설계서 2026-10-27-cs-ai-agent 4절 8 · 9, 실행 플랜 C3-1 · C3-3(원장 R1-2 · R1-3 · R1-20).

* ``cs_agent_turns`` — 손님 글 하나(상담의 마지막 손님 글)에 한 줄. 상태 · 선점 횟수 · 올린 메모 id · 두뇌 결과
  (의도 · 넘김 · 모델 · 깊이 · 토큰 · 비용 · 지연 · 대체 모델 여부 — 코드 · 숫자만) · 검사 코드 · 가린 초안 · 가린 직원 답 ·
  판정 · 이유 코드. ``fallback_used`` 는 아직 어디에도 올리지 않은 이 리비전에 그 자리에서 더했다(원장 R7-12).
  ``uq_cs_agent_turns_chat_turn`` — (상담, 마지막 손님 글 id) 하나에 한 줄(선점 = 있으면 무시하고 넣기의 기준).
  ``ck_cs_agent_turns_state`` — 상태 여섯 가지(claimed · posting · posted · stored · skipped · failed)만.
  ``ix_cs_agent_turns_state_updated`` — 재시작 때 '올리는 중'으로 남은 줄 찾기.
  ``ix_cs_agent_turns_brand_created`` — 브랜드 하루 상한 · 판정 표.

데이터를 바꾸지 않는 표 신설뿐이다. ``downgrade()`` 는 만든 역순으로 지운다(색인 → 표). DDL 은 models.py
``CsAgentTurn`` 과 같다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'csagent_01'
down_revision: Union[str, None] = 'csagent_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(), 'postgresql')


def upgrade() -> None:
    """cs_agent_turns 표와 색인 만들기."""
    op.create_table(
        'cs_agent_turns',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('brand', sa.String(8), nullable=False),
        sa.Column('chat_id', sa.String(64), nullable=False),
        sa.Column('last_user_message_id', sa.String(64), nullable=False),
        sa.Column('state', sa.String(16), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default=sa.text('1')),
        sa.Column('memo_message_id', sa.String(64), nullable=True),
        sa.Column('intent', sa.String(32), nullable=True),
        sa.Column('handoff', sa.Boolean(), nullable=True),
        sa.Column('handoff_reason', sa.String(64), nullable=True),
        sa.Column('model', sa.String(64), nullable=True),
        sa.Column('effort', sa.String(16), nullable=True),
        sa.Column('input_tokens', sa.Integer(), nullable=True),
        sa.Column('output_tokens', sa.Integer(), nullable=True),
        sa.Column('cache_read_tokens', sa.Integer(), nullable=True),
        sa.Column('cache_write_tokens', sa.Integer(), nullable=True),
        sa.Column('cost_usd', sa.Numeric(12, 6), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('fallback_used', sa.Boolean(), nullable=True),
        sa.Column('check_codes', _JSON_TYPE, nullable=True),
        sa.Column('masked_draft', sa.Text(), nullable=True),
        sa.Column('staff_reply_masked', sa.Text(), nullable=True),
        sa.Column('judgment', sa.String(16), nullable=True),
        sa.Column('error_code', sa.String(48), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('chat_id', 'last_user_message_id', name='uq_cs_agent_turns_chat_turn'),
        sa.CheckConstraint("state IN ('claimed','posting','posted','stored','skipped','failed')",
                           name='ck_cs_agent_turns_state'),
    )
    op.create_index('ix_cs_agent_turns_state_updated', 'cs_agent_turns', ['state', 'updated_at'])
    op.create_index('ix_cs_agent_turns_brand_created', 'cs_agent_turns', ['brand', 'created_at'])


def downgrade() -> None:
    """만든 역순으로 색인 → 표 지우기."""
    op.drop_index('ix_cs_agent_turns_brand_created', table_name='cs_agent_turns')
    op.drop_index('ix_cs_agent_turns_state_updated', table_name='cs_agent_turns')
    op.drop_table('cs_agent_turns')
