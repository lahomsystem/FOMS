"""BRAIN-00: HAUD master brain 표 다섯 — 항목 · 링크(쌓기만 하는 판 행) · 제안 · 판 · 직원 챗봇 기록

Revision ID: brain_00
Revises: notice_01
Create Date: 2026-11-02

설계 정본: 설계서 2026-11-02-haud-master-brain 4절 · 5절 · 6절 · 7.5 끝 '저장 꼴'(사장님 결정 D97 '처음부터 항목별 표') ·
10.3. **빈 표 더하기만** 한다 — 데이터를 옮기지 않는다(옮기기는 ``scripts/maintenance/brain_import_knowledge.py``).

* ``brain_objects`` · ``brain_links`` — **쌓기만 하는 판 행**. 고침 = 새 판 줄 + 앞 줄 ``superseded_at``. '지금 판은 하나'는
  부분 유일 색인(``superseded_at IS NULL``)이 막는다. 링크 양 끝 + 종류 색인, (브랜드 · 유형 · 키) 유일(지금 줄),
  이름 · 글 pg_trgm(PostgreSQL 전용 — 지금 줄만).
* ``brain_changes`` — 제안(칸별 전 → 후 · 기준 판 · 까닭 · 근거 · 등급 · 관문 결과 · 상태 · 거절 까닭 · 결정한 사람).
* ``brain_releases`` — 하루 판(번호 · 층 · 개수 · 차이 요약 · 누가 · 언제). 판 0 = 지식 문서에서 옮겨 온 판.
* ``brain_questions`` — 직원 챗봇 기록(10.3) 표만. 가린 글만 · 묻는 사람 번호(ADMIN 만 봄).
* 사람 번호 칸(``human_approver_id`` · ``decided_by`` · ``asker_id`` · ``created_by``)은 FK 가 없다 — 계정을 지워도 지식
  이력이 같이 지워지지 않게(설계서 17.5 '알려진 함정'). 손님 · 직원 개인정보 칸은 없다.

``downgrade()`` 는 표를 지운다(brain 기록이 사라진다 — 무손실 아님. 지식 문서는 그대로라 상담 두뇌에는 영향 없음).
DDL 은 ``foms/persistence/brain/models.py`` 와 같다(시험이 견준다). 상수 동결 원칙에 따라 models 를 import 하지 않는다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'brain_00'
down_revision: Union[str, None] = 'notice_01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_JSON = sa.JSON().with_variant(postgresql.JSONB(), 'postgresql')
CURRENT = 'superseded_at IS NULL'
OBJECT_STATUSES = ('draft', 'active', 'retired')
CONFIDENCES = ('confirmed', 'evidenced', 'observed')
LAYERS = ('common', 'cs', 'drawing', 'production')
CHANGE_OPS = ('create', 'update', 'retire', 'delete', 'link_add', 'link_remove')
CHANGE_STATUSES = ('open', 'applied', 'rejected', 'expired')
FEEDBACKS = ('helpful', 'not_helpful', 'wrong')

#: 표마다 칸 — (이름, 꼴, NULL 허용, 서버 기본값). 순서 = 표 칸 순서(``id`` 다음).
_VERSION_COMMON: tuple[tuple[str, sa.types.TypeEngine, bool, object], ...] = (
    ('confidence', sa.String(16), False, None),
    ('valid_from', sa.Date(), True, None),
    ('valid_to', sa.Date(), True, None),
    ('recorded_at', sa.DateTime(), False, sa.func.now()),
    ('superseded_at', sa.DateTime(), True, None),
    ('evidence_kind', sa.String(16), True, None),
    ('evidence_ref', sa.String(200), True, None),
    ('created_by', sa.String(64), False, None),
    ('human_approver_id', sa.Integer(), True, None),
    ('change_id', sa.Integer(), True, None),
    ('release_no', sa.Integer(), True, None),
)
COLUMNS: dict[str, tuple[tuple[str, sa.types.TypeEngine, bool, object], ...]] = {
    'brain_objects': (
        ('item_key', sa.String(120), False, None),
        ('version', sa.Integer(), False, None),
        ('brand', sa.String(8), False, None),
        ('layer', sa.String(16), False, None),
        ('item_type', sa.String(32), False, None),
        ('name', sa.String(200), False, None),
        ('text', sa.Text(), True, None),
        ('status', sa.String(16), False, None),
        ('risk_grade', sa.String(8), True, None),
        ('checked_at', sa.Date(), True, None),
        ('stale_after', sa.Date(), True, None),
        ('evidence_count', sa.Integer(), False, sa.text('0')),
        ('visibility', sa.String(32), False, None),
        ('copies', _JSON, True, None),
        ('usage_count', sa.Integer(), False, sa.text('0')),
        ('payload', _JSON, True, None),
        *_VERSION_COMMON,
    ),
    'brain_links': (
        ('kind', sa.String(16), False, None),
        ('from_key', sa.String(120), False, None),
        ('to_key', sa.String(120), False, None),
        ('version', sa.Integer(), False, None),
        ('payload', _JSON, True, None),
        *_VERSION_COMMON,
    ),
    'brain_changes': (
        ('op', sa.String(16), False, None),
        ('item_key', sa.String(120), True, None),
        ('link_kind', sa.String(16), True, None),
        ('link_from', sa.String(120), True, None),
        ('link_to', sa.String(120), True, None),
        ('brand', sa.String(8), True, None),
        ('layer', sa.String(16), True, None),
        ('item_type', sa.String(32), True, None),
        ('base_version', sa.Integer(), True, None),
        ('fields', _JSON, True, None),
        ('reason', sa.Text(), True, None),
        ('evidence', _JSON, True, None),
        ('grade', sa.String(8), False, None),
        ('gates', _JSON, True, None),
        ('status', sa.String(16), False, None),
        ('reject_code', sa.String(24), True, None),
        ('rollback_of_version', sa.Integer(), True, None),
        ('proposed_by', sa.String(64), False, None),
        ('decided_by', sa.Integer(), True, None),
        ('result_version', sa.Integer(), True, None),
        ('release_no', sa.Integer(), True, None),
        ('created_at', sa.DateTime(), False, sa.func.now()),
        ('decided_at', sa.DateTime(), True, None),
    ),
    'brain_releases': (
        ('number', sa.Integer(), False, None),
        ('layer', sa.String(16), False, None),
        ('day', sa.Date(), False, None),
        ('counts', _JSON, True, None),
        ('diff', _JSON, True, None),
        ('created_by', sa.Integer(), True, None),
        ('created_at', sa.DateTime(), False, sa.func.now()),
        ('updated_at', sa.DateTime(), False, sa.func.now()),
    ),
    'brain_questions': (
        ('asked_at', sa.DateTime(), False, sa.func.now()),
        ('asker_id', sa.Integer(), True, None),
        ('masked_question', sa.Text(), False, None),
        ('answer', sa.Text(), True, None),
        ('evidence_keys', _JSON, True, None),
        ('unknown', sa.Boolean(), False, sa.text('false')),
        ('confidence', sa.String(16), True, None),
        ('ask_team', sa.String(16), True, None),
        ('layer', sa.String(16), True, None),
        ('feedback', sa.String(16), True, None),
        ('feedback_note', sa.Text(), True, None),
        ('model', sa.String(64), True, None),
    ),
}
#: 표마다 검사 제약 — (이름, 칸, 값들).
CHECKS: dict[str, tuple[tuple[str, str, tuple[str, ...]], ...]] = {
    'brain_objects': (
        ('ck_brain_objects_status', 'status', OBJECT_STATUSES),
        ('ck_brain_objects_confidence', 'confidence', CONFIDENCES),
        ('ck_brain_objects_layer', 'layer', LAYERS),
    ),
    'brain_links': (('ck_brain_links_confidence', 'confidence', CONFIDENCES),),
    'brain_changes': (
        ('ck_brain_changes_op', 'op', CHANGE_OPS),
        ('ck_brain_changes_status', 'status', CHANGE_STATUSES),
    ),
    'brain_releases': (('ck_brain_releases_layer', 'layer', LAYERS),),
    'brain_questions': (('ck_brain_questions_feedback', 'feedback', FEEDBACKS),),
}
#: 표마다 색인 — (이름, 칸들, 유일, 지금 줄만). 순서 = upgrade 순서.
INDEXES: dict[str, tuple[tuple[str, tuple[str, ...], bool, bool], ...]] = {
    'brain_objects': (
        ('uq_brain_objects_key_version', ('item_key', 'version'), True, False),
        ('uq_brain_objects_current_key', ('item_key',), True, True),
        ('uq_brain_objects_current_brand_type_key', ('brand', 'item_type', 'item_key'), True, True),
        ('ix_brain_objects_layer_type', ('layer', 'item_type'), False, True),
    ),
    'brain_links': (
        ('uq_brain_links_identity_version', ('kind', 'from_key', 'to_key', 'version'), True, False),
        ('uq_brain_links_current', ('kind', 'from_key', 'to_key'), True, True),
        ('ix_brain_links_from_kind', ('from_key', 'kind'), False, True),
        ('ix_brain_links_to_kind', ('to_key', 'kind'), False, True),
    ),
    'brain_changes': (
        ('ix_brain_changes_status_created', ('status', 'created_at'), False, False),
        ('ix_brain_changes_item_key', ('item_key', 'status'), False, False),
    ),
    'brain_releases': (
        ('uq_brain_releases_number_layer', ('number', 'layer'), True, False),
        ('ix_brain_releases_day', ('day',), False, False),
    ),
    'brain_questions': (('ix_brain_questions_asked_at', ('asked_at',), False, False),),
}
#: 이름 · 글 비슷함 찾기(pg_trgm) — PostgreSQL 전용 · 지금 줄만. (색인 이름, 칸).
TRGM_INDEXES: tuple[tuple[str, str], ...] = (
    ('ix_brain_objects_name_trgm', 'name'),
    ('ix_brain_objects_text_trgm', 'text'),
)


def in_check(column: str, values: Sequence[str]) -> str:
    """값 목록 검사 제약 식 — ``column IN ('a','b')``(모델 ``CheckConstraint`` 와 같은 글자)."""
    return f"{column} IN (" + ",".join(f"'{value}'" for value in values) + ")"


def trgm_sql(name: str, column: str) -> str:
    """지금 줄만 담는 gin_trgm_ops 색인 DDL."""
    return f"CREATE INDEX IF NOT EXISTS {name} ON brain_objects USING gin ({column} gin_trgm_ops) WHERE {CURRENT}"


def _create(table: str) -> None:
    """표 하나 — 칸 · 검사 제약 → 색인."""
    op.create_table(
        table,
        sa.Column('id', sa.Integer(), primary_key=True),
        *(sa.Column(name, type_, nullable=nullable, server_default=default)
          for name, type_, nullable, default in COLUMNS[table]),
        *(sa.CheckConstraint(in_check(column, values), name=name) for name, column, values in CHECKS[table]),
    )
    for name, columns, unique, current_only in INDEXES[table]:
        where = sa.text(CURRENT) if current_only else None
        op.create_index(name, table, list(columns), unique=unique, postgresql_where=where, sqlite_where=where)


def upgrade() -> None:
    """표 다섯 → (PostgreSQL 이면) 이름 · 글 trgm 색인."""
    for table in COLUMNS:
        _create(table)
    if op.get_bind().dialect.name == 'postgresql':
        op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        for name, column in TRGM_INDEXES:
            op.execute(sa.text(trgm_sql(name, column)))


def downgrade() -> None:
    """만든 역순 — trgm 색인 → 표(색인 · 제약은 표와 같이). pg_trgm 확장은 다른 색인이 써서 지우지 않는다."""
    if op.get_bind().dialect.name == 'postgresql':
        for name, _column in reversed(TRGM_INDEXES):
            op.execute(sa.text(f"DROP INDEX IF EXISTS {name}"))
    for table in reversed(list(COLUMNS)):
        for name, _columns, _unique, _current in reversed(INDEXES[table]):
            op.drop_index(name, table_name=table)
        op.drop_table(table)
