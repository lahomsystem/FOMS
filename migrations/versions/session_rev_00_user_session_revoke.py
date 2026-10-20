"""SESSION-REVOKE-01: 사용자 세션 세대 번호·로그아웃 회수 목록 칸

Revision ID: session_rev_00
Revises: partner_02
Create Date: 2026-10-20

왜: 로그인 상태가 서명 쿠키에만 있어 로그아웃·비밀번호 변경·역할 변경 뒤에도 옛 쿠키가
살아 있었다. 요청마다 이미 읽는 사용자 행에 두 칸을 두어 서버가 끊을 수 있게 한다.

무엇을:
* ``users.session_version`` INTEGER NOT NULL DEFAULT 0 — 비밀번호·역할 변경 때 +1.
* ``users.revoked_session_ids`` JSONB NULL — 로그아웃한 세션 표지 목록.

잠금·소요: 상수 기본값 칸·NULL 칸 추가라 PG 11+ 에서 표 재작성 없이 즉시 끝난다.
기존 세션은 번호가 없어 0 으로 읽히므로 배포 때 아무도 로그아웃되지 않는다.

되돌리기: 두 칸을 지운다.

스펙: docs/specs/2026-10-20-session-revoke_SPEC.md
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = 'session_rev_00'
down_revision: Union[str, None] = 'partner_02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """세대 번호·회수 목록 칸 추가."""
    op.add_column('users', sa.Column('session_version', sa.Integer(), nullable=False,
                                     server_default='0'))
    op.add_column('users', sa.Column(
        'revoked_session_ids',
        sa.JSON().with_variant(postgresql.JSONB(), 'postgresql'),
        nullable=True,
    ))


def downgrade() -> None:
    """두 칸 삭제."""
    op.drop_column('users', 'revoked_session_ids')
    op.drop_column('users', 'session_version')
