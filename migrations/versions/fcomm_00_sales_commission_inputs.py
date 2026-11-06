"""FCOMM-00: 프리랜서 영업 수수료 — 회계팀 입력 표(시공비 · 지정 요율)

Revision ID: fcomm_00
Revises: csagent_07
Create Date: 2026-11-06

설계 정본: ``docs/specs/2026-11-06-freelancer-sales-commission_SPEC.md`` §4.2(J4).

* ``sales_commission_inputs`` — 주문(FK CASCADE, PK — 주문마다 한 줄) · 시공비(0 이상) · 회계팀 지정 요율
  (bp 0~10000) · 메모 · 칸 저장 경합 막기 version · 고친 사람 · 고친 때.

데이터를 바꾸지 않는 표 신설뿐이다. ``downgrade()`` 는 표를 지운다. DDL 은 models.py ``SalesCommissionInput`` 와 같다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'fcomm_00'
down_revision: Union[str, None] = 'csagent_07'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """sales_commission_inputs 표 만들기."""
    op.create_table(
        'sales_commission_inputs',
        sa.Column(
            'order_id', sa.Integer(), sa.ForeignKey('orders.id', ondelete='CASCADE'),
            primary_key=True, autoincrement=False,
        ),
        sa.Column('install_cost', sa.BigInteger(), nullable=True),
        sa.Column('rate_override_bp', sa.Integer(), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False, server_default=sa.text('1')),
        sa.Column('updated_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint('install_cost IS NULL OR install_cost >= 0', name='ck_sales_commission_inputs_install_cost'),
        sa.CheckConstraint(
            'rate_override_bp IS NULL OR (rate_override_bp >= 0 AND rate_override_bp <= 10000)',
            name='ck_sales_commission_inputs_rate_bp',
        ),
    )


def downgrade() -> None:
    """표를 지운다."""
    op.drop_table('sales_commission_inputs')
