"""Phase 0A: notification user-state tables (user states / events / push subscriptions)

Revision ID: phase_0a_notif_user_states
Revises: phase_f_trgm_search_indexes
Create Date: 2026-07-04

공유 Notification row 를 사용자별 상태로 감싸는 기반 테이블 3개를 생성한다.
대량 backfill 은 migration 에 넣지 않는다(scripts/maintenance/backfill_notification_user_states.py).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'phase_0a_notif_user_states'
down_revision: Union[str, None] = 'phase_f_trgm_search_indexes'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """notification_user_states / notification_events / notification_push_subscriptions 생성."""
    op.create_table(
        'notification_user_states',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column(
            'notification_id',
            sa.Integer(),
            sa.ForeignKey('notifications.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('recipient_source', sa.String(30), nullable=False),
        sa.Column('read_at', sa.DateTime(), nullable=True),
        sa.Column('archived_at', sa.DateTime(), nullable=True),
        sa.Column('ack_at', sa.DateTime(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('escalated_at', sa.DateTime(), nullable=True),
        sa.Column('last_opened_at', sa.DateTime(), nullable=True),
        sa.Column('last_delivery_status', sa.String(30), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('notification_id', 'user_id', name='uq_notification_user_states_notif_user'),
    )
    op.create_index(
        'ix_notification_user_states_user_inbox',
        'notification_user_states',
        ['user_id', 'archived_at', 'read_at', 'notification_id'],
    )

    op.create_table(
        'notification_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column(
            'notification_id',
            sa.Integer(),
            sa.ForeignKey('notifications.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'user_state_id',
            sa.Integer(),
            sa.ForeignKey('notification_user_states.id'),
            nullable=True,
        ),
        sa.Column('actor_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('recipient_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('event_type', sa.String(40), nullable=False),
        sa.Column('channel', sa.String(20), nullable=True),
        sa.Column('endpoint_hash', sa.String(64), nullable=True),
        sa.Column('request_id', sa.String(64), nullable=True),
        sa.Column('metadata_json', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index(
        'ix_notification_events_notif_created',
        'notification_events',
        ['notification_id', 'created_at'],
    )
    op.create_index(
        'ix_notification_events_recipient_type_created',
        'notification_events',
        ['recipient_user_id', 'event_type', 'created_at'],
    )
    op.create_index(
        'ix_notification_events_actor_created',
        'notification_events',
        ['actor_user_id', 'created_at'],
    )
    op.create_index(
        'ix_notification_events_endpoint_created',
        'notification_events',
        ['endpoint_hash', 'created_at'],
    )

    op.create_table(
        'notification_push_subscriptions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('endpoint', sa.Text(), nullable=False, unique=True),
        sa.Column('p256dh', sa.Text(), nullable=True),
        sa.Column('auth', sa.Text(), nullable=True),
        sa.Column('platform', sa.String(30), nullable=True),
        sa.Column('browser', sa.String(50), nullable=True),
        sa.Column('device_label', sa.String(100), nullable=True),
        sa.Column('permission_state', sa.String(20), nullable=True),
        sa.Column('last_seen_at', sa.DateTime(), nullable=True),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
    )


def downgrade() -> None:
    """Phase 0A 테이블/인덱스 제거 (생성 역순)."""
    op.drop_table('notification_push_subscriptions')

    op.drop_index('ix_notification_events_endpoint_created', table_name='notification_events')
    op.drop_index('ix_notification_events_actor_created', table_name='notification_events')
    op.drop_index('ix_notification_events_recipient_type_created', table_name='notification_events')
    op.drop_index('ix_notification_events_notif_created', table_name='notification_events')
    op.drop_table('notification_events')

    op.drop_index('ix_notification_user_states_user_inbox', table_name='notification_user_states')
    op.drop_table('notification_user_states')
