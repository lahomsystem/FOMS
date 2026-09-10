"""MGRROOM-00: users.channel_drawing_group_id — 담당자별 개인 도면방 (채널톡 그룹 id)

Revision ID: mgrroom_00
Revises: naversettle_02
Create Date: 2026-09-10

도면방 PUSH 를 공용 도면방(230331)과 **주문 담당자의 개인 도면방**에 동시에 보내기
위한 매핑이다. 담당자 목록의 정본이 users 라서(운영 확인: 대상 9명이 전부 users 에
계정으로 있고 출고설정 measurement_manager 는 비어 있다) 사용자 관리 화면에서
등록한다. ``sender_phone`` 과 같은 모양의 사용자별 메시징 속성이다.

NULL 이면 공용 도면방만 나간다 — 담당자 추가·삭제·미등록 모두 이 한 상태로 흡수된다.
숫자 문자열로 저장한다(입력은 URL 도 받아 숫자만 남긴다).

server_default 없음 — migration_chain 지문(models.py ↔ 마이그레이션 재생) 정합.
``downgrade()`` 는 컬럼 drop(설정값 파생 데이터 — 재등록 가능).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'mgrroom_00'
down_revision: Union[str, None] = 'naversettle_02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """users.channel_drawing_group_id 추가."""
    op.add_column('users', sa.Column('channel_drawing_group_id', sa.String(32), nullable=True))


def downgrade() -> None:
    """users.channel_drawing_group_id 제거."""
    op.drop_column('users', 'channel_drawing_group_id')
