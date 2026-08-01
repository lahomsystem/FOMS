"""AS-BACKFILL-00: AS cycle 정본 UUID registry

Revision ID: as_backfill_00
Revises: production_backfill_00
Create Date: 2026-07-24

§5.2 AS-BACKFILL-00 의 ``order_as_cycles``(AS 실행 cycle 의 DB-global UUID registry)를
신설한다. AS 는 오늘 주문마다 flat ``structured_data['as_info']`` 리스트(접수/방문일정/완료가
한 entry 에 뭉쳐 append)와 flat ``order.status``/``workflow.history`` 의 AS 전이로만 기록돼
실행별 cycle 경계·current cycle 포인터가 남지 않는다. 이 registry 는 AS 발생마다 안정 UUID
cycle 을 발급해 transition/schedule/completion/classification 을 cycle 단위로 귀속하며,
:data:`~foms.services.orders.state_axes.AS_VALUES` (``RECEIVED|IN_PROGRESS|COMPLETED``)
read-model 과 shape 를 정합시킨다(주문당 current cycle 0/1).

이 마이그레이션은 **순수 스키마 추가** 다: 테이블만 만들고, 기존 flat ``as_info``/status/
history 는 그대로 둔다(backfill 은 flat 을 복제만 하고 삭제/재작성하지 않는다). cycle 을 읽는
전이/명령(create/complete)의 활성화는 하류 STATE-AS-01 소관이므로 이 단계는 runtime 의미
변경이 0 이다. DDL 은 ``models.OrderASCycle`` (create_all 테스트 lane)과 SSOT 를 공유한다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'as_backfill_00'
down_revision: Union[str, None] = 'production_backfill_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """order_as_cycles 생성 + order_id 인덱스 + current/legacy partial-unique."""
    op.create_table(
        'order_as_cycles',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column('order_id', sa.Integer(),
                  sa.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),  # RECEIVED|IN_PROGRESS|COMPLETED
        # 발급 시점 as_info entry id(provenance·backfill 멱등 키).
        sa.Column('legacy_as_id', sa.Integer(), nullable=True),
        # transition(시작) 스냅샷 — flat as_info entry 의 started_at/started_by.
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('started_by', sa.String(length=120), nullable=True),
        # classification 스냅샷 — AS 사유/설명.
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        # schedule 스냅샷 — AS 방문일/시각(legacy 문자열 원문 보존).
        sa.Column('visit_date', sa.String(length=32), nullable=True),
        sa.Column('visit_time', sa.String(length=32), nullable=True),
        # completion 스냅샷 — 완료 시각/담당/메모.
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('completed_by', sa.String(length=120), nullable=True),
        sa.Column('completion_note', sa.Text(), nullable=True),
        sa.Column('is_current', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_order_as_cycles_order_id', 'order_as_cycles', ['order_id'])
    # 한 주문의 current(열린) cycle 은 최대 1개("current cycle 0/1" 불변식의 DB 표현).
    # 종결된 cycle(is_current=false)은 여러 개 이력으로 남을 수 있다.
    op.create_index(
        'uq_order_as_cycle_current', 'order_as_cycles',
        ['order_id'], unique=True, postgresql_where=sa.text('is_current'),
    )
    # 한 주문의 한 legacy as_info entry 에 cycle 은 최대 1개(중복 발급 방지·backfill 멱등).
    op.create_index(
        'uq_order_as_cycle_legacy', 'order_as_cycles',
        ['order_id', 'legacy_as_id'], unique=True,
        postgresql_where=sa.text('legacy_as_id IS NOT NULL'),
    )


def downgrade() -> None:
    """생성 역순으로 인덱스/테이블 제거."""
    op.drop_index('uq_order_as_cycle_legacy', table_name='order_as_cycles')
    op.drop_index('uq_order_as_cycle_current', table_name='order_as_cycles')
    op.drop_index('ix_order_as_cycles_order_id', table_name='order_as_cycles')
    op.drop_table('order_as_cycles')
