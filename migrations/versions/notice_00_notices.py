"""NOTICE-00: FOMS 공지사항 표 2개 — notices(공지 한 줄) · notice_acks(사람마다 읽음 · 확인)

Revision ID: notice_00
Revises: csagent_04
Create Date: 2026-11-02

설계 정본: docs/specs/2026-11-02-foms-notices_SPEC.md §1.

* ``notices`` — 제목 · 본문 · 쓴 사람 · 받는 쪽(본사 전체 · 팀 코드 목록 · 협력사 전체 · 협력사 id 목록) · 보이는 방식
  (``POPUP`` | ``LIST``, ``ck_notices_display_mode``) · 맨 위 고정 · 게시 기간(UTC) · 만든 때 · 고친 때 · 지운 때(soft).
  받는 사람은 미리 펼치지 않는다(볼 때 판정 — 나중에 들어온 계정도 받는다).
* ``notice_acks`` — (공지, 사람) 하나에 한 줄(``uq_notice_acks_notice_user``) · 읽은 때 · 확인한 때. 공지를 지우면
  같이 지워진다(ON DELETE CASCADE). ``ix_notice_acks_user_id`` 는 내 공지 목록 · 안 읽음 수 질의용.

데이터를 바꾸지 않는다(새 표). ``downgrade()`` 는 만든 역순으로 지운다(공지 · 확인 기록이 사라진다 — 무손실 아님).
DDL 은 models.py ``Notice`` · ``NoticeAck`` 와 같다. 상수 동결 원칙에 따라 models 를 import 하지 않는다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'notice_00'
down_revision: Union[str, None] = 'csagent_04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _json() -> sa.types.TypeEngine:
    return sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql')


def upgrade() -> None:
    """notices · notice_acks 표와 제약 · 색인을 만든다."""
    op.create_table(
        'notices',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('body', sa.Text(), nullable=False, server_default=''),
        sa.Column('created_by_user_id', sa.Integer(),
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_by_name', sa.String(100), nullable=True),
        sa.Column('audience_staff_all', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('audience_staff_teams', _json(), nullable=True),
        sa.Column('audience_partner_all', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('audience_partner_org_ids', _json(), nullable=True),
        sa.Column('display_mode', sa.String(20), nullable=False, server_default='LIST'),
        sa.Column('pinned', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('starts_at', sa.DateTime(), nullable=True),
        sa.Column('ends_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.CheckConstraint("display_mode IN ('POPUP','LIST')", name='ck_notices_display_mode'),
    )
    op.create_table(
        'notice_acks',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('notice_id', sa.Integer(),
                  sa.ForeignKey('notices.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Integer(),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('read_at', sa.DateTime(), nullable=True),
        sa.Column('ack_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('notice_id', 'user_id', name='uq_notice_acks_notice_user'),
    )
    op.create_index('ix_notice_acks_user_id', 'notice_acks', ['user_id'])


def downgrade() -> None:
    """만든 역순 — 색인 → notice_acks → notices."""
    op.drop_index('ix_notice_acks_user_id', table_name='notice_acks')
    op.drop_table('notice_acks')
    op.drop_table('notices')
