"""CSAGENT-06: cs_agent_image_reads — 손님 그림 읽기(도면 · 예시) 결과 표(숫자 · 코드만)

Revision ID: csagent_06
Revises: notice_00
Create Date: 2026-11-02

설계 정본: 설계서 2026-10-27-cs-ai-agent 17.11 (e)(사장님 결정 D89 ~ D92 · D96). 번호 06 은 설계서가 정한 이름이다 —
17.6.1 의 ``csagent_05`` 가 뒤에 들어오면 그때 이 리비전 뒤로 잇는다(머리 하나 — 번호 차례와 적용 차례가 다를 수 있다).

* (상담, 글, 파일 차례) 하나에 한 줄(``uq_cs_agent_image_reads_file``). 미리 읽기 · 그 자리 읽기가 같은 그림을 두 번 읽지
  않게 선점 칸(``claim_owner`` · ``claim_expires_at``)을 둔다.
* ``state`` 는 여섯 값만(``ck_cs_agent_image_reads_state``). ``result`` · ``personal_codes`` · ``truth`` 는 JSON(PostgreSQL
  JSONB) — 숫자 · 고른 값만이다(글 칸 없음).
* **남기지 않는 것**: 그림 바이트 · 줄인 그림 · 파일 key · 주소 · 파일 이름 · 모델 글 — 칸이 없다.
* 색인: (state, created_at) — 미리 읽기 길이 2초마다 기다리는 줄을 찾는다 · read_at — 하루 장수 상한을 센다. 새 표라
  보통 ``CREATE INDEX`` 다.

``downgrade()`` 는 표를 지운다(그림 읽기 기록이 사라진다 — 무손실 아님). DDL 은 models.py ``CsAgentImageRead`` 와 같다
(시험이 견준다). 상수 동결 원칙에 따라 models 를 import 하지 않는다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'csagent_06'
down_revision: Union[str, None] = 'notice_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'cs_agent_image_reads'
STATES = ('pending', 'reading', 'done', 'skipped', 'failed', 'discarded')
STATE_CHECK = 'ck_cs_agent_image_reads_state'
UNIQUE = ('uq_cs_agent_image_reads_file', ('chat_id', 'message_id', 'file_index'))
#: (색인 이름, 칸들) — 순서 = upgrade 순서.
INDEXES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ('ix_cs_agent_image_reads_state_created', ('state', 'created_at')),
    ('ix_cs_agent_image_reads_read_at', ('read_at',)),
)
_JSON = sa.JSON().with_variant(postgresql.JSONB(), 'postgresql')
#: 칸 — (이름, 꼴, NULL 허용, 서버 기본값). 순서 = 표 칸 순서.
COLUMNS: tuple[tuple[str, sa.types.TypeEngine, bool, object], ...] = (
    ('brand', sa.String(8), False, None),
    ('chat_id', sa.String(64), False, None),
    ('message_id', sa.String(64), False, None),
    ('file_index', sa.Integer(), False, None),
    ('sha256', sa.String(64), True, None),
    ('state', sa.String(16), False, None),
    ('skip_code', sa.String(32), True, None),
    ('result', _JSON, True, None),
    ('confidence', sa.String(8), True, None),
    ('personal_codes', _JSON, True, None),
    ('model', sa.String(64), True, None),
    ('effort', sa.String(16), True, None),
    ('input_tokens', sa.Integer(), True, None),
    ('output_tokens', sa.Integer(), True, None),
    ('cost_usd', sa.Numeric(12, 6), True, None),
    ('latency_ms', sa.Integer(), True, None),
    ('attempts', sa.Integer(), False, sa.text('0')),
    ('claim_owner', sa.String(64), True, None),
    ('claim_expires_at', sa.DateTime(), True, None),
    ('turn_id', sa.Integer(), True, None),
    ('truth', _JSON, True, None),
    ('created_at', sa.DateTime(), False, sa.func.now()),
    ('read_at', sa.DateTime(), True, None),
)


def in_check(column: str, values: Sequence[str]) -> str:
    """값 목록 검사 제약 식 — ``column IN ('a','b')``(모델 ``CheckConstraint`` 와 같은 글자)."""
    return f"{column} IN (" + ",".join(f"'{value}'" for value in values) + ")"


def upgrade() -> None:
    """표 · 고유 · 검사 제약 → 색인."""
    op.create_table(
        TABLE,
        sa.Column('id', sa.Integer(), primary_key=True),
        *(sa.Column(name, type_, nullable=nullable, server_default=default)
          for name, type_, nullable, default in COLUMNS),
        sa.UniqueConstraint(*UNIQUE[1], name=UNIQUE[0]),
        sa.CheckConstraint(in_check('state', STATES), name=STATE_CHECK),
    )
    for name, columns in INDEXES:
        op.create_index(name, TABLE, list(columns))


def downgrade() -> None:
    """만든 역순 — 색인 → 표."""
    for name, _columns in reversed(INDEXES):
        op.drop_index(name, table_name=TABLE)
    op.drop_table(TABLE)
