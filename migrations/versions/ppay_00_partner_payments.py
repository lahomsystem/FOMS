"""PPAY-00: partner_payments — 협력사 입금 장부

Revision ID: ppay_00
Revises: pstmt_00
Create Date: 2026-11-03

설계 정본: ``docs/specs/2026-11-03-partner-statement_SPEC.md`` §3.4 · §5.7(5단계).

* ``partner_payments`` — 협력사(FK) · 입금일 · 금액(> 0) · 메모 · 어느 명세서 입금인지(FK SET NULL, 비면 오래된 명세서부터 채움) ·
  기록한 사람 · 지운 때 · 지운 사람 · 이유(지우기는 줄을 남긴다).
* ``ix_partner_payments_org_paid_on`` — 협력사 월 장부(날짜 범위) 읽기.

데이터를 바꾸지 않는 표 신설뿐이다. ``downgrade()`` 는 표를 지운다. DDL 은 models.py ``PartnerPayment`` 와 같다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'ppay_00'
down_revision: Union[str, None] = 'pstmt_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """partner_payments 표 만들기."""
    op.create_table(
        'partner_payments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('partner_org_id', sa.Integer(), sa.ForeignKey('partner_orgs.id'), nullable=False),
        sa.Column('paid_on', sa.Date(), nullable=False),
        sa.Column('amount', sa.BigInteger(), nullable=False),
        sa.Column('memo', sa.String(200), nullable=True),
        sa.Column('statement_id', sa.Integer(), sa.ForeignKey('partner_statements.id', ondelete='SET NULL'), nullable=True),
        sa.Column('recorded_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('voided_at', sa.DateTime(), nullable=True),
        sa.Column('voided_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('void_reason', sa.String(200), nullable=True),
        sa.CheckConstraint('amount > 0', name='ck_partner_payments_amount'),
    )
    op.create_index('ix_partner_payments_org_paid_on', 'partner_payments', ['partner_org_id', 'paid_on'])


def downgrade() -> None:
    """표를 지운다."""
    op.drop_index('ix_partner_payments_org_paid_on', table_name='partner_payments')
    op.drop_table('partner_payments')
