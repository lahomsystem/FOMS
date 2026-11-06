"""FCOMM-01: 프리랜서 영업 수수료 3단계 — 주문 ↔ 프리랜서 계정 연결 표

Revision ID: fcomm_02
Revises: fcomm_01
Create Date: 2026-11-06

설계 정본: ``docs/specs/2026-11-06-freelancer-sales-commission_SPEC.md`` §4.4 · §5 · §6.1.

* ``order_freelancer_links`` — 주문(FK orders, 주문 하드 삭제 때 같이 지움) · 프리랜서 계정(FK users) ·
  관계(MANAGER_PRIMARY / MANAGER / ORDERER / CREATOR) · 만든 때.
* ``uq_order_freelancer_links_order_user_rel`` — 같은 주문 · 사람 · 관계는 한 줄.
* ``ix_order_freelancer_links_order_id`` · ``ix_order_freelancer_links_user_id`` — 주문별 맞추기 · 사람별 "내 주문".

데이터를 바꾸지 않는 표 신설뿐이다(채우기는 ``scripts/maintenance/backfill_freelancer_links.py``).
``downgrade()`` 는 인덱스와 표를 지운다. DDL 은 models.py ``OrderFreelancerLink`` 와 같다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'fcomm_02'
down_revision: Union[str, None] = 'fcomm_01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """order_freelancer_links 표 · 인덱스 만들기."""
    op.create_table(
        'order_freelancer_links',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('order_id', sa.Integer(), sa.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('relation', sa.String(16), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "relation IN ('MANAGER_PRIMARY','MANAGER','ORDERER','CREATOR')",
            name='ck_order_freelancer_links_relation',
        ),
        sa.UniqueConstraint('order_id', 'user_id', 'relation', name='uq_order_freelancer_links_order_user_rel'),
    )
    op.create_index('ix_order_freelancer_links_order_id', 'order_freelancer_links', ['order_id'])
    op.create_index('ix_order_freelancer_links_user_id', 'order_freelancer_links', ['user_id'])


def downgrade() -> None:
    """인덱스 → 표 순서로 지운다."""
    op.drop_index('ix_order_freelancer_links_user_id', table_name='order_freelancer_links')
    op.drop_index('ix_order_freelancer_links_order_id', table_name='order_freelancer_links')
    op.drop_table('order_freelancer_links')
