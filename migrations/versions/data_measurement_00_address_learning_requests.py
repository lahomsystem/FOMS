"""DATA-MEASUREMENT-01: address_learning_requests child (주소 교정 학습 감사 child)

Revision ID: data_measurement_00
Revises: password_policy_00
Create Date: 2026-07-27

measurement/regional 저장을 typed field registry + 정책 + revision 으로 정본화하는
DATA-MEASUREMENT-01 의 유일 스키마 변경이다. 단일 additive 마이그레이션 — 새 테이블
``address_learning_requests`` 하나만 만든다.

이 child 는 주소 교정 학습(original→corrected + 좌표)을 **감사 가능한 durable 행**으로
남겨, 무제한 all-STAFF in-memory 학습을 policy/rate/audit 로 대체한다. 요청 handler 가
사용자별 최근 창 row 수를 세어 폭주를 거부(rate)하고, ``requested_by_user_id``·
``created_at`` 로 누가/언제(audit)를 보존하며, 이 행 id 를
``domain_side_effect_outbox.address_learning_request_id``(source_domain=ADDRESS_LEARNING)
로 참조해 실제 학습 적용을 worker 로 비동기화한다.

**outbox FK 는 추가하지 않는다**: SIDEFX-00 은 ``address_learning_request_id`` 를 plain
integer(one-of CHECK 로 domain 일치만 강제)로 두고 orphan 거부는 소유 packet 이 FK 를
붙일 때부터라고 명시했으나, 현행 SIDEFX-00 계약 테스트가 그 컬럼을 no-FK 도메인으로
검증하므로(가짜 id 삽입 accept) 여기서 FK 를 추가하면 그 계약이 깨진다. child 참조는
plain integer 로 유지한다. 지오코드 side-effect 는 별도 신규 테이블이 불필요하다
(ORDER_EVENT source 재사용) → 이 마이그레이션은 outbox 를 건드리지 않는다.

``downgrade()`` 는 테이블을 제거한다(학습 감사 로그는 파생 데이터라 무손실 역변환).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'data_measurement_00'
down_revision: Union[str, None] = 'password_policy_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """address_learning_requests 테이블 + rate/audit 조회 인덱스 생성."""
    op.create_table(
        'address_learning_requests',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('original_address', sa.Text(), nullable=False),
        sa.Column('corrected_address', sa.Text(), nullable=False),
        sa.Column('lat', sa.Float(), nullable=True),
        sa.Column('lng', sa.Float(), nullable=True),
        sa.Column('requested_by_user_id', sa.Integer(),
                  sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('now()')),
    )
    # 사용자별 최근 창 count(rate-limit)와 audit 스캔 hot path.
    op.create_index(
        'ix_alr_requester_created', 'address_learning_requests',
        ['requested_by_user_id', 'created_at'],
    )


def downgrade() -> None:
    """생성 역순으로 인덱스/테이블 제거(학습 감사 로그는 파생 데이터라 무손실)."""
    op.drop_index('ix_alr_requester_created', table_name='address_learning_requests')
    op.drop_table('address_learning_requests')
