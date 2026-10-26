"""PARTMEM-00: drawing_part_memory — 도면 마법사 그림 종류 기억(특징 숫자 + 이름표)

Revision ID: partmem_00
Revises: mine_toplevel_drawing_idx_00
Create Date: 2026-10-26

설계 정본: ``docs/plans/2026-10-26-drawing-part-memory-spec.md`` §3.1.

* ``drawing_part_memory`` — 브라우저 AI 가 계산한 그림 특징(float16 × 768 = 1,536바이트)과
  이름표(label·src)·AI 첫 짐작(ai·conf·head)을 주문(order_id FK CASCADE)·그림 키(asset_key)
  하나마다 한 줄로 둔다. 그림 자체는 두지 않는다.
* ``uq_drawing_part_memory_order_key`` — 같은 주문의 같은 그림은 한 줄(덮어쓰기 기준).
* ``ix_drawing_part_memory_updated_at`` — 찾기 캐시가 바뀐 줄만 다시 읽는 기준.

데이터를 바꾸지 않는 표 신설뿐이다. ``downgrade()`` 는 만든 역순으로 지운다(기억은 학습용 사본이라
원본 이름표는 마법사 시트에 그대로 남는다). DDL 은 models.py ``DrawingPartMemory`` 와 같다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'partmem_00'
down_revision: Union[str, None] = 'mine_toplevel_drawing_idx_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """drawing_part_memory 표·색인 만들기."""
    op.create_table(
        'drawing_part_memory',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('order_id', sa.Integer(),
                  sa.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False),
        sa.Column('asset_key', sa.String(500), nullable=False),
        sa.Column('feat', sa.LargeBinary(), nullable=True),
        sa.Column('feat_v', sa.String(16), nullable=True),
        sa.Column('ai', sa.String(16), nullable=True),
        sa.Column('conf', sa.Float(), nullable=True),
        sa.Column('head', sa.String(16), nullable=True),
        sa.Column('label', sa.String(16), nullable=False),
        sa.Column('src', sa.String(8), nullable=False, server_default='ai'),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_by', sa.Integer(),
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('updated_by', sa.Integer(),
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('order_id', 'asset_key', name='uq_drawing_part_memory_order_key'),
        sa.CheckConstraint("src IN ('ai','user')", name='ck_drawing_part_memory_src'),
    )
    op.create_index('ix_drawing_part_memory_order_id', 'drawing_part_memory', ['order_id'])
    op.create_index('ix_drawing_part_memory_updated_at', 'drawing_part_memory', ['updated_at'])


def downgrade() -> None:
    """만든 역순으로 색인 → 표 지우기."""
    op.drop_index('ix_drawing_part_memory_updated_at', table_name='drawing_part_memory')
    op.drop_index('ix_drawing_part_memory_order_id', table_name='drawing_part_memory')
    op.drop_table('drawing_part_memory')
