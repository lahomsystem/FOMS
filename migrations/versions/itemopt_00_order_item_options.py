"""ITEMOPT-00: order_item_options — 협력사 품목마다 고른 옵션

Revision ID: itemopt_00
Revises: pricelist_00
Create Date: 2026-11-03

설계 정본: ``docs/specs/2026-11-03-partner-statement_SPEC.md`` §3.2.

* ``order_item_options`` — 주문(order_id FK CASCADE) · 품목 uid(``structured_data.items[].uid``) · 단계(PARTNER 원문 ·
  CURRENT 지금 값 · CONFIRMED 협력사 확정)마다 한 줄. 고른 줄(lines) · 커스텀(customs) · 도면팀이 바꾼 까닭(changes)은
  JSONB, 고를 때 본 단가표 판(price_list_id FK).
* ``uq_order_item_options_item_stage`` — 한 품목의 한 단계는 한 줄(이 제약의 색인이 주문으로 찾기에도 쓰인다).

데이터를 바꾸지 않는 표 신설뿐이다. ``downgrade()`` 는 표를 지운다(옵션 요약 글은 품목 JSON ``option_detail`` 에
그대로 남는다). DDL 은 models.py ``OrderItemOption`` 과 같다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'itemopt_00'
down_revision: Union[str, None] = 'pricelist_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """order_item_options 표 만들기."""
    op.create_table(
        'order_item_options',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('order_id', sa.Integer(), sa.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False),
        sa.Column('item_uid', sa.String(64), nullable=False),
        sa.Column('stage', sa.String(10), nullable=False),
        sa.Column('state', sa.String(10), nullable=False),
        sa.Column('base_key', sa.String(20), nullable=True),
        sa.Column('lines', postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('customs', postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('changes', postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('price_list_id', sa.Integer(), sa.ForeignKey('partner_price_lists.id'), nullable=True),
        sa.Column('updated_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('order_id', 'item_uid', 'stage', name='uq_order_item_options_item_stage'),
        sa.CheckConstraint("stage IN ('PARTNER','CURRENT','CONFIRMED')", name='ck_order_item_options_stage'),
        sa.CheckConstraint("state IN ('chosen','none','later')", name='ck_order_item_options_state'),
    )


def downgrade() -> None:
    """표를 지운다."""
    op.drop_table('order_item_options')
