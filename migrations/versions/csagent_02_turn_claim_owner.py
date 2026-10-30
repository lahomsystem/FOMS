"""CSAGENT-02: cs_agent_turns — 선점 주인 · 만료 칸과 빠른 길의 두 상태('지난 초안' · '직원 답함')

Revision ID: csagent_02
Revises: csagent_01
Create Date: 2026-10-30

설계 정본: 설계서 2026-10-27-cs-ai-agent 17.3(구조 네 줄), 실행 플랜 C10-1(원장 R10-1 · R10-2 · R10-4 · R10-31).

* ``claim_owner`` — 차례를 선점한 실행 단위(예 ``realtime:호스트:pid`` · ``pass:호스트:pid``). 코드 꼴 글만.
* ``claim_expires_at`` — 선점 만료(UTC naive). 빠른 길은 시간 상한 + 여유(처음 값 90초), 15분 바퀴는 예전처럼 20분.
  만료가 지난 ``claimed`` 줄은 죽은 차례다 — 빠른 길이 ``failed`` 로 정리한 뒤 시도 상한 안에서 다시 집는다.
* ``ck_cs_agent_turns_state`` — 상태 여섯 가지에 두 가지를 더한다: ``superseded``(집은 뒤 손님이 더 써서 갈아 끼운
  차례 — '지난 초안') · ``staff_replied``(직원이 먼저 공개 답을 해 닫은 차례 — '직원 답함').

다음 묶음(C10-4 사례 칸)이 같은 표에 칸을 더하므로 여기에는 C10-1 에 필요한 칸만 둔다. 데이터를 바꾸지 않는다.
``downgrade()`` 는 새 상태 줄을 ``skipped`` 로 돌리고(까닭 코드가 비었으면 그 상태 이름을 적는다 — 무손실 아님) 옛
제약을 다시 건 뒤 칸을 지운다. DDL 은 models.py ``CsAgentTurn`` 과 같다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'csagent_02'
down_revision: Union[str, None] = 'csagent_01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'cs_agent_turns'
CHECK_NAME = 'ck_cs_agent_turns_state'
OLD_STATES = ('claimed', 'posting', 'posted', 'stored', 'skipped', 'failed')
NEW_STATES = OLD_STATES + ('superseded', 'staff_replied')


def _state_check(states: Sequence[str]) -> str:
    """상태 검사 제약 식 — ``state IN ('claimed', …)``."""
    return "state IN (" + ",".join(f"'{state}'" for state in states) + ")"


def upgrade() -> None:
    """선점 주인 · 만료 칸을 더하고 상태 검사 제약을 새 상태까지 넓힌다."""
    op.add_column(TABLE, sa.Column('claim_owner', sa.String(64), nullable=True))
    op.add_column(TABLE, sa.Column('claim_expires_at', sa.DateTime(), nullable=True))
    op.drop_constraint(CHECK_NAME, TABLE, type_='check')
    op.create_check_constraint(CHECK_NAME, TABLE, _state_check(NEW_STATES))


def downgrade() -> None:
    """새 상태 줄을 'skipped'(까닭 코드 = 그 상태 이름)로 돌리고 옛 제약을 다시 건 뒤 칸을 지운다."""
    new_only = ",".join(f"'{state}'" for state in NEW_STATES if state not in OLD_STATES)
    op.execute(f"UPDATE {TABLE} SET error_code = COALESCE(error_code, state), state = 'skipped' "
               f"WHERE state IN ({new_only})")
    op.drop_constraint(CHECK_NAME, TABLE, type_='check')
    op.create_check_constraint(CHECK_NAME, TABLE, _state_check(OLD_STATES))
    op.drop_column(TABLE, 'claim_expires_at')
    op.drop_column(TABLE, 'claim_owner')
