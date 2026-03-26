"""Add ChannelTalk Phase 0 models

Revision ID: c762eed30396
Revises: phase_b_erp_date_cols
Create Date: 2026-03-26 12:40:51.627844

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c762eed30396'
down_revision: Union[str, None] = 'phase_b_erp_date_cols'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ============================================
    # 1. orders 테이블 확장: channel_source_seq 추가
    # ============================================
    op.add_column('orders', sa.Column('channel_source_seq', sa.Integer(), server_default='0', nullable=True))
    
    # 데이터 채우기 (기존 데이터)
    op.execute("UPDATE orders SET channel_source_seq = 0 WHERE channel_source_seq IS NULL")
    
    # Contract: NOT NULL 설정
    op.alter_column('orders', 'channel_source_seq',
               existing_type=sa.Integer(),
               nullable=False,
               server_default='0')

    # ============================================
    # 2. ChannelTalk 연동 테이블 생성
    # ============================================
    op.create_table('channel_delivery_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('event_key', sa.String(length=200), nullable=False),
        sa.Column('source_type', sa.String(length=50), nullable=False),
        sa.Column('source_id', sa.Integer(), nullable=False),
        sa.Column('target_type', sa.String(length=50), nullable=False),
        sa.Column('target_id', sa.String(length=200), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='pending'),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('next_retry_at', sa.DateTime(), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('message_id', sa.String(length=200), nullable=True),
        sa.Column('masked_request_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('masked_response_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('rendered_text_snapshot', sa.Text(), nullable=True),
        sa.Column('file_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('target_group_snapshot', sa.String(length=200), nullable=True),
        sa.Column('template_key', sa.String(length=100), nullable=True),
        sa.Column('template_version', sa.Integer(), nullable=True),
        sa.Column('source_version', sa.Integer(), nullable=True),
        sa.Column('parent_delivery_id', sa.Integer(), nullable=True),
        sa.Column('correlation_id', sa.String(length=100), nullable=True),
        sa.Column('actor_type', sa.String(length=30), nullable=True),
        sa.Column('actor_id', sa.Integer(), nullable=True),
        sa.Column('order_id', sa.Integer(), nullable=True),
        sa.Column('wave', sa.String(length=20), nullable=True),
        sa.Column('request_id', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['parent_delivery_id'], ['channel_delivery_logs.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('event_key', 'target_type', 'target_id', name='uq_channel_delivery_event_target')
    )
    op.create_index('ix_channel_delivery_created_at', 'channel_delivery_logs', ['created_at'], unique=False)
    op.create_index('ix_channel_delivery_order_created', 'channel_delivery_logs', ['order_id', 'created_at'], unique=False)
    op.create_index('ix_channel_delivery_retry', 'channel_delivery_logs', ['status', 'next_retry_at'], unique=False, postgresql_where=sa.text("status IN ('pending', 'api_failed', 'token_issue_failed', 'token_rate_limited')"))
    op.create_index('ix_channel_delivery_source_status', 'channel_delivery_logs', ['source_type', 'source_id', 'status'], unique=False)

    op.create_table('channel_inbound_event_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('provider_event_id', sa.String(length=200), nullable=True),
        sa.Column('dedupe_key', sa.String(length=200), nullable=False),
        sa.Column('creation_key', sa.String(length=200), nullable=True),
        sa.Column('payload_hash', sa.String(length=64), nullable=False),
        sa.Column('raw_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('chat_type', sa.String(length=50), nullable=True),
        sa.Column('source_chat_id', sa.String(length=200), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='received'),
        sa.Column('parsed_result', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('error_reason', sa.Text(), nullable=True),
        sa.Column('correlation_id', sa.String(length=100), nullable=True),
        sa.Column('wave', sa.String(length=20), nullable=True),
        sa.Column('source_manager_id', sa.String(length=200), nullable=True),
        sa.Column('created_order_id', sa.Integer(), nullable=True),
        sa.Column('created_task_id', sa.Integer(), nullable=True),
        sa.Column('created_order_ref', sa.String(length=100), nullable=True),
        sa.Column('created_task_ref', sa.String(length=100), nullable=True),
        sa.Column('received_at', sa.DateTime(), nullable=False),
        sa.Column('processed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['created_order_id'], ['orders.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_task_id'], ['order_tasks.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('creation_key'),
        sa.UniqueConstraint('dedupe_key')
    )
    op.create_index('ix_channel_inbound_status_time', 'channel_inbound_event_logs', ['status', 'received_at'], unique=False)
    op.create_index(op.f('ix_channel_inbound_event_logs_payload_hash'), 'channel_inbound_event_logs', ['payload_hash'], unique=False)
    op.create_index(op.f('ix_channel_inbound_event_logs_provider_event_id'), 'channel_inbound_event_logs', ['provider_event_id'], unique=False)
    op.create_index(op.f('ix_channel_inbound_event_logs_source_chat_id'), 'channel_inbound_event_logs', ['source_chat_id'], unique=False)

    op.create_table('channel_manager_links',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('channel_manager_id', sa.String(length=200), nullable=False),
        sa.Column('channel_manager_email', sa.String(length=200), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('linked_at', sa.DateTime(), nullable=False),
        sa.Column('last_verified_at', sa.DateTime(), nullable=True),
        sa.Column('deactivated_at', sa.DateTime(), nullable=True),
        sa.Column('deactivated_by_user_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['deactivated_by_user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_channel_manager_links_channel_manager_email'), 'channel_manager_links', ['channel_manager_email'], unique=False)
    op.create_index('ix_channel_manager_link_active_id', 'channel_manager_links', ['channel_manager_id'], unique=True, postgresql_where=sa.text('is_active = true'))
    op.create_index('ix_channel_manager_link_user_active', 'channel_manager_links', ['user_id', 'is_active'], unique=False)


def downgrade() -> None:
    # 1. 테이블 삭제
    op.drop_index('ix_channel_manager_link_user_active', table_name='channel_manager_links')
    op.drop_index('ix_channel_manager_link_active_id', table_name='channel_manager_links', postgresql_where=sa.text('is_active = true'))
    op.drop_index(op.f('ix_channel_manager_links_channel_manager_email'), table_name='channel_manager_links')
    op.drop_table('channel_manager_links')
    
    op.drop_index(op.f('ix_channel_inbound_event_logs_source_chat_id'), table_name='channel_inbound_event_logs')
    op.drop_index(op.f('ix_channel_inbound_event_logs_provider_event_id'), table_name='channel_inbound_event_logs')
    op.drop_index(op.f('ix_channel_inbound_event_logs_payload_hash'), table_name='channel_inbound_event_logs')
    op.drop_index('ix_channel_inbound_status_time', table_name='channel_inbound_event_logs')
    op.drop_table('channel_inbound_event_logs')
    
    op.drop_index('ix_channel_delivery_source_status', table_name='channel_delivery_logs')
    op.drop_index('ix_channel_delivery_retry', table_name='channel_delivery_logs', postgresql_where=sa.text("status IN ('pending', 'api_failed', 'token_issue_failed', 'token_rate_limited')"))
    op.drop_index('ix_channel_delivery_order_created', table_name='channel_delivery_logs')
    op.drop_index('ix_channel_delivery_created_at', table_name='channel_delivery_logs')
    op.drop_table('channel_delivery_logs')

    # 2. orders 컬럼 삭제
    op.drop_column('orders', 'channel_source_seq')
