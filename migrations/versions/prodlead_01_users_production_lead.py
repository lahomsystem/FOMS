"""PRODLEAD-01: 반장 따로 지정 — users.production_lead(참 = 반장) + 지금 '파트 없는 생산팀' 계정을 반장으로 채우기

Revision ID: prodlead_01
Revises: prodparts_01
Create Date: 2026-11-24

설계 정본: ``docs/specs/2026-11-23-production-self-claim-and-factory2_SPEC.md`` 맨 위 '승인 때 고친 것' 5(사장님 2026-11-24
"반장을 따로 지정하기"). 2단계(P2)는 파트 없는 생산팀 계정을 모두 반장(대신)으로 봤다. 이제 관리자가 체크한 계정만 반장이고
(네 파트 도면 대신 처리 · 공정 체크칸 손 체크), 파트도 반장도 아닌 생산팀 계정은 보기만 한다.

upgrade(코드보다 먼저 도는 predeploy — 옛 코드는 이 칸을 모르고 그대로 돈다):
  1. 칸 더하기 ``production_lead`` Boolean NULL 허용 — 기본값 · 색인 없음(PG 는 표를 다시 쓰지 않는다, 잠금 짧음).
  2. 채우기 — 생산팀 · 활성 여부 무관 · 파트 없음 · 역할 STAFF · MANAGER(VIEWER 제외) 계정을 참으로. '파트 없음'은 앱 판정
     (``part_constants.stored_production_parts``)과 같은 뜻 = 옛 칸 ``production_part`` NULL — 새 칸에 목록이 남아 있어도 옛 칸이
     비면 앱은 파트 없음(옛 코드가 나중에 '없음'으로 고친 행)으로 본다. 지금 운영에서 이 계정들이 공정 체크칸 · [제작 시작] · [제작 완료]를 쓰고 있어,
     채우지 않으면 새 코드가 올라가는 순간 공정 체크가 막힌다. 다시 돌려도 같다(같은 행을 같은 값으로).
     팀 · 역할 글은 앱 판정과 같은 꼴로 견준다(앞뒤 빈칸 빼고 대문자 — ``order_mutation_policy.normalize_team`` · 생산 쓰기 판정).

새로 추가 · 승인하는 계정의 기본은 반장 아님(NULL). downgrade = 칸 지움(다른 칸은 건드리지 않는다 — 옛 코드는 파트 없는 생산팀을
다시 반장으로 본다). 커밋 되돌리기만 해도 옛 코드는 이 칸을 읽지 않으므로 downgrade 는 골라서 해도 된다.

마이그레이션 상수 동결 원칙에 따라 ``models`` 를 import 하지 않는다(표 · 칸 · 팀 · 역할 글 리터럴). 채우기 조건 글
(:data:`FILL_WHERE`)은 운영에 올리기 전 셀 읽기 전용 집계와 글자 그대로 같다(시험이 본다).
server_default 없음 — migration_chain 지문(models.py ↔ 마이그레이션 재생) 정합.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'prodlead_01'
down_revision: Union[str, None] = 'prodparts_01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'users'
COLUMN = 'production_lead'

#: 채우기 조건(두 방언 같은 글) — 옛 칸이 비면 파트 없음(앱 ``stored_production_parts`` 와 같은 판정).
FILL_WHERE = ("upper(trim(team)) = 'PRODUCTION' AND upper(trim(role)) IN ('STAFF', 'MANAGER') "
              "AND production_part IS NULL")


def upgrade() -> None:
    """칸 더하기 → 지금 '파트 없는 생산팀'(STAFF · MANAGER)을 반장으로 채우기."""
    op.add_column(TABLE, sa.Column(COLUMN, sa.Boolean(), nullable=True))
    op.execute(sa.text(f"UPDATE users SET production_lead = :lead WHERE {FILL_WHERE}").bindparams(lead=True))


def downgrade() -> None:
    """칸 지움(다른 칸은 그대로)."""
    op.drop_column(TABLE, COLUMN)
