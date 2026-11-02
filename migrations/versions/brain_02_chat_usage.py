"""BRAIN-02: 회사 지식 챗봇 — 쓰인 횟수(따로 세기) · 틀림 신고(엇갈림 후보) 표 둘 + 의미 찾기 벡터 표

Revision ID: brain_02
Revises: brain_01
Create Date: 2026-11-02

설계 정본: 설계서 2026-11-02-haud-master-brain 10절(직원 챗봇 — 기록 · 빈 지식 · 틀림 신고) · 7.7 · 사장님 결정 D105
('``usage_count`` 는 판 행이 아니라 따로 센다').

* ``brain_usage`` — (항목 키, 읽은 쪽) 한 줄에 쓰인 수 · 마지막 쓰인 때. 읽은 쪽은 ``chatbot`` · ``cs_brain``. 셀 때마다 판
  줄을 새로 만들지 않는다(쌓기만 하는 판 행 규칙 그대로).
* ``brain_wrong_reports`` — 챗봇 답에 '틀림'을 누르면 그 답의 근거 항목마다 한 줄(가린 고칠 말). 같은 항목에 서로 다른 사람
  둘 이상이면 승인자에게 제안이 간다(``change_id``). 사람 번호 칸은 FK 가 없다.

* ``brain_embeddings`` — 의미 찾기 벡터(사장님 D114 · Voyage AI ``voyage-4`` 1024 차원). **판 행과 따로 · 근원 종류별 한 표**
  (``brain_item`` · ``chatbot_question`` · ``cs_case``), (근원 종류, 근원 키, 모델)마다 한 줄(근원 판 · 글 지문). PostgreSQL ``vector(1024)`` 형 — **pgvector 확장을 쓸 수 있을 때만 만든다**(운영 · 스테이징 0.8.2
  있음). 확장이 없는 PostgreSQL(CI PG 레인 이미지 postgres:17) · SQLite 에서는 이 표만 건너뛴다 — 의미 찾기는 처음부터 꺼져
  있고(설정 ``brain_embeddings_enabled``) 표가 없으면 앱이 글자 찾기로만 돈다(조용히 물러남). 색인 없음(정확 찾기 — HNSW 는
  pgvector 0.8.4 이상 · 수만 줄에서). 이 표는 ORM ``Base`` 밖(``foms/persistence/brain/vectors.py``)이다.

**빈 표 더하기만** 한다(데이터를 바꾸지 않는다). ``downgrade()`` 는 표를 지운다(쓰인 수 · 틀림 신고 · 벡터가 사라진다 — 지식 항목 ·
제안 · 질문 기록은 그대로, 벡터는 백필 스크립트로 다시 만든다). DDL 은 ``foms/persistence/brain/models.py`` ·
``vectors.py`` 와 같다(시험이 견준다). models 를 import 하지 않는다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'brain_02'
down_revision: Union[str, None] = 'brain_01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

READERS = ('chatbot', 'cs_brain')

#: 표마다 칸 — (이름, 꼴, NULL 허용, 서버 기본값). 순서 = 표 칸 순서(``id`` 다음).
COLUMNS: dict[str, tuple[tuple[str, sa.types.TypeEngine, bool, object], ...]] = {
    'brain_usage': (
        ('item_key', sa.String(120), False, None),
        ('reader', sa.String(16), False, None),
        ('count', sa.Integer(), False, sa.text('0')),
        ('last_used_at', sa.DateTime(), True, None),
    ),
    'brain_wrong_reports': (
        ('item_key', sa.String(120), False, None),
        ('question_id', sa.Integer(), False, None),
        ('reporter_id', sa.Integer(), True, None),
        ('note', sa.Text(), True, None),
        ('created_at', sa.DateTime(), False, sa.func.now()),
        ('change_id', sa.Integer(), True, None),
    ),
}
#: 검사 제약 — (이름, 칸, 값들).
CHECKS: dict[str, tuple[tuple[str, str, tuple[str, ...]], ...]] = {
    'brain_usage': (('ck_brain_usage_reader', 'reader', READERS),),
    'brain_wrong_reports': (),
}
#: 색인 — (이름, 칸들, 유일).
INDEXES: dict[str, tuple[tuple[str, tuple[str, ...], bool], ...]] = {
    'brain_usage': (('uq_brain_usage_key_reader', ('item_key', 'reader'), True),),
    'brain_wrong_reports': (
        ('uq_brain_wrong_reports_question_key', ('question_id', 'item_key'), True),
        ('ix_brain_wrong_reports_key_created', ('item_key', 'created_at'), False),
    ),
}


def in_check(column: str, values: Sequence[str]) -> str:
    """값 목록 검사 제약 식 — ``column IN ('a','b')``(모델 ``CheckConstraint`` 와 같은 글자)."""
    return f"{column} IN (" + ",".join(f"'{value}'" for value in values) + ")"


EMBED_TABLE = 'brain_embeddings'
EMBED_DIM = 1024
EMBED_SOURCES = ('brain_item', 'chatbot_question', 'cs_case')
EMBED_DDL = (
    f"CREATE TABLE IF NOT EXISTS {EMBED_TABLE} (id SERIAL PRIMARY KEY, source_kind VARCHAR(24) NOT NULL, "
    "source_key VARCHAR(120) NOT NULL, source_version INTEGER, model VARCHAR(40) NOT NULL, dimension INTEGER NOT NULL, "
    f"embedding vector({EMBED_DIM}) NOT NULL, text_hash VARCHAR(64) NOT NULL, "
    "created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(), "
    f"CONSTRAINT ck_brain_embeddings_source_kind CHECK ({in_check('source_kind', EMBED_SOURCES)}))",
    f"CREATE UNIQUE INDEX IF NOT EXISTS uq_brain_embeddings_source_model ON {EMBED_TABLE} (source_kind, source_key, model)",
)


def _vector_available() -> bool:
    """PostgreSQL 이고 pgvector 확장을 쓸 수 있나(이미 켜짐 또는 설치 가능)."""
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        return False
    row = bind.execute(sa.text("SELECT count(*) FROM pg_available_extensions WHERE name = 'vector'")).fetchone()
    return bool(row and row[0])


def upgrade() -> None:
    """표 둘 — 칸 · 검사 제약 → 색인. 그다음 pgvector 가 있으면 벡터 표."""
    for table, columns in COLUMNS.items():
        op.create_table(
            table,
            sa.Column('id', sa.Integer(), primary_key=True),
            *(sa.Column(name, type_, nullable=nullable, server_default=default)
              for name, type_, nullable, default in columns),
            *(sa.CheckConstraint(in_check(column, values), name=name) for name, column, values in CHECKS[table]),
        )
        for name, cols, unique in INDEXES[table]:
            op.create_index(name, table, list(cols), unique=unique)
    if _vector_available():
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        for statement in EMBED_DDL:
            op.execute(statement)
    else:
        print("[SKIP] brain_embeddings: pgvector 를 쓸 수 없어 벡터 표를 만들지 않는다(의미 찾기는 꺼진 채 — 글자 찾기만)")


def downgrade() -> None:
    """벡터 표(있으면) → 표 둘을 지운다(거꾸로). 확장은 다른 표(designer)도 쓰니 지우지 않는다."""
    if op.get_bind().dialect.name == 'postgresql':
        op.execute(f"DROP TABLE IF EXISTS {EMBED_TABLE}")
    for table in reversed(tuple(COLUMNS)):
        for name, _cols, _unique in reversed(INDEXES[table]):
            op.drop_index(name, table_name=table)
        op.drop_table(table)
