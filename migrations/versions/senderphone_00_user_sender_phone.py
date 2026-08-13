"""SENDERPHONE-00: users.sender_phone — 공유 링크 문자 개인 발신번호 (D2)

Revision ID: senderphone_00
Revises: itemuid_00
Create Date: 2026-08-12

고객 공유 채널 Phase A T8(스펙: docs/specs/2026-08-11-customer-share-phase-a-design.md
§3.3 D2). 개인 명의 발신을 쓰는 영업 인원만 관리자 UI(/admin/users)에서 등록하며,
NULL 이면 회사 대표번호(``SOLAPI_SENDER_PHONE``) 폴백이다. Solapi 발신번호 사전 등록
전제 — 미등록 번호는 벤더 오류("발신번호 미등록")로 표면화된다.

server_default 없음 — migration_chain 지문(models.py ↔ 마이그레이션 재생) 정합.
``downgrade()`` 는 컬럼 drop(설정값 파생 데이터 — 재등록 가능, 무손실 아님을 감수).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'senderphone_00'
down_revision: Union[str, None] = 'itemuid_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """users.sender_phone 추가."""
    op.add_column('users', sa.Column('sender_phone', sa.String(20), nullable=True))


def downgrade() -> None:
    """users.sender_phone 제거."""
    op.drop_column('users', 'sender_phone')
