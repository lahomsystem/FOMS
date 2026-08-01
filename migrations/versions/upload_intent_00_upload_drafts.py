"""UPLOAD-INTENT-01: upload_drafts child + outbox upload_draft_id FK

Revision ID: upload_intent_00
Revises: data_measurement_00
Create Date: 2026-07-27

파일 업로드 **전에** drawing revision / AS cycle 업로드 의도를 durable DRAFT 로 예약하는
UPLOAD-INTENT-01 의 유일 스키마 변경이다. 단일 additive 마이그레이션 — 새 child 테이블
``upload_drafts`` 하나를 만들고, SIDEFX-00 이 plain integer 로 남겨둔
``domain_side_effect_outbox.upload_draft_id`` 에 실 FK 를 부착한다.

* ``upload_drafts`` — pre-file DRAFT 수명주기 행. ``id``(=DRAFT id)·``order_id`` FK·
  ``kind``(drawing_revision|as_cycle)·``created_by_user_id``·``state``(DRAFT|FINALIZED|
  CANCELLED|EXPIRED)·``object_keys``(server-derived key 목록)·``idempotency_key``·
  ``row_version``·``created_at``·``expires_at``(created_at+24h). idempotent create 는
  ``uq_upload_draft_idem`` (order,kind,key) partial unique 로 중복 생성을 0 으로 만든다.
* ``domain_side_effect_outbox.upload_draft_id`` **FK 부착** — SIDEFX-00 계약이 남겨둔
  no-FK 도메인(source_domain=``UPLOAD_DRAFT``)에 부모 테이블이 생겼으므로 실 FK 로
  orphan 을 DB 가 거부한다(one-of matrix ``ck_dseo_source_one_of`` 는 불변; FK 만 추가).

**경계(UPLOAD-INTENT-01)**: 만료 자동 정리 scheduler·R2 객체 삭제·upload_ticket/storage
스키마는 이 packet 이 만들지 않는다(UPLOAD-02 소관). DDL 은 models.py ORM 정의와 SSOT 를
공유한다(create_all 테스트 lane 동일 스키마).

``downgrade()`` 는 FK → 인덱스 → 테이블을 생성 역순으로 제거한다(DRAFT 는 pre-file 예약
행이라 무손실 역변환).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'upload_intent_00'
down_revision: Union[str, None] = 'data_measurement_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """upload_drafts 테이블·인덱스 생성 + outbox upload_draft_id FK 부착."""
    op.create_table(
        'upload_drafts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('order_id', sa.Integer(),
                  sa.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False),
        sa.Column('kind', sa.String(32), nullable=False),
        sa.Column('created_by_user_id', sa.Integer(),
                  sa.ForeignKey('users.id'), nullable=True),
        sa.Column('state', sa.String(20), nullable=False, server_default='DRAFT'),
        sa.Column('object_keys', postgresql.JSONB(), nullable=True),
        sa.Column('idempotency_key', sa.String(80), nullable=True),
        sa.Column('row_version', sa.Integer(), nullable=False, server_default=sa.text('1')),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('drawing_revision','as_cycle')", name='ck_upload_draft_kind'),
        sa.CheckConstraint(
            "state IN ('DRAFT','FINALIZED','CANCELLED','EXPIRED')",
            name='ck_upload_draft_state'),
    )
    # order 별 DRAFT 조회 hot path.
    op.create_index('ix_upload_drafts_order_id', 'upload_drafts', ['order_id'])
    # idempotent create: 같은 (order,kind,key) 는 최대 1행. key NULL 행은 collapse 안 함.
    op.create_index(
        'uq_upload_draft_idem', 'upload_drafts',
        ['order_id', 'kind', 'idempotency_key'],
        unique=True, postgresql_where=sa.text('idempotency_key IS NOT NULL'),
    )
    # UPLOAD_DRAFT 도메인 실 FK 부착(부모 생성 후 orphan 거부; one-of matrix 불변).
    op.create_foreign_key(
        'fk_dseo_upload_draft', 'domain_side_effect_outbox',
        'upload_drafts', ['upload_draft_id'], ['id'], ondelete='CASCADE',
    )


def downgrade() -> None:
    """생성 역순으로 FK → 인덱스 → 테이블 제거."""
    op.drop_constraint('fk_dseo_upload_draft', 'domain_side_effect_outbox',
                       type_='foreignkey')
    op.drop_index('uq_upload_draft_idem', table_name='upload_drafts')
    op.drop_index('ix_upload_drafts_order_id', table_name='upload_drafts')
    op.drop_table('upload_drafts')
