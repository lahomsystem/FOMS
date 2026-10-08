"""PARTNER-02: 협력사를 맡는 우리 영업 직원 칸

Revision ID: partner_01
Revises: partner_00
Create Date: 2026-10-08

왜: 협력사가 등록한 주문도 영업 담당(``OrderAssignment`` SALES · quest ``owner_person``)이 우리
직원이어야 한다(``create_order`` 계약 — 담당 배정 행이 권한 판정에 쓰인다). 협력사 계정을 담당으로
두면 외부 사용자가 배정 행에 들어간다. 그래서 협력사마다 우리 쪽 담당 직원을 하나 정해 두고,
협력사 주문은 그 직원을 담당으로 만든다.

무엇을: ``partner_orgs.owner_user_id`` (FK users.id, NULL 허용). 기존 행은 협력사가 아직 없거나
1단계 시험 행뿐이라 NULL 로 둔다 — 담당이 없는 협력사는 주문 등록을 막는다(앱 판정).

잠금·소요: 작은 표에 NULL 칸 추가 + FK. 즉시 끝난다.

되돌리기: FK → 칸 순으로 지운다.

스펙: docs/specs/2026-10-08-partner-portal_SPEC.md (2단계)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = 'partner_01'
down_revision: Union[str, None] = 'partner_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = 'partner_orgs'
OWNER_FK = 'fk_partner_orgs_owner_user_id_users'


def upgrade() -> None:
    """우리 쪽 담당 직원 칸 + FK."""
    op.add_column(TABLE, sa.Column('owner_user_id', sa.Integer(), nullable=True))
    op.create_foreign_key(OWNER_FK, TABLE, 'users', ['owner_user_id'], ['id'])


def downgrade() -> None:
    """FK → 칸 순으로 지운다."""
    op.drop_constraint(OWNER_FK, TABLE, type_='foreignkey')
    op.drop_column(TABLE, 'owner_user_id')
