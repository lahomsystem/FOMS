"""SHARE-TOKEN-00: order_share_tokens 테이블 (고객 공유 열람 토큰)

Revision ID: share_token_00
Revises: orderdiff_01
Create Date: 2026-08-11

고객 공유 채널 Phase A(스펙: docs/specs/2026-08-11-customer-share-phase-a-design.md
§3.1)의 단일 additive 마이그레이션.

* 토큰 원문 미저장 — sha256 해시(``token_hash``)만 UNIQUE. 256bit 원문이 방어선.
* ``snapshot`` — kind='estimate' 전용 동결 렌더 JSONB(D6, 발송 시점 스냅샷 고정)
  선반영. drawing 은 NULL(라이브 수집). ``sa.JSON().with_variant(JSONB)`` 로
  models.py ``JSONColumn`` 과 타입 정합(기존 json/jsonb 드리프트 3건에 추가 금지).
* server_default 없음 — 모든 insert 가 ORM 경로. migration_chain 지문
  (create_all ↔ 마이그레이션 재생, nullable/default 예외 없이 일치)을 위해
  models.py 정의와 컬럼 단위로 동일하게 유지한다.

``downgrade()`` 는 테이블 drop — 공유 토큰은 파생 데이터라 원본(도면·견적)은
orders/order_attachments 에 그대로 남는다(무손실).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = 'share_token_00'
# deploy 병합 시 orderdiff_01 과 이중 head 발생 → 미푸시 리비전이라 재부모화(단일 head 게이트).
down_revision: Union[str, None] = 'orderdiff_01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """order_share_tokens 테이블·인덱스 생성."""
    op.create_table(
        'order_share_tokens',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('order_id', sa.Integer(),
                  sa.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False),
        sa.Column('kind', sa.String(20), nullable=False),
        sa.Column('token_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('created_by_user_id', sa.Integer(),
                  sa.ForeignKey('users.id'), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('view_count', sa.Integer(), nullable=False),
        sa.Column('last_viewed_at', sa.DateTime(), nullable=True),
        sa.Column('snapshot',
                  sa.JSON().with_variant(JSONB(), 'postgresql'), nullable=True),
    )
    # 주문 상세 모달의 발급 목록 조회 경로(GET /api/share/list/<order_id>).
    op.create_index('ix_order_share_tokens_order_id',
                    'order_share_tokens', ['order_id'])


def downgrade() -> None:
    """order_share_tokens 제거 (인덱스·UNIQUE 는 테이블과 함께 drop)."""
    op.drop_index('ix_order_share_tokens_order_id', table_name='order_share_tokens')
    op.drop_table('order_share_tokens')
