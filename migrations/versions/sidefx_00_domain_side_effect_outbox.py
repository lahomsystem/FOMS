"""SIDEFX-00: typed-domain side-effect outbox + worker heartbeat

Revision ID: sidefx_00
Revises: assignment_00
Create Date: 2026-07-24

§2.3 line 391 의 typed-domain side-effect outbox 초기 스키마. domain side-effect
(notification·cache·geocode·storage-delete·provider call)를 business tx 와 원자적으로
기록하는 durable outbox 를 만든다. 실 producer(도메인 write)·consumer(worker delivery/
expiry/retention loop)는 하류(SIDEFX-WORKER-01·CHANNEL·URGENT 등) 몫이다.

* ``domain_side_effect_outbox`` — source_domain(7 도메인)·per-domain source FK·payload
  JSONB·schema_version·source_generation·provider_idempotency_key·dedupe_key·status·
  attempts·lease(owner_hash/token/expires_at)·available_at·retention timestamp.
  - **one-of FK CHECK matrix**(``ck_dseo_source_one_of``): 각 source_domain 은 정확히
    자기 FK 하나만 non-null 이어야 하며 mismatch/다중/전무 를 거부한다.
  - 실 FK 는 부모 테이블이 존재하는 3 도메인만: ``order_events``·``notification_events``·
    ``chat_attachments`` → orphan 을 DB 가 거부. 나머지 4 도메인(address_learning·
    wizard_pending·upload_ticket·upload_draft)은 소유 packet 이 자기 business table 과
    FK 를 additive migration 으로 추가한다(ORDER-IMPORT-01 이 8번째 ORDER_IMPORT_ARTIFACT
    를 그렇게 등록하는 선례와 동일). SIDEFX-00 은 그 business table 을 선행 생성하지 않는다.
  - unique ``(effect_type, dedupe_key)`` (partial, dedupe_key NOT NULL) — 중복 outbox 억제.
  - queue ``(status, available_at)``, lease reclaim ``(lease_expires_at) WHERE PROCESSING``,
    retention ``(completed_at) WHERE DONE`` / ``(dead_at) WHERE DEAD``.
* ``side_effect_worker_heartbeats`` — worker readiness 정본(worker 가 upsert; 여기선 테이블만).

one-of CHECK SQL 은 ``models.DOMAIN_SIDE_EFFECT_ONE_OF_CHECK_SQL`` 을 공유해 ORM(create_all
테스트 lane)과 DDL drift 를 막는다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from models import DOMAIN_SIDE_EFFECT_ONE_OF_CHECK_SQL

revision: str = 'sidefx_00'
down_revision: Union[str, None] = 'assignment_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """outbox + heartbeat 테이블과 one-of CHECK·dedupe/queue/lease/retention 인덱스 생성."""
    op.create_table(
        'domain_side_effect_outbox',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('source_domain', sa.String(40), nullable=False),
        # per-domain source FK — 실존 부모 3 도메인만 실 FK(orphan 거부).
        sa.Column('order_event_id', sa.Integer(),
                  sa.ForeignKey('order_events.id', ondelete='CASCADE'), nullable=True),
        sa.Column('notification_event_id', sa.Integer(),
                  sa.ForeignKey('notification_events.id', ondelete='CASCADE'),
                  nullable=True),
        # 아래 4 도메인은 부모 테이블 미존재 → FK 는 소유 packet 이 additive 로 추가.
        sa.Column('address_learning_request_id', sa.Integer(), nullable=True),
        sa.Column('wizard_pending_id', sa.Integer(), nullable=True),
        sa.Column('upload_ticket_id', sa.Integer(), nullable=True),
        sa.Column('upload_draft_id', sa.Integer(), nullable=True),
        sa.Column('chat_attachment_id', sa.Integer(),
                  sa.ForeignKey('chat_attachments.id', ondelete='CASCADE'), nullable=True),
        sa.Column('effect_type', sa.String(40), nullable=False),
        sa.Column('payload', postgresql.JSONB(), nullable=False),
        sa.Column('schema_version', sa.Integer(), nullable=False,
                  server_default=sa.text('1')),
        sa.Column('source_generation', sa.BigInteger(), nullable=True),
        sa.Column('provider_idempotency_key', sa.String(200), nullable=True),
        sa.Column('dedupe_key', sa.String(200), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='PENDING'),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('lease_owner_hash', sa.String(64), nullable=True),
        sa.Column('lease_token', postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column('lease_expires_at', sa.DateTime(), nullable=True),
        sa.Column('available_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('dead_at', sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "source_domain IN ('ORDER_EVENT','NOTIFICATION_EVENT','ADDRESS_LEARNING',"
            "'WIZARD_PENDING','UPLOAD_TICKET','UPLOAD_DRAFT','CHAT_ATTACHMENT')",
            name='ck_dseo_source_domain',
        ),
        sa.CheckConstraint(
            "status IN ('PENDING','PROCESSING','DONE','DEAD')",
            name='ck_dseo_status',
        ),
        # exact source-domain/FK one-of matrix(models 와 공유).
        sa.CheckConstraint(DOMAIN_SIDE_EFFECT_ONE_OF_CHECK_SQL, name='ck_dseo_source_one_of'),
    )
    # dedupe unique(effect_type,dedupe_key) — dedupe_key NULL 행은 collapse 하지 않음.
    op.create_index(
        'uq_dseo_effect_dedupe', 'domain_side_effect_outbox',
        ['effect_type', 'dedupe_key'],
        unique=True, postgresql_where=sa.text('dedupe_key IS NOT NULL'),
    )
    # queue pickup: PENDING 을 available_at 순.
    op.create_index('ix_dseo_queue', 'domain_side_effect_outbox',
                    ['status', 'available_at'])
    # lease reclaim: 만료 lease(PROCESSING) 회수.
    op.create_index('ix_dseo_lease_expiry', 'domain_side_effect_outbox',
                    ['lease_expires_at'],
                    postgresql_where=sa.text("status = 'PROCESSING'"))
    # retention: DONE completed_at>30d / DEAD dead_at>180d 조회.
    op.create_index('ix_dseo_done_retention', 'domain_side_effect_outbox',
                    ['completed_at'], postgresql_where=sa.text("status = 'DONE'"))
    op.create_index('ix_dseo_dead_retention', 'domain_side_effect_outbox',
                    ['dead_at'], postgresql_where=sa.text("status = 'DEAD'"))

    op.create_table(
        'side_effect_worker_heartbeats',
        sa.Column('worker_kind', sa.String(40), primary_key=True),
        sa.Column('last_heartbeat_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('oldest_lag_seconds', sa.Integer(), nullable=True),
        sa.Column('metadata_json', postgresql.JSONB(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('now()')),
    )


def downgrade() -> None:
    """생성 역순으로 인덱스/테이블 제거."""
    op.drop_table('side_effect_worker_heartbeats')
    op.drop_index('ix_dseo_dead_retention', table_name='domain_side_effect_outbox')
    op.drop_index('ix_dseo_done_retention', table_name='domain_side_effect_outbox')
    op.drop_index('ix_dseo_lease_expiry', table_name='domain_side_effect_outbox')
    op.drop_index('ix_dseo_queue', table_name='domain_side_effect_outbox')
    op.drop_index('uq_dseo_effect_dedupe', table_name='domain_side_effect_outbox')
    op.drop_table('domain_side_effect_outbox')
