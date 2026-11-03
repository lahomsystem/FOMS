"""PSTMT-00: partner_statements · partner_statement_questions — 협력사 거래명세서 · 금액 문의

Revision ID: pstmt_00
Revises: itemopt_00
Create Date: 2026-11-03

설계 정본: ``docs/specs/2026-11-03-partner-statement_SPEC.md`` §3.3 · §3.5.

* ``partner_statements`` — 주문(order_id FK CASCADE)마다 여러 장(수정본 · 추가 작업). DRAFT → ISSUED → VOID.
  번호(doc_no unique, 발행 때 정함) · 일자 · 단가표 판(FK) · 확정 도면 회차 · 파일 열쇠 스냅샷 · 묶음(groups JSONB) ·
  합계 · 공급가액 · 세액 · 잔액 스냅샷 · 수정본 고리(revision_of FK self) · 협력사가 열어 봄 · 확인함.
* ``uq_partner_statements_order_draft`` — 주문마다 DRAFT 는 하나(부분 유니크).
* ``partner_statement_questions`` — 명세서(FK CASCADE) 줄 골라 묻기 · 답.

데이터를 바꾸지 않는 표 신설뿐이다. ``downgrade()`` 는 자식(문의)부터 표를 지운다. DDL 은 models.py 와 같다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'pstmt_00'
down_revision: Union[str, None] = 'itemopt_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """partner_statements · partner_statement_questions 표 만들기."""
    op.create_table(
        'partner_statements',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('partner_org_id', sa.Integer(), sa.ForeignKey('partner_orgs.id'), nullable=False),
        sa.Column('order_id', sa.Integer(), sa.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False),
        sa.Column('doc_no', sa.String(30), nullable=True, unique=True),
        sa.Column('statement_date', sa.Date(), nullable=True),
        sa.Column('status', sa.String(10), nullable=False, server_default='DRAFT'),
        sa.Column('revision_of', sa.Integer(), sa.ForeignKey('partner_statements.id'), nullable=True),
        sa.Column('price_list_id', sa.Integer(), sa.ForeignKey('partner_price_lists.id'), nullable=True),
        sa.Column('drawing_round', sa.Integer(), nullable=True),
        sa.Column('drawing_keys', postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('groups', postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('total', sa.BigInteger(), nullable=False, server_default=sa.text('0')),
        sa.Column('supply', sa.BigInteger(), nullable=False, server_default=sa.text('0')),
        sa.Column('vat', sa.BigInteger(), nullable=False, server_default=sa.text('0')),
        sa.Column('prev_balance', sa.BigInteger(), nullable=True),
        sa.Column('after_balance', sa.BigInteger(), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('issued_at', sa.DateTime(), nullable=True),
        sa.Column('issued_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('voided_at', sa.DateTime(), nullable=True),
        sa.Column('voided_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('partner_viewed_at', sa.DateTime(), nullable=True),
        sa.Column('partner_ack_at', sa.DateTime(), nullable=True),
        sa.Column('partner_ack_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False, server_default=sa.text('1')),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('DRAFT','ISSUED','VOID')", name='ck_partner_statements_status'),
    )
    op.create_index('ix_partner_statements_order_id', 'partner_statements', ['order_id'])
    op.create_index('ix_partner_statements_org_status', 'partner_statements', ['partner_org_id', 'status'])
    op.create_index('uq_partner_statements_order_draft', 'partner_statements', ['order_id'], unique=True,
                    postgresql_where=sa.text("status = 'DRAFT'"))
    op.create_table(
        'partner_statement_questions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('statement_id', sa.Integer(), sa.ForeignKey('partner_statements.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('line_ref', sa.String(20), nullable=True),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('asked_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('asked_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('answer', sa.Text(), nullable=True),
        sa.Column('answered_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('answered_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_partner_statement_questions_statement_id', 'partner_statement_questions', ['statement_id'])


def downgrade() -> None:
    """자식(문의)부터 표를 지운다."""
    op.drop_index('ix_partner_statement_questions_statement_id', table_name='partner_statement_questions')
    op.drop_table('partner_statement_questions')
    op.drop_index('uq_partner_statements_order_draft', table_name='partner_statements')
    op.drop_index('ix_partner_statements_org_status', table_name='partner_statements')
    op.drop_index('ix_partner_statements_order_id', table_name='partner_statements')
    op.drop_table('partner_statements')
