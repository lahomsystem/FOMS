"""WIZ-01-COMPLETION: drawing_wizard_pending child + outbox wizard_pending_id FK

Revision ID: wiz_pending_00
Revises: channel_inbound_00
Create Date: 2026-07-27

WIZ-01 의 미배달 스코프(master plan line 530/721 "WIZ-01 **child**/Order commands")를
완성하는 단일 additive 마이그레이션이다. 새 child 테이블 ``drawing_wizard_pending`` 하나를
만들고, SIDEFX-00 이 plain integer 로 남겨둔 ``domain_side_effect_outbox.wizard_pending_id``
에 실 FK 를 부착한다(UPLOAD-02 ``upload_ticket_id`` 선례 동일).

* ``drawing_wizard_pending`` — 전달 대기(sheet PNG export) pending 을 정본화하는 child row.
  ``id``·``order_id`` FK(CASCADE)·``owner_user_id`` FK(users, SET NULL)·``object_key``
  (server-derived exports prefix, unique)·``state``(READY|CLAIMED|DELETE_PENDING|DELETED|
  QUARANTINED)·``row_version``·``created_at``·``expires_at``. server-derived key 는
  ``uq_drawing_wizard_pending_object_key`` 로 유일하고 ``ix_drawing_wizard_pending_expiry``
  가 bounded cleanup 의 만료 claim hot path 다(WIZ-DELETE-01 이 DELETE_PENDING state machine
  대상으로 사용).
* ``domain_side_effect_outbox.wizard_pending_id`` **FK 부착** — SIDEFX-00 계약이 남겨둔
  no-FK 도메인(source_domain=``WIZARD_PENDING``)에 부모 테이블이 생겼으므로 실 FK 로
  orphan 을 DB 가 거부한다(one-of matrix ``ck_dseo_source_one_of`` 는 불변; FK 만 추가).

**경계(WIZ-01-COMPLETION)**: 별도 scheduler/cleanup loop 를 만들지 않는다(만료 scan 은 SIDEFX
worker 300s expiry scan provider 가 호출). DDL 은 models.py ORM 정의와 SSOT 를 공유한다
(create_all 테스트 lane 동일 스키마).

``downgrade()`` 는 FK → 인덱스 → 테이블을 생성 역순으로 제거한다(pending 은 전달 전 예약
행이라 무손실 역변환).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'wiz_pending_00'
down_revision: Union[str, None] = 'channel_inbound_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """drawing_wizard_pending 테이블·인덱스 생성 + outbox wizard_pending_id FK 부착."""
    op.create_table(
        'drawing_wizard_pending',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('order_id', sa.Integer(),
                  sa.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False),
        sa.Column('owner_user_id', sa.Integer(),
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('object_key', sa.String(500), nullable=False),
        sa.Column('state', sa.String(20), nullable=False, server_default='READY'),
        sa.Column('row_version', sa.Integer(), nullable=False, server_default=sa.text('1')),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "state IN ('READY','CLAIMED','DELETE_PENDING','DELETED','QUARANTINED')",
            name='ck_drawing_wizard_pending_state'),
    )
    # order 별 pending 조회·collection ETag.
    op.create_index('ix_drawing_wizard_pending_order_id',
                    'drawing_wizard_pending', ['order_id'])
    # server-derived key 는 pending 당 유일 → 중복 export 차단·STORAGE_DELETE tamper 기준.
    op.create_index('uq_drawing_wizard_pending_object_key',
                    'drawing_wizard_pending', ['object_key'], unique=True)
    # bounded cleanup 의 만료 claim hot path(만료 활성 pending 을 state,expires_at 순).
    op.create_index('ix_drawing_wizard_pending_expiry',
                    'drawing_wizard_pending', ['state', 'expires_at'])
    # WIZARD_PENDING 도메인 실 FK 부착(부모 생성 후 orphan 거부; one-of matrix 불변).
    op.create_foreign_key(
        'fk_dseo_wizard_pending', 'domain_side_effect_outbox',
        'drawing_wizard_pending', ['wizard_pending_id'], ['id'], ondelete='CASCADE',
    )


def downgrade() -> None:
    """생성 역순으로 FK → 인덱스 → 테이블 제거."""
    op.drop_constraint('fk_dseo_wizard_pending', 'domain_side_effect_outbox',
                       type_='foreignkey')
    op.drop_index('ix_drawing_wizard_pending_expiry', table_name='drawing_wizard_pending')
    op.drop_index('uq_drawing_wizard_pending_object_key', table_name='drawing_wizard_pending')
    op.drop_index('ix_drawing_wizard_pending_order_id', table_name='drawing_wizard_pending')
    op.drop_table('drawing_wizard_pending')
