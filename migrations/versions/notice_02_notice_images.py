"""NOTICE-02: 공지 사진 — notices.images (JSONB 목록, 비면 [])

Revision ID: notice_02
Revises: brain_00
Create Date: 2026-11-02

설계 정본: docs/specs/2026-11-02-foms-notices_SPEC.md §8(사진 첨부). 지금 머리가 ``brain_00`` 이라 머리 하나를 지키려고 그 뒤로 잇는다.

* ``notices.images`` — 공지에 붙인 사진 목록(보이는 순서 그대로, 최대 5장). 항목 ``{key, thumb_key, name, width, height, size}``.
  ``key`` · ``thumb_key`` 는 관리자 업로드 API(``POST /api/admin/notices/images``)가 만든 저장소 key(``notices/images/...``)뿐이다.
  NOT NULL · 기본 ``'[]'`` — 이미 있는 공지는 사진 없음으로 채워진다(데이터 변경 없음).

``downgrade()`` 는 칸을 지운다(붙인 사진 목록이 사라진다 — 저장소 파일은 남는다).
DDL 은 models.py ``Notice.images`` 와 같다. 상수 동결 원칙에 따라 models 를 import 하지 않는다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'notice_02'
down_revision: Union[str, None] = 'brain_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NOTICES = 'notices'
_JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql')


def upgrade() -> None:
    """``notices.images`` JSONB NOT NULL DEFAULT '[]'."""
    op.add_column(
        NOTICES,
        sa.Column('images', _JSON, nullable=False, server_default=sa.text("'[]'")),
    )


def downgrade() -> None:
    """``notices.images`` 를 지운다."""
    op.drop_column(NOTICES, 'images')
