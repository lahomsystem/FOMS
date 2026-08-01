"""CHANNEL-WEBHOOK-AUTH-01: webhook acceptance receipt/conflict/intent/job schema

Revision ID: channel_webhook_00
Revises: as_backfill_00
Create Date: 2026-07-25

§5.2 CHANNEL-WEBHOOK-AUTH-01 의 Webhook acceptance 정본 스키마를 신설한다. ChannelTalk
Webhook 은 provider token(x-signature) 검증 뒤 **acceptance transaction** 으로만 2xx 를
내며, 그 tx 가 쓰는 4개 테이블을 만든다:

* ``channel_webhook_receipts`` — accepted_at + JCS canonical ``content_hash`` + 30d dedup
  window + **versioned AES-256-GCM envelope**(raw payload 암호문, 평문 미저장).
* ``channel_webhook_conflicts`` — 30d window 안 중복 재전송(soak) 관측(masked only).
* ``channel_webhook_intents`` — receipt 당 1개 intent marker(상세 실행은 downstream).
* ``channel_webhook_jobs`` — durable ID-job(transactional outbox). 이 row 가 receipt 와
  같은 tx 로 커밋된 뒤에만 webhook 이 2xx 를 낸다(부분 수용 0).

**순수 스키마 추가**다: 기존 ``channel_inbound_event_logs`` 파이프라인은 그대로 두고
(``channel_webhook_jobs.legacy_log_id`` 로 연결만 한다), 실 Order mutation 은 downstream
worker 소관이라 이 단계의 runtime 의미 변경은 0 이다. DDL 은 ``models`` 의
``ChannelWebhook{Receipt,Conflict,Intent,Job}`` (create_all 테스트 lane)과 SSOT 를 공유한다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'channel_webhook_00'
down_revision: Union[str, None] = 'as_backfill_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """receipt/conflict/intent/job 테이블 + 인덱스/제약 생성."""
    op.create_table(
        'channel_webhook_receipts',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column('source', sa.String(length=40), nullable=False),
        sa.Column('content_hash', sa.String(length=64), nullable=False),
        sa.Column('accepted_at', sa.DateTime(), nullable=False),
        sa.Column('dedup_expires_at', sa.DateTime(), nullable=False),
        # versioned AES-256-GCM envelope(version/alg/nonce/aad_sha256/ciphertext) — 평문 0.
        sa.Column('envelope', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_channel_webhook_receipts_content_hash', 'channel_webhook_receipts',
                    ['content_hash'])
    # 30d dedup window 조회((content_hash, accepted_at >= now-30d)) 인덱스.
    op.create_index('ix_channel_webhook_receipt_hash_time', 'channel_webhook_receipts',
                    ['content_hash', 'accepted_at'])

    op.create_table(
        'channel_webhook_conflicts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('receipt_id', postgresql.UUID(as_uuid=False),
                  sa.ForeignKey('channel_webhook_receipts.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('content_hash', sa.String(length=64), nullable=False),
        sa.Column('source', sa.String(length=40), nullable=False),
        sa.Column('observed_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_channel_webhook_conflicts_receipt_id', 'channel_webhook_conflicts',
                    ['receipt_id'])
    op.create_index('ix_channel_webhook_conflicts_content_hash', 'channel_webhook_conflicts',
                    ['content_hash'])

    op.create_table(
        'channel_webhook_intents',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column('receipt_id', postgresql.UUID(as_uuid=False),
                  sa.ForeignKey('channel_webhook_receipts.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('intent_type', sa.String(length=80), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('receipt_id', name='uq_channel_webhook_intent_receipt'),
    )

    op.create_table(
        'channel_webhook_jobs',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column('receipt_id', postgresql.UUID(as_uuid=False),
                  sa.ForeignKey('channel_webhook_receipts.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('legacy_log_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending','enqueued','failed')",
            name='ck_channel_webhook_job_status',
        ),
    )
    op.create_index('ix_channel_webhook_jobs_receipt_id', 'channel_webhook_jobs', ['receipt_id'])


def downgrade() -> None:
    """생성 역순으로 인덱스/테이블 제거."""
    op.drop_index('ix_channel_webhook_jobs_receipt_id', table_name='channel_webhook_jobs')
    op.drop_table('channel_webhook_jobs')
    op.drop_table('channel_webhook_intents')
    op.drop_index('ix_channel_webhook_conflicts_content_hash', table_name='channel_webhook_conflicts')
    op.drop_index('ix_channel_webhook_conflicts_receipt_id', table_name='channel_webhook_conflicts')
    op.drop_table('channel_webhook_conflicts')
    op.drop_index('ix_channel_webhook_receipt_hash_time', table_name='channel_webhook_receipts')
    op.drop_index('ix_channel_webhook_receipts_content_hash', table_name='channel_webhook_receipts')
    op.drop_table('channel_webhook_receipts')
