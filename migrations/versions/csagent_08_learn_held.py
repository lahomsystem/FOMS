"""CSAGENT-08: cs_agent_learn_held — 넘긴 상담 배우기 '기다리는 말' 표 + 의미 찾기 근원 종류 하나 더

Revision ID: csagent_08
Revises: brain_03
Create Date: 2026-11-23

설계 정본: ``docs/specs/2026-11-23-brain-learning-upgrade_SPEC.md`` 3절(사장님 11-23 '여러 번 나온 것만 바로 반영').

* ``cs_agent_learn_held`` — 밤 배우기가 한 상담에서만 들은 말 한 줄. 브랜드 · 이름 · 글(가림 관문을 지난 일반화한 글만) · 근거
  상담 번호들 · 근거 차례 번호들 · 올릴 때 합칠 근거 글 · 처음 · 마지막 본 때 · 상태(``waiting`` · ``promoted`` · ``dropped``).
  사람 · 차례 번호 칸에 FK 가 없다(차례 줄을 지워도 기록이 남는다 — 다른 cs_agent 표와 같다).
* ``brain_embeddings`` 근원 종류 검사 제약에 ``cs_learn_held`` 를 더한다(기다리는 말의 뜻 찾기 벡터 — 근원 키 = 그 줄 번호).
  그 표는 pgvector 가 있는 PostgreSQL 에만 있다(``brain_02``) — **표가 있을 때만** 제약을 바꾼다(없으면 건너뜀 · SQLite 시험은
  ``vector_metadata`` 가 새 목록으로 만든다). 수천 줄짜리 표라 제약 검사는 바로 끝난다.

**빈 표 하나를 더하고 제약 글 하나를 넓히기만** 한다(데이터를 바꾸지 않는다 · 빈 표라 CONCURRENTLY · advisory lock 이 필요
없다). ``downgrade()`` 는 기다리는 말 벡터 줄을 지우고 제약을 예전 셋으로 되돌린 뒤 표를 지운다(그 사이 모은 기다리는 말이
사라진다 — 지식 · 제안은 그대로). DDL 은 models.py ``CsAgentLearnHeld`` · ``foms/persistence/brain/vectors.py`` 와 같다(시험이
견준다). 상수 동결 원칙에 따라 models 를 import 하지 않는다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'csagent_08'
down_revision: Union[str, None] = 'brain_03'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'cs_agent_learn_held'
STATES = ('waiting', 'promoted', 'dropped')
STATE_CHECK = 'ck_cs_agent_learn_held_state'
#: (색인 이름, 칸들) — 순서 = upgrade 순서.
INDEXES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ('ix_cs_agent_learn_held_state_last_seen', ('state', 'last_seen')),
    ('ix_cs_agent_learn_held_brand_state', ('brand', 'state')),
)
_JSON = sa.JSON().with_variant(postgresql.JSONB(), 'postgresql')
#: 칸 — (이름, 꼴, NULL 허용, 서버 기본값). 순서 = 표 칸 순서(``id`` 다음).
COLUMNS: tuple[tuple[str, sa.types.TypeEngine, bool, object], ...] = (
    ('brand', sa.String(8), False, None),
    ('title', sa.String(100), False, None),
    ('text', sa.Text(), False, None),
    ('chat_ids', _JSON, False, None),
    ('turn_ids', _JSON, False, None),
    ('evidence', _JSON, False, None),
    ('state', sa.String(16), False, None),
    ('first_seen', sa.DateTime(), False, None),
    ('last_seen', sa.DateTime(), False, None),
)

EMBED_TABLE = 'brain_embeddings'
EMBED_CHECK = 'ck_brain_embeddings_source_kind'
#: 근원 종류 — 예전 셋(``brain_02``)과 이 리비전 뒤 넷(작성 시점 스냅샷 — vectors.py 와 같은 글자인지는 시험이 본다).
EMBED_SOURCES_BEFORE = ('brain_item', 'chatbot_question', 'cs_case')
EMBED_SOURCES = (*EMBED_SOURCES_BEFORE, 'cs_learn_held')


def in_check(column: str, values: Sequence[str]) -> str:
    """값 목록 검사 제약 식 — ``column IN ('a','b')``(모델 ``CheckConstraint`` 와 같은 글자)."""
    return f"{column} IN (" + ",".join(f"'{value}'" for value in values) + ")"


def _embed_table_here() -> bool:
    """의미 찾기 벡터 표가 있는 PostgreSQL 인가(pgvector 가 없으면 ``brain_02`` 가 표를 만들지 않았다)."""
    bind = op.get_bind()
    return bind.dialect.name == 'postgresql' and sa.inspect(bind).has_table(EMBED_TABLE)


def _set_embed_check(values: Sequence[str]) -> None:
    """벡터 표 근원 종류 검사 제약을 그 목록으로 바꾼다(지우고 다시 건다)."""
    op.execute(f"ALTER TABLE {EMBED_TABLE} DROP CONSTRAINT IF EXISTS {EMBED_CHECK}")
    op.execute(f"ALTER TABLE {EMBED_TABLE} ADD CONSTRAINT {EMBED_CHECK} CHECK ({in_check('source_kind', values)})")


def upgrade() -> None:
    """표 · 검사 제약 → 색인 → (벡터 표가 있으면) 근원 종류 넷."""
    op.create_table(
        TABLE,
        sa.Column('id', sa.Integer(), primary_key=True),
        *(sa.Column(name, type_, nullable=nullable, server_default=default)
          for name, type_, nullable, default in COLUMNS),
        sa.CheckConstraint(in_check('state', STATES), name=STATE_CHECK),
    )
    for name, columns in INDEXES:
        op.create_index(name, TABLE, list(columns))
    if _embed_table_here():
        _set_embed_check(EMBED_SOURCES)
    else:
        print("[SKIP] brain_embeddings: 벡터 표가 없어 근원 종류 제약을 바꾸지 않는다(의미 찾기는 꺼진 채 — 글자 찾기만)")


def downgrade() -> None:
    """만든 역순 — (벡터 표가 있으면) 기다리는 말 벡터 줄 지우기 · 근원 종류 셋 → 색인 → 표."""
    if _embed_table_here():
        op.execute(sa.text(f"DELETE FROM {EMBED_TABLE} WHERE source_kind = :kind").bindparams(kind=EMBED_SOURCES[-1]))
        _set_embed_check(EMBED_SOURCES_BEFORE)
    for name, _columns in reversed(INDEXES):
        op.drop_index(name, table_name=TABLE)
    op.drop_table(TABLE)
