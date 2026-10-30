"""CSAGENT-03: cs_agent_turns — 사례 기억 칸(L0 학습 짝) + 같은 브랜드 비슷한 사례 찾기 trgm 색인

Revision ID: csagent_03
Revises: csagent_02
Create Date: 2026-10-30

설계 정본: 설계서 2026-10-27-cs-ai-agent 17.2('사례 기억' · '되먹임 막기' · '직원 정보') · 17.5 · 17.6 L0, 실행 플랜 C10-4
(원장 S10-1 · S10-2 · R10-5 · R10-28). 새 표 없이 차례 줄에 칸을 더한다 — 보관 기간은 차례 줄과 같다.

* ``masked_question`` — 그 차례 손님 글(가림 검사를 넘은 것만)의 가린 사본.
* ``outcome`` — 끝난 꼴: ``as_is`` 그대로 · ``edited`` 고침 · ``direct`` 직접 답 · ``copied`` 복사(학습 무게 0) ·
  ``discarded`` 버림. ``ck_cs_agent_turns_outcome`` 이 이 다섯만 받는다(비면 아직 사례 아님).
* ``edit_ratio`` — 고친 정도 0~1(``ck_cs_agent_turns_edit_ratio``). ``edit_reason`` — 고친 까닭 코드(``wrong_fact`` ·
  ``promise`` · ``tone`` · ``missing`` · ``other`` — 2주차 C10-3 화면이 채움, ``ck_cs_agent_turns_edit_reason``).
* ``sent_by_user_id`` — [보내기]를 누른 FOMS 사용자 id(2주차, FK 없음 — 계정을 지워도 사례가 남는다). ADMIN 만 본다.
* ``desk_manager_id`` — 데스크에서 직접 답한 상담원 id(채널톡 manager id, 1주차 직접 답이 채움). ADMIN 만 본다.
* ``sent_message_id`` — 우리가 보낸 공개 글 id(2주차) — 웹훅 · Open API 로 돌아온 그 글을 '직접 답'에서 뺀다(R10-5).
* ``quote_lines`` — 견적 줄(JSON — C10-6 이 채움). ``held_out`` — 시험용 떼어 둔 사례(평가 묶음 C12-1, 처음 false).
* ``ix_cs_agent_turns_question_trgm`` — ``masked_question`` gin_trgm_ops(PostgreSQL 전용 — SQLite 레인은 건너뛴다).
  pg_trgm 은 이미 쓰는 확장이다(``phase_d_trgm_indexes``) — 없을 때만 만든다. 차례 표는 작고(하루 수백 줄) 쓰는 쪽이
  WORKER 하나라 트랜잭션 안의 보통 ``CREATE INDEX`` 로 만든다(``naverfail_00`` 과 같은 꼴 — 되돌리기도 한 트랜잭션).

데이터를 바꾸지 않는다(새 칸은 비고 ``held_out`` 은 false). ``downgrade()`` 는 만든 역순으로 색인 → 제약 → 칸을 지운다
(사례 칸 값은 사라진다 — 무손실 아님). DDL 은 models.py ``CsAgentTurn`` 과 같다(시험이 글자 단위로 견준다). 상수 동결
원칙에 따라 models 를 import 하지 않는다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'csagent_03'
down_revision: Union[str, None] = 'csagent_02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'cs_agent_turns'
OUTCOMES = ('as_is', 'edited', 'direct', 'copied', 'discarded')
EDIT_REASONS = ('wrong_fact', 'promise', 'tone', 'missing', 'other')
OUTCOME_CHECK = 'ck_cs_agent_turns_outcome'
EDIT_REASON_CHECK = 'ck_cs_agent_turns_edit_reason'
EDIT_RATIO_CHECK = 'ck_cs_agent_turns_edit_ratio'
EDIT_RATIO_SQL = "edit_ratio >= 0 AND edit_ratio <= 1"
INDEX_NAME = 'ix_cs_agent_turns_question_trgm'
CREATE_INDEX_SQL = f"CREATE INDEX IF NOT EXISTS {INDEX_NAME} ON {TABLE} USING gin (masked_question gin_trgm_ops)"
DROP_INDEX_SQL = f"DROP INDEX IF EXISTS {INDEX_NAME}"

_JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(), 'postgresql')
#: 더하는 칸 — (이름, 꼴, NULL 허용, 서버 기본값). 순서 = upgrade 순서(downgrade 는 거꾸로).
COLUMNS: tuple[tuple[str, sa.types.TypeEngine, bool, object], ...] = (
    ('masked_question', sa.Text(), True, None),
    ('outcome', sa.String(16), True, None),
    ('edit_ratio', sa.Numeric(4, 3), True, None),
    ('edit_reason', sa.String(16), True, None),
    ('sent_by_user_id', sa.Integer(), True, None),
    ('desk_manager_id', sa.String(64), True, None),
    ('sent_message_id', sa.String(64), True, None),
    ('quote_lines', _JSON_TYPE, True, None),
    ('held_out', sa.Boolean(), False, sa.text('false')),
)


def in_check(column: str, values: Sequence[str]) -> str:
    """값 목록 검사 제약 식 — ``column IN ('a','b')``(모델 ``CheckConstraint`` 와 같은 글자)."""
    return f"{column} IN (" + ",".join(f"'{value}'" for value in values) + ")"


def upgrade() -> None:
    """사례 칸 · 검사 제약을 더하고, PostgreSQL 이면 trgm 색인을 만든다."""
    for name, type_, nullable, default in COLUMNS:
        op.add_column(TABLE, sa.Column(name, type_, nullable=nullable, server_default=default))
    op.create_check_constraint(OUTCOME_CHECK, TABLE, in_check('outcome', OUTCOMES))
    op.create_check_constraint(EDIT_REASON_CHECK, TABLE, in_check('edit_reason', EDIT_REASONS))
    op.create_check_constraint(EDIT_RATIO_CHECK, TABLE, EDIT_RATIO_SQL)
    if op.get_bind().dialect.name == 'postgresql':
        op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        op.execute(sa.text(CREATE_INDEX_SQL))


def downgrade() -> None:
    """만든 역순 — (PostgreSQL 이면) 색인 → 검사 제약 → 칸. pg_trgm 확장은 다른 색인이 써서 지우지 않는다."""
    if op.get_bind().dialect.name == 'postgresql':
        op.execute(sa.text(DROP_INDEX_SQL))
    op.drop_constraint(EDIT_RATIO_CHECK, TABLE, type_='check')
    op.drop_constraint(EDIT_REASON_CHECK, TABLE, type_='check')
    op.drop_constraint(OUTCOME_CHECK, TABLE, type_='check')
    for name, _type, _nullable, _default in reversed(COLUMNS):
        op.drop_column(TABLE, name)
