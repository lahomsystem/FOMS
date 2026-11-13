"""PRODPART-00: 생산 파트 나누기 — 계정 파트 칸 + 도면 장 × 파트 표시 표

Revision ID: prodpart_00
Revises: chat_drop_01
Create Date: 2026-11-13

설계 정본: ``docs/specs/2026-11-09-tablet-production-ui_SPEC.md`` §15.3(D47~D57, 사용자 승인 "이대로 만들기").

upgrade:

1. ``users.production_part`` String(16) NULL + CHECK ``ck_users_production_part``(NULL 또는 네 파트 key).
   기본값 없는 NULL 칸이라 PG 는 표를 다시 쓰지 않는다(메타만 바뀜). 기존 행은 전부 NULL 이라 CHECK 검사가
   바로 끝난다(사용자 표는 작다).
2. ``production_part_marks`` 표 — 주문(FK CASCADE) · 도면 장 key · 시트 신원 · 파트 · 상태 · 맡은/끝낸/고친 사람
   (FK SET NULL) · 이름 스냅샷 · 때. UNIQUE ``(order_id, drawing_key, part)`` + CHECK 셋(파트 · 상태 ·
   '기본'은 재단만). 빈 표라 CONCURRENTLY · advisory lock 이 필요 없다.

데이터 이행은 없다. ``downgrade()`` 는 반대 순서(표 지우기 → 사용자 CHECK · 칸 지우기)다 — 그 사이에 쌓인
파트 표시와 계정 파트 값은 사라진다.

DDL 은 models.py ``ProductionPartMark`` · ``User`` 와 같다. CHECK 글은 작성 시점 스냅샷이다(models 를 import
하지 않는다 — 선례 ``chat_drop_01``). 같은 글인지는 ``tests/domains/test_production_part_marks_model.py`` 가 본다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'prodpart_00'
down_revision: Union[str, None] = 'chat_drop_01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'production_part_marks'
USERS_CHECK = 'ck_users_production_part'
USERS_CHECK_SQL = "production_part IS NULL OR production_part IN ('cut','edge','assemble','inspect')"
MARKS_UNIQUE = 'uq_production_part_marks_order_key_part'
MARKS_PART_CHECK = 'ck_production_part_marks_part'
MARKS_PART_CHECK_SQL = "part IN ('cut','edge','assemble','inspect')"
MARKS_STATE_CHECK = 'ck_production_part_marks_state'
MARKS_STATE_CHECK_SQL = "state IN ('NONE','NEED','BASIC','DONE')"
MARKS_BASIC_CHECK = 'ck_production_part_marks_basic_cut'
MARKS_BASIC_CHECK_SQL = "state <> 'BASIC' OR part = 'cut'"


def _user_fk_column(name: str) -> sa.Column:
    """사용자를 가리키는 NULL 칸(사용자가 지워지면 NULL — 이름 스냅샷은 남는다)."""
    return sa.Column(name, sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)


def upgrade() -> None:
    """① 사용자 파트 칸 + CHECK → ② 표시 표 + UNIQUE · CHECK 셋."""
    op.add_column('users', sa.Column('production_part', sa.String(length=16), nullable=True))
    op.create_check_constraint(USERS_CHECK, 'users', sa.text(USERS_CHECK_SQL))

    op.create_table(
        TABLE,
        sa.Column('id', sa.BigInteger().with_variant(sa.Integer, 'sqlite'), primary_key=True),
        sa.Column('order_id', sa.Integer(), sa.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False),
        sa.Column('drawing_key', sa.String(length=500), nullable=False),
        sa.Column('sheet_id', sa.String(length=64), nullable=True),
        sa.Column('part', sa.String(length=16), nullable=False),
        sa.Column('state', sa.String(length=8), nullable=False),
        _user_fk_column('picked_by_user_id'),
        sa.Column('picked_by_name', sa.String(length=120), nullable=True),
        sa.Column('picked_at', sa.DateTime(), nullable=True),
        _user_fk_column('done_by_user_id'),
        sa.Column('done_by_name', sa.String(length=120), nullable=True),
        sa.Column('done_at', sa.DateTime(), nullable=True),
        _user_fk_column('updated_by_user_id'),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('order_id', 'drawing_key', 'part', name=MARKS_UNIQUE),
        sa.CheckConstraint(MARKS_PART_CHECK_SQL, name=MARKS_PART_CHECK),
        sa.CheckConstraint(MARKS_STATE_CHECK_SQL, name=MARKS_STATE_CHECK),
        sa.CheckConstraint(MARKS_BASIC_CHECK_SQL, name=MARKS_BASIC_CHECK),
    )


def downgrade() -> None:
    """반대 순서: 표시 표 지우기 → 사용자 CHECK · 칸 지우기."""
    op.drop_table(TABLE)
    op.drop_constraint(USERS_CHECK, 'users', type_='check')
    op.drop_column('users', 'production_part')
