"""PRODPARTS-01: 계정마다 생산 파트 여러 개 — users.production_parts(목록) + 옛 칸에서 채우기 + PG CHECK

Revision ID: prodparts_01
Revises: prodpart_01_handover
Create Date: 2026-11-24

설계 정본: ``docs/specs/2026-11-23-production-self-claim-and-factory2_SPEC.md`` §4-12 · §6-1 · §15(사장님 승인 2026-11-23).

계정마다 파트를 0 ~ 4개(재단 · 엣지 · 조립 · 검수) 정한다. 값은 사용자 행에 목록으로 둔다(안 ⓓ — 요청마다 이미 읽는 행이라
쿼리 0, 연결 표는 요청마다 +1). PostgreSQL 은 JSONB, SQLite(시험 레인)는 JSON.

upgrade(코드보다 먼저 도는 predeploy — 옛 코드는 이 칸을 모르고 그대로 돈다):
  1. 칸 더하기 ``production_parts`` NULL 허용 — 기본값 · 색인 없음(PG 는 표를 다시 쓰지 않는다, 잠금 짧음).
  2. 채우기 — 옛 칸 ``production_part`` 가 있는 행만 ``[옛 값]``(이미 채운 행은 건드리지 않는다 — 다시 돌려도 같다).
  3. CHECK ``ck_users_production_parts``(PG 전용) — NULL 이거나 네 key 만 든 배열. users 는 작은 표라 한 번에 검사한다.

downgrade(되돌리기 §15 — 옛 칸 지우기 ``prodparts_02`` 전까지만): CHECK 를 지우고, 새 칸이 있는 행은 옛 칸을 새 칸 첫 값으로
맞춘 뒤 새 칸을 지운다. 두 번째 이후 파트는 사라진다(옛 코드는 파트 하나만 안다). 커밋 되돌리기만 해도 옛 코드는 옛 칸
(= 새 코드가 늘 같이 쓴 첫 파트)을 읽으므로 downgrade 는 골라서 해도 된다.

옛 칸 ``production_part`` 는 이 판에서 지우지 않는다 — 한 판 동안 새 코드가 둘을 같이 쓴다(관리자 저장 = 새 칸 + 옛 칸 = 첫 파트).
운영 1주 뒤 ``prodparts_02_drop_production_part`` 가 옛 칸을 지운다(이번 판 아님).

마이그레이션 상수 동결 원칙에 따라 ``models`` 를 import 하지 않는다(표 · 칸 · CHECK 글 리터럴). CHECK 글은 models.py
``PRODUCTION_PARTS_CHECK_SQL`` 과 글자 단위로 같다(시험 ``tests/domains/test_production_multi_parts_admin.py`` 가 견준다).
server_default 없음 — migration_chain 지문(models.py ↔ 마이그레이션 재생) 정합.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'prodparts_01'
down_revision: Union[str, None] = 'prodpart_01_handover'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'users'
COLUMN = 'production_parts'
LEGACY_COLUMN = 'production_part'
CHECK_NAME = 'ck_users_production_parts'
CHECK_SQL = (
    "production_parts IS NULL OR (jsonb_typeof(production_parts) = 'array' "
    "AND production_parts <@ '[\"cut\",\"edge\",\"assemble\",\"inspect\"]'::jsonb)"
)
# models.JSONColumn 과 같은 꼴을 리터럴로(모델 import 금지 — 상수 동결).
JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(), 'postgresql')

# 채우기 · 되돌리기 글 — 방언마다 JSON 함수 이름만 다르다(PG = jsonb, SQLite = json1).
_FILL_SQL = {
    'postgresql': ("UPDATE users SET production_parts = jsonb_build_array(production_part) "
                   "WHERE production_part IS NOT NULL AND production_parts IS NULL"),
    'sqlite': ("UPDATE users SET production_parts = json_array(production_part) "
               "WHERE production_part IS NOT NULL AND production_parts IS NULL"),
}
_RESTORE_SQL = {
    'postgresql': "UPDATE users SET production_part = production_parts ->> 0 WHERE production_parts IS NOT NULL",
    'sqlite': "UPDATE users SET production_part = json_extract(production_parts, '$[0]') WHERE production_parts IS NOT NULL",
}


def _dialect() -> str:
    """지금 연결의 방언 이름(postgresql · sqlite)."""
    return op.get_bind().dialect.name


def upgrade() -> None:
    """칸 더하기 → 옛 칸에서 채우기 → (PG) CHECK."""
    op.add_column(TABLE, sa.Column(COLUMN, JSON_TYPE, nullable=True))
    dialect = _dialect()
    op.execute(sa.text(_FILL_SQL[dialect]))
    if dialect == 'postgresql':
        op.create_check_constraint(CHECK_NAME, TABLE, sa.text(CHECK_SQL))


def downgrade() -> None:
    """(PG) CHECK 지움 → 옛 칸을 새 칸 첫 값으로 → 새 칸 지움."""
    dialect = _dialect()
    if dialect == 'postgresql':
        op.drop_constraint(CHECK_NAME, TABLE, type_='check')
    op.execute(sa.text(_RESTORE_SQL[dialect]))
    op.drop_column(TABLE, COLUMN)
