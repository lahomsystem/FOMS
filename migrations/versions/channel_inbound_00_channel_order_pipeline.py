"""CHANNEL-INBOUND-ORDER-01: 채널 수신 주문 파이프라인 (recovery key state + create flag
+ receipt lifecycle + dedicated worker heartbeat)

Revision ID: channel_inbound_00
Revises: blueprint_00
Create Date: 2026-07-27

채널 webhook 수신 receipt 를 create_order 로 정본 생성하는 파이프라인의 스키마를
**additive expand** 로 배포한다:

* ``channel_inbound_key_state`` singleton(id=1) — AUTH-ACCOUNT-01 ``auth_rate_key_state``
  와 동형인 prepare/activate 상태기계. channel key material 은 AES-256-GCM envelope 로
  at-rest 저장(plaintext 키 금지).
* ``channel_create_flag`` singleton(id=1, 기본 DISABLED) — 전역 채널 주문 생성 on/off.
* ``channel_inbound_worker_heartbeats`` — dedicated worker heartbeat/lag(readiness).
* ``channel_inbound_event_logs`` 에 receipt lifecycle 컬럼 추가(receipt_state·retention·
  legal_hold·create_attempts·key_generation·sealed_secret·worker lease).

기존 runtime 은 새 table/컬럼/env 를 읽지 않으므로 기존 채널 수신 의미는 변하지 않는다
(seed 외 의미 변경 0). 실제 dedicated worker 생성은 operator 가 CHANNEL_CREATE_ENABLE 로
플래그를 켜고 key 를 활성화한 뒤에만 동작한다.

singleton seed SQL 은 ``models`` 의 SSOT 상수를 공유해 ORM(create_all 테스트 lane)과 DDL
drift 를 막는다(SecuritySigningState/AuthRateKeyState 와 같은 이중 SSOT 패턴).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from models import (
    CHANNEL_CREATE_FLAG_SEED_SQL,
    CHANNEL_INBOUND_KEY_STATE_SEED_SQL,
)

revision: str = 'channel_inbound_00'
down_revision: Union[str, None] = 'blueprint_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """key state·create flag·worker heartbeat 테이블 생성 + receipt lifecycle 컬럼 추가."""
    op.create_table(
        'channel_inbound_key_state',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('mode', sa.String(20), nullable=False, server_default='EMPTY'),
        sa.Column('version', sa.Integer(), nullable=False, server_default=sa.text('1')),
        sa.Column('generation', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('active_key_id', sa.String(64), nullable=True),
        sa.Column('previous_key_id', sa.String(64), nullable=True),
        sa.Column('pending_key_id', sa.String(64), nullable=True),
        sa.Column('active_key_ciphertext', sa.Text(), nullable=True),
        sa.Column('previous_key_ciphertext', sa.Text(), nullable=True),
        sa.Column('pending_key_ciphertext', sa.Text(), nullable=True),
        sa.Column('previous_not_after', sa.DateTime(), nullable=True),
        sa.Column('prepared_key_artifact_sha256', sa.String(64), nullable=True),
        sa.Column('prepared_rollout_artifact_sha256', sa.String(64), nullable=True),
        sa.Column('prepared_at', sa.DateTime(), nullable=True),
        sa.Column('activated_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_by_admin_user_id', sa.Integer(),
                  sa.ForeignKey('users.id'), nullable=True),
        sa.CheckConstraint('id = 1', name='ck_channel_inbound_key_singleton'),
        sa.CheckConstraint(
            "mode IN ('EMPTY','READY','ACTIVE','ROTATION_READY','ROTATING')",
            name='ck_channel_inbound_key_mode',
        ),
    )
    op.execute(CHANNEL_INBOUND_KEY_STATE_SEED_SQL)

    op.create_table(
        'channel_create_flag',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('state', sa.String(20), nullable=False, server_default='DISABLED'),
        sa.Column('version', sa.Integer(), nullable=False, server_default=sa.text('1')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_by_admin_user_id', sa.Integer(),
                  sa.ForeignKey('users.id'), nullable=True),
        sa.CheckConstraint('id = 1', name='ck_channel_create_flag_singleton'),
        sa.CheckConstraint(
            "state IN ('ENABLED','DISABLED')", name='ck_channel_create_flag_state'),
    )
    op.execute(CHANNEL_CREATE_FLAG_SEED_SQL)

    op.create_table(
        'channel_inbound_worker_heartbeats',
        sa.Column('worker_kind', sa.String(40), primary_key=True),
        sa.Column('last_heartbeat_at', sa.DateTime(), nullable=False),
        sa.Column('oldest_lag_seconds', sa.Integer(), nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
    )

    # receipt lifecycle 컬럼(additive; 기존 행은 server_default 로 채워진다).
    op.add_column('channel_inbound_event_logs',
                  sa.Column('receipt_state', sa.String(30), nullable=False,
                            server_default='NONE'))
    op.add_column('channel_inbound_event_logs',
                  sa.Column('retention_deadline', sa.DateTime(), nullable=True))
    op.add_column('channel_inbound_event_logs',
                  sa.Column('retention_alert_stage', sa.String(10), nullable=True))
    op.add_column('channel_inbound_event_logs',
                  sa.Column('legal_hold', sa.Boolean(), nullable=False,
                            server_default=sa.text('false')))
    op.add_column('channel_inbound_event_logs',
                  sa.Column('create_attempts', sa.Integer(), nullable=False,
                            server_default=sa.text('0')))
    op.add_column('channel_inbound_event_logs',
                  sa.Column('key_generation', sa.Integer(), nullable=True))
    op.add_column('channel_inbound_event_logs',
                  sa.Column('sealed_secret', sa.Text(), nullable=True))
    op.add_column('channel_inbound_event_logs',
                  sa.Column('lease_owner_hash', sa.String(64), nullable=True))
    op.add_column('channel_inbound_event_logs',
                  sa.Column('lease_token', sa.String(64), nullable=True))
    op.add_column('channel_inbound_event_logs',
                  sa.Column('lease_expires_at', sa.DateTime(), nullable=True))
    op.create_index('ix_channel_inbound_receipt_state', 'channel_inbound_event_logs',
                    ['receipt_state', 'lease_expires_at'])


def downgrade() -> None:
    """receipt lifecycle 컬럼·인덱스 제거 후 3개 신규 테이블 제거."""
    op.drop_index('ix_channel_inbound_receipt_state', table_name='channel_inbound_event_logs')
    for col in (
        'lease_expires_at', 'lease_token', 'lease_owner_hash', 'sealed_secret',
        'key_generation', 'create_attempts', 'legal_hold', 'retention_alert_stage',
        'retention_deadline', 'receipt_state',
    ):
        op.drop_column('channel_inbound_event_logs', col)
    op.drop_table('channel_inbound_worker_heartbeats')
    op.drop_table('channel_create_flag')
    op.drop_table('channel_inbound_key_state')
