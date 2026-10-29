"""CSAGENT-00: cs_agent_chats · cs_agent_messages — AI 상담팀원 상태 재료(파생 칸만, 글 원문 없음)

Revision ID: csagent_00
Revises: partmem_00
Create Date: 2026-10-28

설계 정본: 설계서 2026-10-27-cs-ai-agent 4절 2 · 15.2, 실행 플랜 C1-2.

* ``cs_agent_messages`` — 채널톡 상담 글 하나에 한 줄. 글 원문 · 손님 정보는 두지 않고 personType ·
  작성 시각(entity.createdAt) · 비공개 · 기록 · 첨부 · 맺음 · 확인코드 · 약속 기한만 둔다.
  ``uq_cs_agent_messages_chat_message`` — (상담, 메시지 id) 하나에 한 줄(있으면 무시하고 넣기의 기준).
  ``ix_cs_agent_messages_inbound_log_id`` — 수신 기록 뒤돌아 읽기가 이미 넣은 줄의 원본을 다시 열지 않는 기준.
* ``cs_agent_chats`` — 상담 하나에 한 줄. 채널 · 브랜드 · 마지막 손님 글 · 마지막 공개 직원 글 · 채널톡 상태.
  ``uq_cs_agent_chats_chat_id``.

데이터를 바꾸지 않는 표 신설뿐이다. ``downgrade()`` 는 만든 역순으로 지운다(파생 칸이라 수신 기록 ·
Open API 에서 다시 만들 수 있다). DDL 은 models.py ``CsAgentChat`` · ``CsAgentMessage`` 와 같다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'csagent_00'
down_revision: Union[str, None] = 'partmem_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """cs_agent_chats · cs_agent_messages 표와 색인 만들기."""
    op.create_table(
        'cs_agent_chats',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('chat_id', sa.String(64), nullable=False),
        sa.Column('brand', sa.String(8), nullable=False),
        sa.Column('channel_id', sa.String(32), nullable=False),
        sa.Column('chat_state', sa.String(16), nullable=True),
        sa.Column('state_at', sa.DateTime(), nullable=True),
        sa.Column('last_user_message_id', sa.String(64), nullable=True),
        sa.Column('last_user_at', sa.DateTime(), nullable=True),
        sa.Column('last_answer_message_id', sa.String(64), nullable=True),
        sa.Column('last_answer_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('chat_id', name='uq_cs_agent_chats_chat_id'),
    )
    op.create_table(
        'cs_agent_messages',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('chat_id', sa.String(64), nullable=False),
        sa.Column('message_id', sa.String(64), nullable=False),
        sa.Column('brand', sa.String(8), nullable=False),
        sa.Column('person_type', sa.String(16), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('is_private', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('is_log', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('has_file', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('is_closing', sa.Boolean(), nullable=True),
        sa.Column('is_code_message', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('promise_kind', sa.String(8), nullable=True),
        sa.Column('promise_due_at', sa.DateTime(), nullable=True),
        sa.Column('promise_rule', sa.String(16), nullable=True),
        sa.Column('source', sa.String(8), nullable=False),
        sa.Column('inbound_log_id', sa.Integer(), nullable=True),
        sa.Column('ingested_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('chat_id', 'message_id', name='uq_cs_agent_messages_chat_message'),
        sa.CheckConstraint("source IN ('webhook','openapi')", name='ck_cs_agent_messages_source'),
    )
    op.create_index('ix_cs_agent_messages_inbound_log_id', 'cs_agent_messages', ['inbound_log_id'])


def downgrade() -> None:
    """만든 역순으로 색인 → 표 지우기."""
    op.drop_index('ix_cs_agent_messages_inbound_log_id', table_name='cs_agent_messages')
    op.drop_table('cs_agent_messages')
    op.drop_table('cs_agent_chats')
