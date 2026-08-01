"""PASSWORD-POLICY-01: users.password_policy_version (강도 정책 버전 컬럼)

Revision ID: password_policy_00
Revises: shipment_reference_00
Create Date: 2026-07-27

비밀번호 강도 정책을 **명시 버전 컬럼**으로 추적한다(강도 SSOT). 단일 additive 마이그레이션:

``users.password_policy_version`` (Integer, NOT NULL, server_default ``'0'``) 를 추가한다.
``0`` = LEGACY(강도 미검증·약할 수 있음), ``1`` = STRONG. **기존 모든 행은 server_default
로 LEGACY(0) 로 backfill** 한다 — 저장된 hash 를 rehash 해서 강도를 추정하지 않는다(단방향
hash 로 강도를 역산할 수 없고, 추정은 legacy 계정을 조용히 strong 으로 오분류한다). 새/변경
비번만 애플리케이션이 설정 시점에 STRONG 으로 명시 기록한다.

정책 버전 값의 SSOT 는 ``foms.services.security.password_policy`` 상수
(``POLICY_VERSION_LEGACY``/``POLICY_VERSION_STRONG``)이며, 이 마이그레이션의 server_default
``'0'`` 은 그 LEGACY 값과 일치한다. ``downgrade()`` 는 컬럼을 제거한다(무손실 역변환 —
정책 버전은 파생 메타데이터라 컬럼 제거로 데이터 유실 없음).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'password_policy_00'
down_revision: Union[str, None] = 'shipment_reference_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """users.password_policy_version 컬럼 추가(NOT NULL, 기존 행 server_default=LEGACY)."""
    op.add_column(
        'users',
        sa.Column(
            'password_policy_version',
            sa.Integer(),
            nullable=False,
            server_default=sa.text('0'),  # 0 = LEGACY (강도 미검증). hash 추정 없이 명시 backfill.
        ),
    )


def downgrade() -> None:
    """password_policy_version 컬럼 제거(파생 메타데이터라 무손실)."""
    op.drop_column('users', 'password_policy_version')
