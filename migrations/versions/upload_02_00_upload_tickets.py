"""UPLOAD-02: upload_tickets child + outbox upload_ticket_id FK

Revision ID: upload_02_00
Revises: upload_intent_00
Create Date: 2026-07-27

per-file 업로드 ticket 수명주기(issue/complete/expire/cancel)의 유일 스키마 변경이다.
단일 additive 마이그레이션 — 새 child 테이블 ``upload_tickets`` 하나를 만들고, SIDEFX-00 이
plain integer 로 남겨둔 ``domain_side_effect_outbox.upload_ticket_id`` 에 실 FK 를 부착한다.

* ``upload_tickets`` — per-file 티켓 행. ``id``·``order_id`` FK·``category``·``item_id``
  (order_item_identities FK, SET NULL)·``item_index``·``object_key``(server-derived,
  unique)·``filename``·``file_type``·``file_size``·``state``(ISSUED|COMPLETED|EXPIRED|
  CANCELLED)·``issued_by``·``row_version``·``created_at``·``expires_at``(created_at+900s)·
  ``completed_at``. server-derived key 는 ``uq_upload_ticket_object_key`` 로 유일하고
  ``ix_upload_ticket_expiry`` 가 bounded cleanup provider 의 만료 claim hot path 다.
* ``domain_side_effect_outbox.upload_ticket_id`` **FK 부착** — SIDEFX-00 계약이 남겨둔
  no-FK 도메인(source_domain=``UPLOAD_TICKET``)에 부모 테이블이 생겼으므로 실 FK 로
  orphan 을 DB 가 거부한다(one-of matrix ``ck_dseo_source_one_of`` 는 불변; FK 만 추가).

**경계(UPLOAD-02)**: 별도 scheduler/cleanup loop 를 만들지 않는다(만료 scan 은 SIDEFX
worker 300s expiry scan 이 provider 를 호출). DDL 은 models.py ORM 정의와 SSOT 를 공유한다
(create_all 테스트 lane 동일 스키마).

``downgrade()`` 는 FK → 인덱스 → 테이블을 생성 역순으로 제거한다(ISSUED 티켓은 pre-확정
예약 행이라 무손실 역변환).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'upload_02_00'
down_revision: Union[str, None] = 'upload_intent_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """upload_tickets 테이블·인덱스 생성 + outbox upload_ticket_id FK 부착."""
    op.create_table(
        'upload_tickets',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('order_id', sa.Integer(),
                  sa.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False),
        sa.Column('category', sa.String(50), nullable=False),
        sa.Column('item_id', postgresql.UUID(as_uuid=False),
                  sa.ForeignKey('order_item_identities.id', ondelete='SET NULL'), nullable=True),
        sa.Column('item_index', sa.Integer(), nullable=True),
        sa.Column('object_key', sa.String(500), nullable=False),
        sa.Column('filename', sa.String(255), nullable=False),
        sa.Column('file_type', sa.String(50), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=False),
        sa.Column('state', sa.String(20), nullable=False, server_default='ISSUED'),
        sa.Column('issued_by', sa.Integer(),
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('row_version', sa.Integer(), nullable=False, server_default=sa.text('1')),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "state IN ('ISSUED','COMPLETED','EXPIRED','CANCELLED')",
            name='ck_upload_ticket_state'),
    )
    # order 별 티켓 조회.
    op.create_index('ix_upload_tickets_order_id', 'upload_tickets', ['order_id'])
    # server-derived key 는 티켓당 유일 → complete tamper 검사·중복 발급 차단.
    op.create_index('uq_upload_ticket_object_key', 'upload_tickets',
                    ['object_key'], unique=True)
    # bounded cleanup provider 의 만료 claim hot path.
    op.create_index('ix_upload_ticket_expiry', 'upload_tickets', ['state', 'expires_at'])
    # item-retire cleanup: 은퇴 identity 의 ISSUED 티켓 claim.
    op.create_index('ix_upload_ticket_item', 'upload_tickets', ['item_id'])
    # UPLOAD_TICKET 도메인 실 FK 부착(부모 생성 후 orphan 거부; one-of matrix 불변).
    op.create_foreign_key(
        'fk_dseo_upload_ticket', 'domain_side_effect_outbox',
        'upload_tickets', ['upload_ticket_id'], ['id'], ondelete='CASCADE',
    )


def downgrade() -> None:
    """생성 역순으로 FK → 인덱스 → 테이블 제거."""
    op.drop_constraint('fk_dseo_upload_ticket', 'domain_side_effect_outbox',
                       type_='foreignkey')
    op.drop_index('ix_upload_ticket_item', table_name='upload_tickets')
    op.drop_index('ix_upload_ticket_expiry', table_name='upload_tickets')
    op.drop_index('uq_upload_ticket_object_key', table_name='upload_tickets')
    op.drop_index('ix_upload_tickets_order_id', table_name='upload_tickets')
    op.drop_table('upload_tickets')
