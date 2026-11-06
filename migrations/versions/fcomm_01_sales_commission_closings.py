"""FCOMM-01: 프리랜서 영업 수수료 — 달 마감 표(줄 스냅샷 · 합계 · 세금 · 지급 완료)

Revision ID: fcomm_01
Revises: fcomm_00
Create Date: 2026-11-06

설계 정본: ``docs/specs/2026-11-06-freelancer-sales-commission_SPEC.md`` §4.3 · §8(J9).

* ``sales_commission_closings`` — 프리랜서(FK users) · 달(YYYY-MM) · 상태(CLOSED/PAID) · 합계 · 소득세 · 지방소득세 ·
  부가세 · 실지급 · 마감 때 세금 방식 · 줄 스냅샷(lines JSONB) · 마감한 사람 · 때 · 지급 완료한 사람 · 때.
* ``uq_sales_commission_closings_user_month`` — 프리랜서마다 달 하나에 마감 하나.

데이터를 바꾸지 않는 표 신설뿐이다. ``downgrade()`` 는 표를 지운다. DDL 은 models.py ``SalesCommissionClosing`` 와 같다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'fcomm_01'
down_revision: Union[str, None] = 'fcomm_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """sales_commission_closings 표 만들기."""
    op.create_table(
        'sales_commission_closings',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('month', sa.String(7), nullable=False),
        sa.Column('status', sa.String(8), nullable=False, server_default='CLOSED'),
        sa.Column('gross', sa.BigInteger(), nullable=False, server_default=sa.text('0')),
        sa.Column('tax_income', sa.BigInteger(), nullable=False, server_default=sa.text('0')),
        sa.Column('tax_local', sa.BigInteger(), nullable=False, server_default=sa.text('0')),
        sa.Column('vat', sa.BigInteger(), nullable=False, server_default=sa.text('0')),
        sa.Column('net', sa.BigInteger(), nullable=False, server_default=sa.text('0')),
        sa.Column('tax_type', sa.String(16), nullable=False),
        sa.Column('lines', postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('closed_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('closed_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('paid_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('paid_at', sa.DateTime(), nullable=True),
        sa.CheckConstraint("status IN ('CLOSED','PAID')", name='ck_sales_commission_closings_status'),
        sa.UniqueConstraint('user_id', 'month', name='uq_sales_commission_closings_user_month'),
    )


def downgrade() -> None:
    """표를 지운다."""
    op.drop_table('sales_commission_closings')
