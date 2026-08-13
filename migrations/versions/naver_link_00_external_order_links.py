"""NAVER-INGEST-01 T2: external_order_links (외부 채널 주문 수집 링크 + 원본 스냅샷)

Revision ID: naver_link_00
Revises: senderphone_00
Create Date: 2026-08-13

스마트스토어 주문 자동 수집(NAVER-INGEST-01 §3.4)의 멱등 정본 테이블을 만든다.

* ``UNIQUE (channel, external_id)`` 가 중복 수집 차단의 본체다. 앱 선체크는 체크와 INSERT
  사이 창이 있어 다중 replica 동시 스윕 레이스를 못 막는다.
* ``order_id`` 는 nullable + ``ON DELETE SET NULL``. nullable 인 것은 매핑 실패 보류
  (``PENDING_REVIEW``) 상태가 주문 없이 존재하기 때문이고, SET NULL 인 것은 주문이 지워져도
  "이미 수집함" 사실은 남아야 재수집으로 되살아나지 않기 때문이다.
* ``raw_snapshot`` 은 채널 원본 응답 그대로다(매핑 수정 후 재처리용). 개인정보를 담으므로
  노출은 관리자 전용 — 그건 앱 레벨 책임이고 여기서는 컬럼만 만든다.

DDL 은 ``models.ExternalOrderLink`` 와 SSOT 를 공유한다(create_all 테스트 lane 동일 스키마).
마이그레이션 상수 동결 원칙에 따라 ``models`` 를 import 하지 않는다(테이블/제약명 리터럴).

``downgrade()`` 는 인덱스 → 테이블 생성 역순으로 제거한다. 수집 이력 전용 테이블이라
다른 테이블을 건드리지 않으며, drop 시 수집 이력은 사라진다(멱등 근거 소실 → 재실행 시
과거 주문이 다시 수집될 수 있으므로 운영 downgrade 는 수집 게이트 off 상태에서만 한다).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'naver_link_00'
down_revision: Union[str, None] = 'senderphone_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'external_order_links'


def upgrade() -> None:
    """external_order_links 생성(UNIQUE 멱등 키 + 상태 CHECK + 조회 인덱스 2종)."""
    op.create_table(
        TABLE,
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('channel', sa.String(20), nullable=False, server_default='NAVER'),
        sa.Column('external_id', sa.String(64), nullable=False),
        sa.Column('order_id', sa.Integer(),
                  sa.ForeignKey('orders.id', ondelete='SET NULL'), nullable=True),
        sa.Column('external_order_no', sa.String(64), nullable=True),
        sa.Column('raw_snapshot', postgresql.JSONB(), nullable=True),
        sa.Column('sync_status', sa.String(20), nullable=False, server_default='LINKED'),
        sa.Column('failure_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('now()')),
        sa.UniqueConstraint('channel', 'external_id',
                            name='uq_external_order_link_channel_ext'),
        sa.CheckConstraint(
            "sync_status IN ('LINKED','PENDING_REVIEW','FAILED')",
            name='ck_external_order_link_status'),
    )
    # 관리 화면: 보류/실패 목록을 최신순으로 훑는 경로.
    op.create_index('ix_external_order_link_status_created', TABLE,
                    ['sync_status', 'created_at'])
    # 주문 상세에서 "이 주문이 어느 채널 수집분인가" 역조회.
    op.create_index('ix_external_order_link_order', TABLE, ['order_id'])


def downgrade() -> None:
    """생성 역순 제거. 수집 이력이 함께 사라지므로 게이트 off 상태에서만 수행한다."""
    op.drop_index('ix_external_order_link_order', table_name=TABLE)
    op.drop_index('ix_external_order_link_status_created', table_name=TABLE)
    op.drop_table(TABLE)
