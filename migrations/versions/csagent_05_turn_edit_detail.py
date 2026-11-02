"""CSAGENT-05: 고친 까닭 자세히 · 사진 — cs_agent_turns 칸 셋 + cs_agent_turn_photos 표

Revision ID: csagent_05
Revises: csagent_06
Create Date: 2026-11-02

설계 정본: 설계서 2026-10-27-cs-ai-agent 17.6.1 (b)(사장님 결정 D94). 번호 05 는 설계서가 정한 이름이다 — 그림 읽기
``csagent_06`` 이 먼저 들어가 그 뒤로 잇는다(번호 차례와 적용 차례가 다르다, 머리 하나).

* ``cs_agent_turns``: ``edit_detail_masked``(가린 자세한 이유 — 가림 검사 0 일 때만) · ``edit_detail_by``(적은 직원 번호, FK
  없음 — ``sent_by_user_id`` 와 같은 꼴) · ``edit_detail_at``(UTC). 비어 있는 칸만 더해 옛 줄은 그대로다.
* ``cs_agent_turn_photos``: 사진 하나 = 줄 하나. ``turn_id`` 는 차례 줄 FK(지우기 막음 — 차례 줄을 지우는 단계가 생기면 저장소
  사진을 먼저 지워야 한다). (turn_id, seq) 고유, ``seq`` 는 1~10(살아 있는 사진 5장 상한은 코드가 본다 — 직원이 지운 줄은
  ``purged_at`` 만 남아 번호를 차지한다). ``desc_state`` 다섯 값만. 바이트 · 주소 · 파일 이름 칸은 없다 — ``storage_key`` 는
  ``cs-agent/edit-photos/<차례>/<uuid>.<확장자>`` 꼴(이름 · 상담 id 없음)이고 원본을 지우면 NULL.
* 색인: (desc_state, created_at) — 15분 바퀴가 설명 뽑을 사진을 찾는다 · created_at — 밤 단계가 90일 지난 원본을 찾는다.
  새 표라 보통 ``CREATE INDEX`` 다.

``downgrade()`` 는 표와 칸을 지운다(자세한 이유 · 사진 줄이 사라진다 — 무손실 아님, 저장소 파일은 남는다). DDL 은 models.py
``CsAgentTurn`` · ``CsAgentTurnPhoto`` 와 같다(시험이 견준다). 상수 동결 원칙에 따라 models 를 import 하지 않는다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'csagent_05'
down_revision: Union[str, None] = 'csagent_06'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TURNS = 'cs_agent_turns'
TABLE = 'cs_agent_turn_photos'
#: 차례 표에 더하는 칸 — (이름, 꼴, NULL 허용, 서버 기본값).
TURN_COLUMNS: tuple[tuple[str, sa.types.TypeEngine, bool, object], ...] = (
    ('edit_detail_masked', sa.Text(), True, None),
    ('edit_detail_by', sa.Integer(), True, None),
    ('edit_detail_at', sa.DateTime(), True, None),
)
DESC_STATES = ('pending', 'done', 'leak', 'skipped', 'failed')
DESC_STATE_CHECK = 'ck_cs_agent_turn_photos_desc_state'
SEQ_CHECK = 'ck_cs_agent_turn_photos_seq'
SEQ_MAX = 10
UNIQUE = ('uq_cs_agent_turn_photos_turn_seq', ('turn_id', 'seq'))
#: (색인 이름, 칸들) — 순서 = upgrade 순서.
INDEXES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ('ix_cs_agent_turn_photos_desc_state_created', ('desc_state', 'created_at')),
    ('ix_cs_agent_turn_photos_created', ('created_at',)),
)
#: 사진 표 칸(id · turn_id 뒤) — (이름, 꼴, NULL 허용, 서버 기본값). 순서 = 표 칸 순서.
COLUMNS: tuple[tuple[str, sa.types.TypeEngine, bool, object], ...] = (
    ('seq', sa.Integer(), False, None),
    ('storage_key', sa.String(200), True, None),
    ('content_type', sa.String(16), False, None),
    ('bytes', sa.Integer(), False, None),
    ('width', sa.Integer(), False, None),
    ('height', sa.Integer(), False, None),
    ('sha256', sa.String(64), False, None),
    ('no_personal', sa.Boolean(), False, sa.text('false')),
    ('desc_state', sa.String(8), False, None),
    ('desc_masked', sa.Text(), True, None),
    ('desc_at', sa.DateTime(), True, None),
    ('uploaded_by', sa.Integer(), False, None),
    ('created_at', sa.DateTime(), False, sa.func.now()),
    ('purged_at', sa.DateTime(), True, None),
)


def in_check(column: str, values: Sequence[str]) -> str:
    """값 목록 검사 제약 식 — ``column IN ('a','b')``(모델 ``CheckConstraint`` 와 같은 글자)."""
    return f"{column} IN (" + ",".join(f"'{value}'" for value in values) + ")"


def seq_check() -> str:
    """사진 차례 번호 검사 식(모델과 같은 글자)."""
    return f"seq >= 1 AND seq <= {SEQ_MAX}"


def upgrade() -> None:
    """차례 표 칸 → 사진 표(고유 · 검사 제약 · FK) → 색인."""
    for name, type_, nullable, default in TURN_COLUMNS:
        op.add_column(TURNS, sa.Column(name, type_, nullable=nullable, server_default=default))
    op.create_table(
        TABLE,
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('turn_id', sa.Integer(), sa.ForeignKey(f'{TURNS}.id'), nullable=False),
        *(sa.Column(name, type_, nullable=nullable, server_default=default)
          for name, type_, nullable, default in COLUMNS),
        sa.UniqueConstraint(*UNIQUE[1], name=UNIQUE[0]),
        sa.CheckConstraint(in_check('desc_state', DESC_STATES), name=DESC_STATE_CHECK),
        sa.CheckConstraint(seq_check(), name=SEQ_CHECK),
    )
    for name, columns in INDEXES:
        op.create_index(name, TABLE, list(columns))


def downgrade() -> None:
    """만든 역순 — 색인 → 사진 표 → 차례 표 칸."""
    for name, _columns in reversed(INDEXES):
        op.drop_index(name, table_name=TABLE)
    op.drop_table(TABLE)
    for name, _type, _nullable, _default in reversed(TURN_COLUMNS):
        op.drop_column(TURNS, name)
