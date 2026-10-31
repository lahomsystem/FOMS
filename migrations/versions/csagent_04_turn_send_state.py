"""CSAGENT-04: cs_agent_turns — [보내기] · [수정하기] 칸(보내기 상태 · 보낸 때 · 누름 밀리초 · 고칠 말)과 시간 지표 칸

Revision ID: csagent_04
Revises: csagent_03
Create Date: 2026-10-31

설계 정본: 설계서 2026-10-27-cs-ai-agent 17.2('누를 때 서버가 확인하는 것' 1~5) · 17.2.1(링크 길) · 17.3('잰다'), 실행 플랜
C10-3 · C10-5(원장 R10-9 ~ R10-11 · R10-16 · R10-7 · D68). 보낼 글의 원문은 두지 않는다 — 글은 가린 칸에만.

* ``placed_at`` — 초안을 내부 메모로 올리거나 저장만 한 때(UTC) — '초안 뜸' 지표(C10-5). ``updated_at`` 은 뒤 쓰기가 바꾼다.
* ``send_state`` — [보내기] 상태: ``sending`` 보내는 중(채널톡을 부르기 전에 조건부 쓰기로 커밋 — 두 번 누름 · 두 사람 동시엔
  하나만) · ``sent`` 보냄 · ``unknown`` 결과 모름(10초 끊김 · 5xx — 다시 보내지 않고 requestId 로 맞춘다) · ``failed`` 확실히
  못 보냄(다시 누를 수 있다). ``ck_cs_agent_turns_send_state`` 가 이 넷만 받는다(비면 아직 누르지 않음).
* ``send_started_at`` · ``sent_at`` — '보내는 중'을 커밋한 때 · 채널톡이 받은 글 시각(UTC). ``send_error`` — 마지막 막힘 ·
  실패 코드(글 없음).
* ``click_ms`` — 화면이 보인 때부터 [보내기]를 누를 때까지(밀리초) — '5초 안에 누름' 지표(GET 은 쓰지 않는다).
* ``waiting_since`` — 보낼 때 본 첫 미답 손님 글 시각(UTC) — '발송' 지표(첫 미답 손님 글 → 보냄).
* ``rewrite_state`` — '고칠 말'(AI 다시 쓰기) 요청: ``requested`` · ``working`` · ``done`` · ``failed``
  (``ck_cs_agent_turns_rewrite_state``). ``rewrite_note_masked`` — 가린 '고칠 말'(가림 검사를 넘은 것만) ·
  ``rewrite_requested_at`` · ``rewrite_count``(다시 쓴 수 — 상한을 코드가 본다, 처음 0).
* ``ix_cs_agent_turns_send_state`` · ``ix_cs_agent_turns_rewrite_state`` — 빠른 길이 5초마다 '결과 모름 · 고칠 말 요청'
  줄을 찾는 질의의 색인(거의 모든 줄이 비어 있다). 표가 작아(하루 수백 줄) 보통 ``CREATE INDEX`` 로 만든다.

데이터를 바꾸지 않는다(새 칸은 비고 ``rewrite_count`` 는 0). ``downgrade()`` 는 만든 역순으로 색인 → 제약 → 칸을 지운다
(보내기 · 고칠 말 기록은 사라진다 — 무손실 아님). DDL 은 models.py ``CsAgentTurn`` 과 같다(시험이 견준다). 상수 동결 원칙에
따라 models 를 import 하지 않는다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'csagent_04'
down_revision: Union[str, None] = 'csagent_03'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'cs_agent_turns'
SEND_STATES = ('sending', 'sent', 'unknown', 'failed')
REWRITE_STATES = ('requested', 'working', 'done', 'failed')
SEND_STATE_CHECK = 'ck_cs_agent_turns_send_state'
REWRITE_STATE_CHECK = 'ck_cs_agent_turns_rewrite_state'
#: (색인 이름, 칸) — 순서 = upgrade 순서.
INDEXES: tuple[tuple[str, str], ...] = (
    ('ix_cs_agent_turns_send_state', 'send_state'),
    ('ix_cs_agent_turns_rewrite_state', 'rewrite_state'),
)
#: 더하는 칸 — (이름, 꼴, NULL 허용, 서버 기본값). 순서 = upgrade 순서(downgrade 는 거꾸로).
COLUMNS: tuple[tuple[str, sa.types.TypeEngine, bool, object], ...] = (
    ('placed_at', sa.DateTime(), True, None),
    ('send_state', sa.String(16), True, None),
    ('send_started_at', sa.DateTime(), True, None),
    ('sent_at', sa.DateTime(), True, None),
    ('send_error', sa.String(48), True, None),
    ('click_ms', sa.Integer(), True, None),
    ('waiting_since', sa.DateTime(), True, None),
    ('rewrite_state', sa.String(16), True, None),
    ('rewrite_note_masked', sa.Text(), True, None),
    ('rewrite_requested_at', sa.DateTime(), True, None),
    ('rewrite_count', sa.Integer(), False, sa.text('0')),
)


def in_check(column: str, values: Sequence[str]) -> str:
    """값 목록 검사 제약 식 — ``column IN ('a','b')``(모델 ``CheckConstraint`` 와 같은 글자)."""
    return f"{column} IN (" + ",".join(f"'{value}'" for value in values) + ")"


def upgrade() -> None:
    """보내기 · 고칠 말 · 시간 칸과 검사 제약 · 색인을 더한다."""
    for name, type_, nullable, default in COLUMNS:
        op.add_column(TABLE, sa.Column(name, type_, nullable=nullable, server_default=default))
    op.create_check_constraint(SEND_STATE_CHECK, TABLE, in_check('send_state', SEND_STATES))
    op.create_check_constraint(REWRITE_STATE_CHECK, TABLE, in_check('rewrite_state', REWRITE_STATES))
    for name, column in INDEXES:
        op.create_index(name, TABLE, [column])


def downgrade() -> None:
    """만든 역순 — 색인 → 검사 제약 → 칸."""
    for name, _column in reversed(INDEXES):
        op.drop_index(name, table_name=TABLE)
    op.drop_constraint(REWRITE_STATE_CHECK, TABLE, type_='check')
    op.drop_constraint(SEND_STATE_CHECK, TABLE, type_='check')
    for name, _type, _nullable, _default in reversed(COLUMNS):
        op.drop_column(TABLE, name)
