"""PARTNER-01: 외부 협력사 표 + 사용자·주문의 협력사 칸

Revision ID: partner_00
Revises: draftidx_00
Create Date: 2026-10-08

왜: 외부 협력사가 영업·실측·초안 도면까지 하고 우리에게 넘기는 주문을 받는다. 지금 앱은
로그인한 사용자 누구나 모든 주문을 읽을 수 있고(``user_can_read_order`` 전역 허용), 회사 개념이
없다. 협력사 계정이 자기 회사 주문만 보게 하려면 판정 축이 되는 ID 칸이 필요하다.

무엇을:
* ``partner_orgs`` 표 생성.
* ``users.partner_org_id`` (FK, 색인) + CHECK ``ck_users_partner_role_org`` —
  협력사 계정(role PARTNER)은 반드시 협력사 id 가 있고, 우리 직원은 반드시 없다.
  기존 행은 role 이 PARTNER 가 아니고 새 칸이 NULL 이라 모두 통과한다.
* ``orders.partner_org_id`` (FK) + 부분 색인 ``ix_orders_partner_org_id``
  (``WHERE partner_org_id IS NOT NULL``). 기존 행은 전부 NULL 이라 색인이 비어 있다.

잠금·소요: 새 칸은 기본값 없는 NULL 칸이라 표를 다시 쓰지 않는다(메타데이터만 바뀜). FK 검증과
CHECK 검증은 전 행이 NULL·비협력사라 즉시 끝난다. 부분 색인도 대상 행 0개라 즉시 만들어진다.

되돌리기: ``downgrade()`` 는 만든 역순으로 지운다. 협력사 주문·계정이 이미 생겼다면 그 연결이
사라지므로, 되돌리기 전에 협력사 계정을 끄고 주문의 협력사 표식을 따로 백업한다.

스펙: docs/specs/2026-10-08-partner-portal_SPEC.md (§3, 1단계)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = 'partner_00'
down_revision: Union[str, None] = 'draftidx_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = 'partner_orgs'
USERS_FK = 'fk_users_partner_org_id_partner_orgs'
USERS_INDEX = 'ix_users_partner_org_id'
USERS_CHECK = 'ck_users_partner_role_org'
USERS_CHECK_SQL = "(upper(role) = 'PARTNER') = (partner_org_id IS NOT NULL)"
ORDERS_FK = 'fk_orders_partner_org_id_partner_orgs'
ORDERS_INDEX = 'ix_orders_partner_org_id'


def upgrade() -> None:
    """협력사 표 → 사용자 칸·제약 → 주문 칸·부분 색인 순으로 만든다."""
    op.create_table(
        TABLE,
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(length=100), nullable=False, unique=True),
        sa.Column('biz_reg_no', sa.String(length=20), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('customer_messaging', sa.String(length=20), nullable=False, server_default='NONE'),
        sa.Column('logo_storage_key', sa.String(length=500), nullable=True),
        sa.Column('contact_name', sa.String(length=100), nullable=True),
        sa.Column('contact_phone', sa.String(length=30), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.add_column('users', sa.Column('partner_org_id', sa.Integer(), nullable=True))
    op.create_foreign_key(USERS_FK, 'users', TABLE, ['partner_org_id'], ['id'])
    op.create_index(USERS_INDEX, 'users', ['partner_org_id'])
    op.create_check_constraint(USERS_CHECK, 'users', sa.text(USERS_CHECK_SQL))

    op.add_column('orders', sa.Column('partner_org_id', sa.Integer(), nullable=True))
    op.create_foreign_key(ORDERS_FK, 'orders', TABLE, ['partner_org_id'], ['id'])
    op.create_index(
        ORDERS_INDEX, 'orders', ['partner_org_id'],
        postgresql_where=sa.text('partner_org_id IS NOT NULL'),
    )


def downgrade() -> None:
    """만든 역순으로 지운다(주문 → 사용자 → 협력사 표)."""
    op.drop_index(ORDERS_INDEX, table_name='orders')
    op.drop_constraint(ORDERS_FK, 'orders', type_='foreignkey')
    op.drop_column('orders', 'partner_org_id')

    op.drop_constraint(USERS_CHECK, 'users', type_='check')
    op.drop_index(USERS_INDEX, table_name='users')
    op.drop_constraint(USERS_FK, 'users', type_='foreignkey')
    op.drop_column('users', 'partner_org_id')

    op.drop_table(TABLE)
