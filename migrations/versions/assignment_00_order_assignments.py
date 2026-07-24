"""ASSIGNMENT-00: order 배정 authorization 정본(order_assignments)

Revision ID: assignment_00
Revises: backfill_artifact_00
Create Date: 2026-07-24

§2.1 line 172 의 배정 정본 스키마. drawing/construction/sales 권한 판정을 JSONB 이름
배열이 아닌 user-ID row 로 옮기기 위한 테이블만 만든다. 실제 route/AUTH enforcement 적용은
AUTH-01 몫이다(ASSIGNMENT-00 은 테이블+service+backfill+테스트 경계).

* ``order_assignments`` — domain(SALES|DRAWING|CONSTRUCTION)·source(SELF_CLAIM|
  TEAM_REPLACE|INITIAL_OWNER|BACKFILL)·active·release 이력.
* partial unique ``(order_id,domain,user_id) WHERE active`` — 중복 active 배정 금지.
* partial unique ``(order_id) WHERE active AND domain='SALES'`` — SALES 주문당 owner 1명.
* partial index ``(order_id,domain) WHERE active`` — authorization 조회.

DDL 은 models.py 의 ORM 정의(OrderAssignment)와 SSOT 를 공유한다(create_all 테스트 lane
과 동일 스키마).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'assignment_00'
down_revision: Union[str, None] = 'backfill_artifact_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """order_assignments 테이블 + partial unique/lookup 인덱스 생성."""
    op.create_table(
        'order_assignments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('order_id', sa.Integer(),
                  sa.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False),
        sa.Column('domain', sa.String(20), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('source', sa.String(20), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('assigned_at', sa.DateTime(), nullable=False),
        sa.Column('assigned_by_user_id', sa.Integer(), sa.ForeignKey('users.id'),
                  nullable=False),
        sa.Column('released_at', sa.DateTime(), nullable=True),
        sa.Column('released_by_user_id', sa.Integer(), sa.ForeignKey('users.id'),
                  nullable=True),
        sa.Column('release_reason', sa.Text(), nullable=True),
        sa.CheckConstraint(
            "domain IN ('SALES','DRAWING','CONSTRUCTION')",
            name='ck_order_assignment_domain',
        ),
        sa.CheckConstraint(
            "source IN ('SELF_CLAIM','TEAM_REPLACE','INITIAL_OWNER','BACKFILL')",
            name='ck_order_assignment_source',
        ),
    )
    op.create_index(
        'uq_order_assignment_active', 'order_assignments',
        ['order_id', 'domain', 'user_id'],
        unique=True, postgresql_where=sa.text('active'),
    )
    op.create_index(
        'uq_order_assignment_sales_owner', 'order_assignments', ['order_id'],
        unique=True, postgresql_where=sa.text("active AND domain = 'SALES'"),
    )
    op.create_index(
        'ix_order_assignment_active_lookup', 'order_assignments',
        ['order_id', 'domain'],
        postgresql_where=sa.text('active'),
    )


def downgrade() -> None:
    """생성 역순으로 인덱스/테이블 제거."""
    op.drop_index('ix_order_assignment_active_lookup', table_name='order_assignments')
    op.drop_index('uq_order_assignment_sales_owner', table_name='order_assignments')
    op.drop_index('uq_order_assignment_active', table_name='order_assignments')
    op.drop_table('order_assignments')
