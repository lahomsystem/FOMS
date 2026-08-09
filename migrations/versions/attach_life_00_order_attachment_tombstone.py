"""ATTACH-LIFE-01: order_attachments tombstone(soft delete) 컬럼 + key 조회 인덱스

Revision ID: attach_life_00
Revises: merge_acct_typedrift
Create Date: 2026-08-06

첨부 수명주기 전환(스펙: docs/specs/2026-08-05-system-audit-logging-design.md §4 T4)의
단일 additive 마이그레이션. 첨부 삭제가 hard delete + R2 즉시삭제였던 것을 tombstone +
``ATTACHMENT_DELETED`` 이벤트 + ``STORAGE_DELETE`` outbox 지연삭제로 바꾸기 위한 스키마다.

* ``order_attachments.deleted_at`` — tombstone 시각(NULL = 살아있음). 전역
  ``do_orm_execute`` 필터가 이 컬럼으로 모든 ORM SELECT 를 기본 제외한다. 기존 행은 전부
  NULL 이라 동작 불변(additive).
* ``order_attachments.deleted_by_user_id`` — 삭제 actor(users FK, ondelete SET NULL —
  사용자 삭제가 첨부 감사행을 지우지 않는다).
* ``ix_order_attachments_storage_key`` / ``ix_order_attachments_thumbnail_key`` — canonical
  파일 라우트가 요청 object key 로 tombstone 여부를 1쿼리 판정하는 hot path 인덱스. 조회가
  ``storage_key = :k OR thumbnail_key = :k`` 라 두 인덱스가 모두 있어야 BitmapOr 로 풀린다
  (이전에는 두 컬럼 모두 무인덱스라 legacy row 조회가 Seq Scan 이었다).

``downgrade()`` 는 인덱스 → 컬럼 순서로 되돌린다. tombstone 컬럼을 지우면 "삭제됨" 표시가
사라져 삭제 첨부가 다시 보이게 되므로, downgrade 는 R2 blob 이 아직 살아있는(유예 중)
상태에서만 안전하다 — 데이터 손실은 없다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'attach_life_00'
down_revision: Union[str, None] = 'merge_acct_typedrift'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """tombstone 컬럼 2개 + storage/thumbnail key 인덱스 2개 추가."""
    op.add_column(
        'order_attachments',
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
    )
    op.add_column(
        'order_attachments',
        sa.Column(
            'deleted_by_user_id', sa.Integer(),
            sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True,
        ),
    )
    # canonical 파일 라우트 tombstone lookup(매 파일 요청) — OR 조회라 양쪽 다 필요.
    op.create_index(
        'ix_order_attachments_storage_key', 'order_attachments', ['storage_key'])
    op.create_index(
        'ix_order_attachments_thumbnail_key', 'order_attachments', ['thumbnail_key'])


def downgrade() -> None:
    """생성 역순으로 인덱스 → 컬럼 제거."""
    op.drop_index('ix_order_attachments_thumbnail_key', table_name='order_attachments')
    op.drop_index('ix_order_attachments_storage_key', table_name='order_attachments')
    op.drop_column('order_attachments', 'deleted_by_user_id')
    op.drop_column('order_attachments', 'deleted_at')
