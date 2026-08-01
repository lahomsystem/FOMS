"""WDC-LINK-FENCE-00: WDC link cutover runtime state (SEPARATE topology)

Revision ID: wdc_link_fence_00
Revises: index_ops_00
Create Date: 2026-07-25

§8.2 line 734 의 SEPARATE_DATABASE topology WDC link fence 정본 스키마. WDC(WDCalculator)
link migration 이 legacy ``EstimateOrderMatch`` → canonical ``estimate_order_links_v2`` 로
넘어갈 때 WDC DB 에서 상태(``LEGACY → FROZEN → CANONICAL``)를 게이트하는 singleton 을 만든다.

* ``wdc_link_runtime_state`` — id PK(singleton, ``id = 1``), mode(LEGACY|FROZEN|CANONICAL),
  generation, row_version, prepared_consumer_generation, frozen_at, freeze_source_fingerprint,
  freeze_rollout_artifact_sha256, updated_at, updated_by_admin_user_id.

singleton **row 는 seed 하지 않는다**. SAME_DATABASE topology 는 이 상태기계를 쓰지 않으므로
(한 tx / no-freeze) row seed 는 SEPARATE 프로비저닝(하류)이 WDC DB 에서 수행한다
(``foms.services.security.cutover.wdc_link_fence.seed_wdc_link_runtime_state``). 이 migration
은 스키마(빈 테이블)만 만든다 — models.py 와 SSOT 를 공유하며 create_all 테스트 lane 과 동형이다.

fence 전이 로직 / freeze / canonical / abort CLI 는 WDC-LINK-BACKFILL-00 / WDC-LINK-01 하류
몫이다(이 packet 은 fence 정의만).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'wdc_link_fence_00'
down_revision: Union[str, None] = 'index_ops_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """SEPARATE topology WDC link fence singleton 테이블 생성(row seed 없음)."""
    op.create_table(
        'wdc_link_runtime_state',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('mode', sa.String(20), nullable=False, server_default='LEGACY'),
        sa.Column('generation', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('row_version', sa.Integer(), nullable=False, server_default=sa.text('1')),
        sa.Column('prepared_consumer_generation', sa.Integer(), nullable=True),
        sa.Column('frozen_at', sa.DateTime(), nullable=True),
        sa.Column('freeze_source_fingerprint', sa.String(64), nullable=True),
        sa.Column('freeze_rollout_artifact_sha256', sa.String(64), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_by_admin_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.CheckConstraint(
            "mode IN ('LEGACY','FROZEN','CANONICAL')",
            name='ck_wdc_link_state_mode',
        ),
        sa.CheckConstraint('id = 1', name='ck_wdc_link_state_singleton'),
    )


def downgrade() -> None:
    """singleton 테이블 제거."""
    op.drop_table('wdc_link_runtime_state')
