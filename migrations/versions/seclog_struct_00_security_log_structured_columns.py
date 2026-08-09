"""AUDIT-LOG T8: security_logs 구조화 컬럼 + 대상 조회 인덱스

Revision ID: seclog_struct_00
Revises: access_log_00
Create Date: 2026-08-07

``security_logs`` 는 자유 텍스트 ``message`` 1컬럼짜리 감사 원장이라 "누가 무엇을 바꿨나"를
SQL 로 물을 수 없었다(스펙 §1-2, ``web/admin/audit.py`` 조회가 ILIKE 뿐). 이 마이그레이션은
질의 가능한 구조화 컬럼 4개를 **additive** 로 추가한다:

* ``action``(64) — 행위 종류 태그(``USER_UPDATE``·``LOGIN_FAIL``·``ACCESS_DENIED`` 등).
* ``target_type``(32)/``target_id`` — 행위 대상(``user`` 등 + 대상 PK).
* ``detail`` — 구조화 부가정보(JSONB on PostgreSQL). 기존에 버려지던 ``log_access``
  의 ``additional_data`` 가 여기에 격납된다.

인덱스 ``ix_security_logs_target`` 는 "이 대상에게 무슨 일이 있었나"
(``WHERE target_type = ? AND target_id = ? ORDER BY timestamp DESC``) 조사 질의용이다.
**``models.py`` 의 ``SecurityLog.__table_args__`` 와 이름·컬럼 순서가 완전히 같아야 한다** —
스키마를 ``create_all`` 로 만드는 레인(pytest·PG 테스트 레인)과 alembic 레인이 서로 다른
스키마가 되면 체인 왕복 테스트가 red 로 잡는다.

기존 행 백필은 하지 않는다(스펙 §6 범위 밖) — 전부 NULL 로 남고 ``message`` 의미는 불변이다.
기존 trgm 인덱스(``ix_security_logs_message_trgm``, ``phase_f``)는 건드리지 않는다.

마이그레이션 상수 동결 원칙에 따라 ``models`` 를 import 하지 않는다(테이블/컬럼명 리터럴).
``downgrade()`` 는 인덱스 → 컬럼 순으로 되돌린다(구조화 정보만 소실, ``message`` 는 보존).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'seclog_struct_00'
down_revision: Union[str, None] = 'access_log_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'security_logs'
TARGET_INDEX = 'ix_security_logs_target'
# models.JSONColumn 과 같은 형태를 리터럴로 재현한다(모델 import 금지 — 상수 동결).
_JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(), 'postgresql')


def upgrade() -> None:
    """구조화 컬럼 4개(action·target_type·target_id·detail) + 대상 조회 인덱스 추가."""
    op.add_column(TABLE, sa.Column('action', sa.String(length=64), nullable=True))
    op.add_column(TABLE, sa.Column('target_type', sa.String(length=32), nullable=True))
    op.add_column(TABLE, sa.Column('target_id', sa.Integer(), nullable=True))
    op.add_column(TABLE, sa.Column('detail', _JSON_TYPE, nullable=True))
    op.create_index(TARGET_INDEX, TABLE, ['target_type', 'target_id', 'timestamp'])


def downgrade() -> None:
    """생성 역순으로 인덱스 → 구조화 컬럼 제거(``message``·기존 행은 보존)."""
    op.drop_index(TARGET_INDEX, table_name=TABLE)
    op.drop_column(TABLE, 'detail')
    op.drop_column(TABLE, 'target_id')
    op.drop_column(TABLE, 'target_type')
    op.drop_column(TABLE, 'action')
