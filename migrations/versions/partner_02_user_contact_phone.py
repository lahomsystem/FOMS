"""PARTNER-04: 협력사 직원 연락처 칸

Revision ID: partner_02
Revises: partner_01
Create Date: 2026-10-11

왜: 협력사 주문의 담당이 협력사 직원이 되었다(스펙 §16). 도면 "담당 연락처"에 그 직원 번호를
찍어야 하는데, 사용자 표에는 알림톡 발신번호(``sender_phone``)밖에 없다. 발신번호는 문자 발송
명의라 섞지 않고 연락처 칸을 따로 둔다.

무엇을: ``users.contact_phone`` (VARCHAR(30), NULL 허용). 기존 행은 NULL — 관리 화면에서 넣는다.

잠금·소요: NULL 칸 추가(기본값 없음)라 표 재작성 없이 즉시 끝난다.

되돌리기: 칸을 지운다.

스펙: docs/specs/2026-10-08-partner-portal_SPEC.md §16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = 'partner_02'
down_revision: Union[str, None] = 'partner_01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """연락처 칸 추가."""
    op.add_column('users', sa.Column('contact_phone', sa.String(length=30), nullable=True))


def downgrade() -> None:
    """연락처 칸 삭제."""
    op.drop_column('users', 'contact_phone')
