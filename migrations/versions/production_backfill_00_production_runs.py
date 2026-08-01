"""PRODUCTION-BACKFILL-00: production run 정본 UUID registry

Revision ID: production_backfill_00
Revises: item_id_00
Create Date: 2026-07-24

§5.2 PRODUCTION-BACKFILL-00 의 ``production_runs``(생산 실행 DB-global UUID run registry)
를 신설한다. 생산 공정은 오늘 주문마다 단일 flat ``structured_data['production']``(단일
steps/defects 리스트·rework count)로만 기록돼 실행별 step/defect scope 경계가 남지 않는다.
이 registry 는 실행마다 안정 UUID run 을 발급해 scope 를 실행 단위로 귀속하며,
:func:`~foms.services.orders.state_axes.read_current_production_run` 의 canonical target
(``production.runs[]`` + ``current_run_id``)과 shape 를 정합시킨다.

이 마이그레이션은 **순수 스키마 추가** 다: 테이블만 만들고, 기존 flat production 데이터는
그대로 둔다(backfill 은 flat 을 복제만 하고 삭제하지 않는다). run 을 읽는 전이/명령의
활성화는 하류 STATE-PROD-01 소관이므로 이 단계는 runtime 의미 변경이 0 이다. DDL 은
``models.ProductionRun`` (create_all 테스트 lane) 과 SSOT 를 공유한다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'production_backfill_00'
down_revision: Union[str, None] = 'item_id_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """production_runs 생성 + order_id 인덱스 + current run partial-unique."""
    op.create_table(
        'production_runs',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column('order_id', sa.Integer(),
                  sa.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),  # IN_PROGRESS|COMPLETED|SUPERSEDED
        # legacy 생산 시작 시각(provenance) — flat workflow.history 의 PRODUCTION 진입 시각.
        sa.Column('started_at', sa.DateTime(), nullable=True),
        # 실행 단위 step/defect scope 스냅샷(flat production.steps/defects 복제 — flat 보존).
        sa.Column('steps', postgresql.JSONB(), nullable=True),
        sa.Column('defects', postgresql.JSONB(), nullable=True),
        sa.Column('is_current', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_production_runs_order_id', 'production_runs', ['order_id'])
    # 한 주문의 current run 은 최대 1개(current_run_id 포인터 DB 표현·backfill 멱등).
    # 종결된 run(is_current=false)은 여러 개 이력으로 남을 수 있다.
    op.create_index(
        'uq_production_run_current', 'production_runs',
        ['order_id'], unique=True, postgresql_where=sa.text('is_current'),
    )


def downgrade() -> None:
    """생성 역순으로 인덱스/테이블 제거."""
    op.drop_index('uq_production_run_current', table_name='production_runs')
    op.drop_index('ix_production_runs_order_id', table_name='production_runs')
    op.drop_table('production_runs')
