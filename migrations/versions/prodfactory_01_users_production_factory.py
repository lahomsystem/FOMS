"""PRODFACTORY-01: 계정 공장 — users.production_factory(1 · 2, NULL = 1공장) + CHECK(두 DB)

Revision ID: prodfactory_01
Revises: prodlead_01
Create Date: 2026-11-24

설계 정본: ``docs/specs/2026-11-23-production-self-claim-and-factory2_SPEC.md`` §3 'P3 2공장' · §6-2 · C9(사장님 승인 2026-11-23).

생산팀 계정마다 1공장 또는 2공장(한 사람 한 공장, '둘 다' 값 없음 — 두 공장은 관리자만). 비면 1공장 = 지금과 같다(채우기 없음).

upgrade(코드보다 먼저 도는 predeploy — 옛 코드는 이 칸을 모르고 그대로 돈다: 사용자 행을 읽을 때 칸을 집어 읽고, 새 행은 이 칸을
비워 넣으니 NULL 이라 CHECK 를 지난다):
  칸 더하기 ``production_factory`` SmallInteger NULL 허용 + 칸 CHECK ``ck_users_production_factory``(NULL 또는 1 · 2). 기본값 · 색인 ·
  채우기 없음 — PG 는 표를 다시 쓰지 않고(NULL 칸) CHECK 검사만 한 번(users 는 작은 표, 모두 NULL 이라 지난다). SQLite 는 칸에 붙은
  CHECK 로 같은 뜻(ALTER TABLE ADD COLUMN 이 받는 꼴).

downgrade = (PG) CHECK 지움 → 칸 지움. **다른 칸은 건드리지 않는다**(2단계 검토 교훈 — 되돌리기가 다른 칸을 덮어쓰지 않는다).
커밋 되돌리기만 해도 옛 코드는 이 칸을 읽지 않으므로 downgrade 는 골라서 해도 된다(2공장 계정은 그동안 1공장 계정처럼 보인다).

마이그레이션 상수 동결 원칙에 따라 ``models`` 를 import 하지 않는다(표 · 칸 · CHECK 글 리터럴). CHECK 글은 models.py
``PRODUCTION_FACTORY_CHECK_SQL`` 과 글자 단위로 같다(시험 ``tests/domains/test_production_factory_account.py`` 가 견준다).
server_default 없음 — migration_chain 지문(models.py ↔ 마이그레이션 재생) 정합.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'prodfactory_01'
down_revision: Union[str, None] = 'prodlead_01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'users'
COLUMN = 'production_factory'
CHECK_NAME = 'ck_users_production_factory'
CHECK_SQL = "production_factory IS NULL OR production_factory IN (1, 2)"


def _dialect() -> str:
    """지금 연결의 방언 이름(postgresql · sqlite)."""
    return op.get_bind().dialect.name


def upgrade() -> None:
    """칸 더하기(칸에 붙은 CHECK 와 함께 — 두 DB 같은 꼴)."""
    op.add_column(TABLE, sa.Column(COLUMN, sa.SmallInteger(), sa.CheckConstraint(CHECK_SQL, name=CHECK_NAME),
                                   nullable=True))


def downgrade() -> None:
    """(PG) CHECK 지움 → 칸 지움. 다른 칸은 그대로."""
    if _dialect() == 'postgresql':
        op.drop_constraint(CHECK_NAME, TABLE, type_='check')
    op.drop_column(TABLE, COLUMN)
