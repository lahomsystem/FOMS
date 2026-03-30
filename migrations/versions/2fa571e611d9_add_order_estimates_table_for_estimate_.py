"""add order_estimates table for estimate/contract

Revision ID: 2fa571e611d9
Revises: c762eed30396
Create Date: 2026-03-30 09:07:52.721248

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '2fa571e611d9'
down_revision: Union[str, None] = 'c762eed30396'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """order_estimates 테이블 생성 — 견적서/계약서 관리."""
    op.create_table(
        'order_estimates',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('order_id', sa.Integer(), sa.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('estimate_number', sa.String(50), nullable=False, unique=True),
        sa.Column('customer_name', sa.String(100), nullable=False),
        sa.Column('customer_phone', sa.String(50), nullable=True),
        sa.Column('site_address', sa.Text(), nullable=True),
        sa.Column('estimate_date', sa.String(10), nullable=False),
        sa.Column('construction_date', sa.String(10), nullable=True),
        sa.Column('manager_name', sa.String(100), nullable=True),
        sa.Column('manager_phone', sa.String(50), nullable=True),
        sa.Column('items', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('total_amount', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('deposit_amount', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('balance_amount', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('payment_info', postgresql.JSONB(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='DRAFT'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
    )


def downgrade() -> None:
    """order_estimates 테이블 제거."""
    op.drop_table('order_estimates')
