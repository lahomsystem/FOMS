"""ACCOUNT-SELF-01: users.approval_status + password_reset_requests 테이블

Revision ID: account_self_00
Revises: typedrift_00
Create Date: 2026-08-06

계정 셀프서비스 v1(스펙: docs/specs/2026-08-06-account-self-service-design.md)의
단일 additive 마이그레이션.

* ``users.approval_status`` — 셀프 가입 승인 상태(ACTIVE|PENDING). 기존 행은
  server_default('ACTIVE') 로 전부 backfill 되어 동작 불변. 거절은 상태 보존 없이
  row 삭제이므로 REJECTED 값은 없다.
* ``password_reset_requests`` — 재설정 요청 큐(관리자 처리형). 계정 열거 방지를 위해
  미매칭 username 도 ``user_id`` NULL 로 기록한다. 사용자 삭제 시 요청 row 는 감사로
  보존(SET NULL).

``downgrade()`` 는 테이블 → 컬럼 순서로 제거한다(요청 큐는 파생 감사 데이터라 무손실
역변환 아님을 감수하는 단순 drop).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'account_self_00'
down_revision: Union[str, None] = 'typedrift_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """users.approval_status 추가 + password_reset_requests 테이블 생성."""
    op.add_column(
        'users',
        sa.Column('approval_status', sa.String(20), nullable=False,
                  server_default='ACTIVE'),
    )
    op.create_table(
        'password_reset_requests',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('username_submitted', sa.String(64), nullable=False),
        sa.Column('user_id', sa.Integer(),
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='PENDING'),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('handled_by_user_id', sa.Integer(),
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('handled_at', sa.DateTime(), nullable=True),
        sa.Column('request_ip', sa.String(64), nullable=True),
        sa.CheckConstraint(
            "status IN ('PENDING','DONE','DISMISSED')",
            name='ck_password_reset_requests_status'),
    )
    # 관리자 대기 큐 조회 hot path(PENDING 을 최신순).
    op.create_index('ix_password_reset_requests_status_created',
                    'password_reset_requests', ['status', 'created_at'])


def downgrade() -> None:
    """생성 역순으로 테이블 → 컬럼 제거."""
    op.drop_index('ix_password_reset_requests_status_created',
                  table_name='password_reset_requests')
    op.drop_table('password_reset_requests')
    op.drop_column('users', 'approval_status')
