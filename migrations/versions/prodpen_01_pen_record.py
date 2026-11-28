"""PRODPEN-01: 생산 도면 펜 기록 — 계정 칸 둘(users) + 기록 원본 표 production_drawing_notes

Revision ID: prodpen_01_pen_record
Revises: prodpart_03_basic_parts
Create Date: 2026-11-28

설계 정본: ``docs/specs/2026-11-28-production-pen-record_SPEC.md`` §3-1 · §4-1 · §4-3(사장님 2026-11-28 "승인 — 만들기 시작").

upgrade:

1. ``users.production_pen_write`` · ``users.production_pen_first`` Boolean NULL 허용 — 반장 칸(``prodlead_01``)과 같은 꼴.
   기본값 · 색인 · 채우기 없음(PG 는 표를 다시 쓰지 않는다 — 메타만 바뀜, 잠금 짧음). NULL · 거짓 = 꺼짐.
2. ``production_drawing_notes`` 표 — 주문(FK CASCADE) × 도면 key 로 한 줄. 기록 원본(``objects`` JSON · PG 는 JSONB) ·
   좌표 기준 크기 · 버전(같이 고칠 때 견줌) · 지금 합친 그림 첨부(FK SET NULL) · 쓴 사람(FK SET NULL) · 이름 스냅샷 · 때.
   UNIQUE ``(order_id, drawing_key)`` — 앞머리가 ``order_id`` 라 ``order_id IN (…)`` 읽기 색인을 겸한다(표시 표와 같은 까닭).
   빈 표라 CONCURRENTLY · advisory lock 이 필요 없다.

스위치(``FOMS_PRODUCTION_PEN_RECORD``)와 상관없이 올라간다 — 옛 코드는 칸 · 표를 모르고 그대로 돈다(마이그레이션 먼저 → 코드).
downgrade 는 반대 순서(표 → 칸 둘)다. 그 사이에 쌓인 기록 원본과 계정 칸 값은 사라진다(합친 그림은 주문 첨부에 남는다).

마이그레이션 상수 동결 원칙에 따라 ``models`` 를 import 하지 않는다(표 · 칸 · 제약 이름 리터럴). DDL 은 models.py
``ProductionDrawingNote`` · ``User`` 와 같다 — SQLite 시험 ``tests/domains/test_production_pen_record_base.py``,
PG 왕복 · 유일 제약 ``tests/postgres/test_production_pen_record_pg.py`` · ``tests/postgres/test_migration_chain.py``.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'prodpen_01_pen_record'
down_revision: Union[str, None] = 'prodpart_03_basic_parts'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

USERS = 'users'
USER_COLUMNS = ('production_pen_write', 'production_pen_first')
TABLE = 'production_drawing_notes'
UNIQUE = 'uq_production_drawing_notes_order_key'


def _user_fk_column(name: str) -> sa.Column:
    """사용자를 가리키는 NULL 칸(사용자가 지워지면 NULL — 이름 스냅샷은 남는다)."""
    return sa.Column(name, sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)


def upgrade() -> None:
    """① 계정 칸 둘 → ② 기록 원본 표 + UNIQUE."""
    for column in USER_COLUMNS:
        op.add_column(USERS, sa.Column(column, sa.Boolean(), nullable=True))

    op.create_table(
        TABLE,
        sa.Column('id', sa.BigInteger().with_variant(sa.Integer, 'sqlite'), primary_key=True),
        sa.Column('order_id', sa.Integer(), sa.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False),
        sa.Column('drawing_key', sa.String(length=500), nullable=False),
        sa.Column('sheet_id', sa.String(length=64), nullable=True),
        sa.Column('drawing_no', sa.Integer(), nullable=True),
        sa.Column('objects', sa.JSON(none_as_null=True).with_variant(postgresql.JSONB(none_as_null=True), 'postgresql'),
                  nullable=False),
        sa.Column('base_w', sa.Integer(), nullable=False),
        sa.Column('base_h', sa.Integer(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('attachment_id', sa.Integer(), sa.ForeignKey('order_attachments.id', ondelete='SET NULL'), nullable=True),
        _user_fk_column('updated_by_user_id'),
        sa.Column('updated_by_name', sa.String(length=120), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        _user_fk_column('created_by_user_id'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('order_id', 'drawing_key', name=UNIQUE),
    )


def downgrade() -> None:
    """반대 순서: 표 지우기 → 계정 칸 둘 지우기."""
    op.drop_table(TABLE)
    for column in reversed(USER_COLUMNS):
        op.drop_column(USERS, column)
