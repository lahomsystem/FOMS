"""add order_drafts table for mobile wizard autosave

Revision ID: add_order_drafts_table
Revises: designer_sketchup_intake
Create Date: 2026-05-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'add_order_drafts_table'
down_revision: Union[str, None] = 'designer_sketchup_intake'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """order_drafts 테이블 생성 — 모바일 wizard 자동저장 draft."""
    op.create_table(
        'order_drafts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column(
            'user_id',
            sa.Integer(),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'order_id',
            sa.Integer(),
            sa.ForeignKey('orders.id', ondelete='CASCADE'),
            nullable=True,
        ),
        sa.Column('draft_key', sa.String(length=64), nullable=False),
        sa.Column('step', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('payload', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('schema_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=True, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=True, server_default=sa.text('now()')),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('user_id', 'draft_key', name='uq_order_drafts_user_key'),
    )
    op.create_index(op.f('ix_order_drafts_user_id'), 'order_drafts', ['user_id'], unique=False)
    op.create_index(op.f('ix_order_drafts_order_id'), 'order_drafts', ['order_id'], unique=False)
    op.create_index(op.f('ix_order_drafts_expires_at'), 'order_drafts', ['expires_at'], unique=False)


def downgrade() -> None:
    """order_drafts 테이블 제거."""
    op.drop_index(op.f('ix_order_drafts_expires_at'), table_name='order_drafts')
    op.drop_index(op.f('ix_order_drafts_order_id'), table_name='order_drafts')
    op.drop_index(op.f('ix_order_drafts_user_id'), table_name='order_drafts')
    op.drop_table('order_drafts')
