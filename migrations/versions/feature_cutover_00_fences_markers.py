"""CUTOVER-MODE-01: feature cutover fences + irreversible markers

Revision ID: feature_cutover_00
Revises: rev_00_order_mutation
Create Date: 2026-07-24

§8.2 line 1518 무중단 cutover 메커니즘의 선행 스키마. 15 family 의 fence(additive
pre-seed OPEN)와 irreversible marker 정본만 만든다. 실제 business mutation 에 대한
fence/mode 적용은 각 family packet 몫이다(이 migration 은 메커니즘 테이블만 소유).

* ``feature_cutover_fences`` — family PK, mode=OPEN|DRAINING|CUTOVER, generation,
  row_version, updated_at. 15 family 를 mode=OPEN 으로 pre-seed.
* ``feature_cutover_markers`` — family PK, cutover_at/sha/generation, min compat
  generation, readiness artifact sha256, ops_approval_id, approved_by_admin_user_id,
  row_version, created_at. BEFORE UPDATE/DELETE trigger 로 irreversible.

DDL·trigger·seed SQL 은 models.py 와 SSOT 를 공유한다(create_all 테스트 lane 과 동일).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from models import (
    FEATURE_CUTOVER_FENCE_SEED_SQL,
    FEATURE_CUTOVER_MARKER_IMMUTABLE_SQL,
    FEATURE_CUTOVER_MARKER_IMMUTABLE_DROP_SQL,
)

revision: str = 'feature_cutover_00'
down_revision: Union[str, None] = 'rev_00_order_mutation'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """fence/marker 테이블 + marker irreversibility trigger + 15 family fence pre-seed."""
    op.create_table(
        'feature_cutover_fences',
        sa.Column('family', sa.String(40), primary_key=True),
        sa.Column('mode', sa.String(20), nullable=False, server_default='OPEN'),
        sa.Column('generation', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('row_version', sa.Integer(), nullable=False, server_default=sa.text('1')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.CheckConstraint(
            "mode IN ('OPEN','DRAINING','CUTOVER')",
            name='ck_feature_cutover_fence_mode',
        ),
    )

    op.create_table(
        'feature_cutover_markers',
        sa.Column('family', sa.String(40), primary_key=True),
        sa.Column('cutover_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('cutover_sha', sa.String(64), nullable=False),
        sa.Column('cutover_generation', sa.Integer(), nullable=False),
        sa.Column('minimum_compatibility_generation', sa.Integer(), nullable=False),
        sa.Column('readiness_artifact_sha256', sa.String(64), nullable=False),
        sa.Column('ops_approval_id', sa.dialects.postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('approved_by_admin_user_id', sa.Integer(), sa.ForeignKey('users.id'),
                  nullable=False),
        sa.Column('row_version', sa.Integer(), nullable=False, server_default=sa.text('1')),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
    )

    # marker irreversibility (BEFORE UPDATE/DELETE RAISE) + 15 family fence pre-seed.
    op.execute(FEATURE_CUTOVER_MARKER_IMMUTABLE_SQL)
    op.execute(FEATURE_CUTOVER_FENCE_SEED_SQL)


def downgrade() -> None:
    """생성 역순으로 trigger/함수/테이블 제거(테이블 DROP 은 row-level trigger 무관)."""
    op.execute(FEATURE_CUTOVER_MARKER_IMMUTABLE_DROP_SQL)
    op.drop_table('feature_cutover_markers')
    op.drop_table('feature_cutover_fences')
