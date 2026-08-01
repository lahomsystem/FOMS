"""REV-00: order mutation revision · idempotency · read-after-write receipt 기반

Revision ID: rev_00_order_mutation
Revises: ops_approval_00
Create Date: 2026-07-24

§2.4 주문 mutation revision 의 선행 스키마. 초 단위 ``structured_updated_at`` 이
구분하지 못하는 동시 저장을 낙관적 concurrency 로 대체하기 위한 기반만 만든다.
실제 mutation route 적용은 하류 packet(STATE-CORE-00·DATA-01 등) 몫이다.

* ``orders.mutation_version INTEGER NOT NULL DEFAULT 1`` — 기존 행은 server_default 로
  1 채움.
* ``order_mutation_receipts`` — idempotency receipt + read-after-write receipt 겸용
  parent. ``(actor_user_id, policy_id, idempotency_key)`` unique, opaque
  ``read_receipt_id`` UNIQUE, ``read_expires_at`` (커밋+2분) cleanup 인덱스,
  ``(expires_at, id)`` purge 인덱스(REV-00 은 인덱스만; purge 도구는 REV-CLEANUP-01).
* ``order_mutation_read_resources`` — receipt 가 건드린 Order 를 정규화한 child,
  PK ``(read_receipt_id, order_id)``, ``(order_id, read_receipt_id)`` 인덱스.

DDL 은 models.py 의 ORM 정의와 SSOT 를 공유한다(create_all 테스트 lane 과 동일 스키마).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'rev_00_order_mutation'
down_revision: Union[str, None] = 'ops_approval_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """mutation_version 컬럼 + receipt/read-resource 테이블·인덱스 생성."""
    op.add_column(
        'orders',
        sa.Column('mutation_version', sa.Integer(), nullable=False,
                  server_default=sa.text('1')),
    )

    op.create_table(
        'order_mutation_receipts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('read_receipt_id', postgresql.UUID(as_uuid=False),
                  nullable=False, unique=True),
        sa.Column('actor_user_id', sa.Integer(), sa.ForeignKey('users.id'),
                  nullable=False),
        sa.Column('policy_id', sa.String(80), nullable=False),
        sa.Column('idempotency_key', sa.String(64), nullable=True),
        sa.Column('scope_hash', sa.String(64), nullable=False),
        sa.Column('request_hash', sa.String(64), nullable=False),
        sa.Column('response_status', sa.Integer(), nullable=False),
        sa.Column('response_body', postgresql.JSONB(), nullable=False),
        sa.Column('resulting_versions', postgresql.JSONB(), nullable=False),
        sa.Column('read_expires_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('now()')),
        sa.UniqueConstraint('actor_user_id', 'policy_id', 'idempotency_key',
                            name='uq_order_mutation_receipt_idem'),
    )
    op.create_index('ix_omr_actor_read_expires', 'order_mutation_receipts',
                    ['actor_user_id', 'read_expires_at'])
    # REV-CLEANUP-01 purge keyset. REV-00 은 인덱스만 소유(purge 도구는 미구현).
    op.create_index('ix_omr_expires_id', 'order_mutation_receipts',
                    ['expires_at', 'id'])

    op.create_table(
        'order_mutation_read_resources',
        sa.Column('read_receipt_id', postgresql.UUID(as_uuid=False),
                  sa.ForeignKey('order_mutation_receipts.read_receipt_id',
                                ondelete='CASCADE'),
                  primary_key=True),
        sa.Column('order_id', sa.Integer(), sa.ForeignKey('orders.id'),
                  primary_key=True),
        sa.Column('resulting_version', sa.Integer(), nullable=False),
        sa.Column('changed_cache_families_json', postgresql.JSONB(), nullable=False),
    )
    op.create_index('ix_omrr_order_receipt', 'order_mutation_read_resources',
                    ['order_id', 'read_receipt_id'])


def downgrade() -> None:
    """생성 역순으로 인덱스/테이블/컬럼 제거."""
    op.drop_index('ix_omrr_order_receipt', table_name='order_mutation_read_resources')
    op.drop_table('order_mutation_read_resources')
    op.drop_index('ix_omr_expires_id', table_name='order_mutation_receipts')
    op.drop_index('ix_omr_actor_read_expires', table_name='order_mutation_receipts')
    op.drop_table('order_mutation_receipts')
    op.drop_column('orders', 'mutation_version')
