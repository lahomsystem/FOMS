"""CREW-00: 설치 작업자 마스터 + 주문 배정 registry

Revision ID: crew_00
Revises: signing_state_00
Create Date: 2026-07-24

§5.2 CREW-00 의 ``installation_workers``(외부 설치 작업자 마스터) 와
``order_installation_assignments``(주문↔작업자 배정 history) 를 **additive** 로 만든다.

기존 runtime 은 이 두 table 을 읽지 않으므로(route 실배선은 하류 SHIPMENT-REFERENCE-01)
의미 변경은 0 이다 — 순수 스키마 추가다. DDL 은 ``models.InstallationWorker`` /
``models.OrderInstallationAssignment`` (create_all 테스트 lane) 과 SSOT 를 공유해 drift 를
막는다. seed 행은 없다(마스터는 명시 등록으로만 채운다 — free-name master write 금지).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'crew_00'
down_revision: Union[str, None] = 'signing_state_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """installation_workers + order_installation_assignments 테이블/제약/인덱스 생성."""
    op.create_table(
        'installation_workers',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('external_worker_id', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(120), nullable=False),
        sa.Column('phone', sa.String(40), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('deactivated_at', sa.DateTime(), nullable=True),
    )
    # 활성 external_worker_id 유일 — 비활성화 뒤 같은 ID 재등록은 partial 이라 허용.
    op.create_index(
        'uq_installation_worker_active_external_id', 'installation_workers',
        ['external_worker_id'], unique=True, postgresql_where=sa.text('is_active'),
    )
    # picker display projection(활성 worker 정렬 목록) 조회.
    op.create_index(
        'ix_installation_worker_active', 'installation_workers',
        ['is_active', 'display_name'],
    )

    op.create_table(
        'order_installation_assignments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('order_id', sa.Integer(),
                  sa.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False),
        sa.Column('worker_id', sa.Integer(),
                  sa.ForeignKey('installation_workers.id'), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='ACTIVE'),
        sa.Column('assigned_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('assigned_by_user_id', sa.Integer(),
                  sa.ForeignKey('users.id'), nullable=True),
        sa.Column('released_at', sa.DateTime(), nullable=True),
        sa.Column('released_by_user_id', sa.Integer(),
                  sa.ForeignKey('users.id'), nullable=True),
        sa.Column('release_reason', sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('ACTIVE','RELEASED')",
            name='ck_order_installation_status',
        ),
    )
    # 같은 worker 를 같은 주문에 중복 active 배정 금지(released 뒤 재배정은 허용).
    op.create_index(
        'uq_order_installation_active', 'order_installation_assignments',
        ['order_id', 'worker_id'], unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    # 주문별 active 배정 조회(0..20 카운트·picker) 인덱스.
    op.create_index(
        'ix_order_installation_active_lookup', 'order_installation_assignments',
        ['order_id'], postgresql_where=sa.text("status = 'ACTIVE'"),
    )


def downgrade() -> None:
    """생성 역순으로 인덱스/테이블 제거(FK 자식 테이블 먼저)."""
    op.drop_index('ix_order_installation_active_lookup',
                  table_name='order_installation_assignments')
    op.drop_index('uq_order_installation_active',
                  table_name='order_installation_assignments')
    op.drop_table('order_installation_assignments')
    op.drop_index('ix_installation_worker_active', table_name='installation_workers')
    op.drop_index('uq_installation_worker_active_external_id',
                  table_name='installation_workers')
    op.drop_table('installation_workers')
