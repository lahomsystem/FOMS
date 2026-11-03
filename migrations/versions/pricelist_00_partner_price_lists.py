"""PRICELIST-00: partner_price_lists — 협력사 단가표 판

Revision ID: pricelist_00
Revises: brain_02
Create Date: 2026-11-03

설계 정본: ``docs/specs/2026-11-03-partner-statement_SPEC.md`` §3.1.

* ``partner_price_lists`` — 협력사마다 단가표 판(1, 2, 3 …). 저장하면 새 판이 ACTIVE 가 되고 옛 판은
  RETIRED 로 남는다. ``sheet`` 는 단가표 모양 + 줄마다 계산 정보(JSONB), ``rules`` 는 반올림 자리 등.
* ``uq_partner_price_lists_org_version`` — 협력사 안에서 판 번호는 하나씩.
* ``uq_partner_price_lists_active`` — 협력사마다 ACTIVE 판은 하나(부분 유니크).

데이터를 바꾸지 않는 표 신설뿐이다. ``downgrade()`` 는 만든 역순으로 지운다. DDL 은 models.py
``PartnerPriceList`` 와 같다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'pricelist_00'
down_revision: Union[str, None] = 'brain_02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """partner_price_lists 표 · 색인 만들기."""
    op.create_table(
        'partner_price_lists',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('partner_org_id', sa.Integer(), sa.ForeignKey('partner_orgs.id'), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('label', sa.String(40), nullable=False),
        sa.Column('effective_from', sa.Date(), nullable=False),
        sa.Column('status', sa.String(10), nullable=False, server_default='ACTIVE'),
        sa.Column('sheet', postgresql.JSONB(), nullable=False),
        sa.Column('rules', postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('partner_org_id', 'version', name='uq_partner_price_lists_org_version'),
        sa.CheckConstraint("status IN ('DRAFT','ACTIVE','RETIRED')", name='ck_partner_price_lists_status'),
    )
    op.create_index(
        'uq_partner_price_lists_active', 'partner_price_lists', ['partner_org_id'],
        unique=True, postgresql_where=sa.text("status = 'ACTIVE'"),
    )


def downgrade() -> None:
    """만든 역순으로 지운다."""
    op.drop_index('uq_partner_price_lists_active', table_name='partner_price_lists')
    op.drop_table('partner_price_lists')
