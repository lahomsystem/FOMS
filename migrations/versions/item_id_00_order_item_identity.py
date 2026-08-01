"""ITEM-ID-00: 주문 아이템 UUID identity registry + attachment/schedule item_id

Revision ID: item_id_00
Revises: crew_00
Create Date: 2026-07-24

§5.2 ITEM-ID-00 의 ``order_item_identities``(주문 아이템 DB-global UUID identity registry
·tombstone) 를 신설하고, ``order_attachments`` / ``order_schedule_dates`` 에 nullable
``item_id`` FK 를 **expand** 로 추가한다.

첨부/일정은 오늘 위치 인덱스(``item_index``)로만 아이템에 결합돼 아이템 추가/삭제/재정렬에
조용히 깨진다. 이 registry 는 아이템마다 안정 UUID 를 발급해 결합을 위치→UUID 로 옮긴다.
이 마이그레이션은 **expand 단계** 다: 컬럼을 nullable 로만 추가하고 backfill(safe 만
UUID 발급·정확 매핑) 이후 ambiguous 0건이 확인되기 전에는 NOT NULL enforcement 를 걸지
않는다(``backfill_order_item_identities.can_enforce_not_null`` 게이트). DDL 은
``models.OrderItemIdentity`` / ``OrderAttachment`` / ``OrderScheduleDate`` (create_all
테스트 lane) 과 SSOT 를 공유한다. 순수 스키마 추가라 기존 runtime 의미 변경은 0 이다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'item_id_00'
down_revision: Union[str, None] = 'crew_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """order_item_identities 생성 + attachment/schedule 에 nullable item_id FK 추가."""
    op.create_table(
        'order_item_identities',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column('order_id', sa.Integer(),
                  sa.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False),
        # 발급 시점 아이템 슬롯 좌표(provenance/backfill 멱등 키). 런타임 auth/link 근거 아님.
        sa.Column('item_index', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('retired_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_order_item_identities_order_id', 'order_item_identities', ['order_id'])
    # 한 주문의 한 아이템 슬롯에 활성 identity 는 최대 1개(중복 발급 방지·backfill 멱등).
    # tombstone(is_active=false) 뒤 같은 슬롯은 새 UUID 로 재발급 가능.
    op.create_index(
        'uq_order_item_identity_active', 'order_item_identities',
        ['order_id', 'item_index'], unique=True, postgresql_where=sa.text('is_active'),
    )

    # expand: nullable item_id FK — backfill 로 채운 뒤에야 enforcement(별도 마이그레이션).
    op.add_column('order_attachments', sa.Column(
        'item_id', postgresql.UUID(as_uuid=False),
        sa.ForeignKey('order_item_identities.id', ondelete='SET NULL'), nullable=True,
    ))
    op.create_index('ix_order_attachments_item_id', 'order_attachments', ['item_id'])

    op.add_column('order_schedule_dates', sa.Column(
        'item_id', postgresql.UUID(as_uuid=False),
        sa.ForeignKey('order_item_identities.id', ondelete='SET NULL'), nullable=True,
    ))
    op.create_index('ix_order_schedule_dates_item_id', 'order_schedule_dates', ['item_id'])


def downgrade() -> None:
    """생성 역순으로 컬럼/인덱스/테이블 제거(FK 자식 컬럼 먼저)."""
    op.drop_index('ix_order_schedule_dates_item_id', table_name='order_schedule_dates')
    op.drop_column('order_schedule_dates', 'item_id')
    op.drop_index('ix_order_attachments_item_id', table_name='order_attachments')
    op.drop_column('order_attachments', 'item_id')
    op.drop_index('uq_order_item_identity_active', table_name='order_item_identities')
    op.drop_index('ix_order_item_identities_order_id', table_name='order_item_identities')
    op.drop_table('order_item_identities')
