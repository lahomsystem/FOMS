"""CONSTRUCTION-BACKFILL-00: 시공 attempt 정본 UUID registry

Revision ID: construction_backfill_00
Revises: order_import_00
Create Date: 2026-07-27

§5.2 CONSTRUCTION-BACKFILL-00 의 ``order_construction_attempts``(시공 실행 attempt 의
DB-global UUID registry)를 신설한다. 시공은 오늘 주문마다 flat ``workflow.history`` 의
``시공 시작`` 진입·``structured_data['construction_fail_history']``(시공 불가 재작업 리스트)·
``construction.evidence``·``schedule.construction`` 와 시공 완료 시 ``order.status`` 의
``COMPLETED`` 전이로만 기록돼 attempt 별 경계·current attempt 포인터가 남지 않는다. 이
registry 는 시공 attempt 마다 안정 UUID attempt 를 발급해 schedule/transition/completion/
classification 을 attempt 단위로 귀속하며,
:data:`~foms.services.orders.state_axes.CONSTRUCTION_VALUES`
(``IN_PROGRESS|READY|COMPLETED|REWORKED``) read-model 과 shape 를 정합시킨다(주문당 current
attempt 0/1).

이 마이그레이션은 **순수 스키마 추가** 다: 테이블만 만들고, 기존 flat 시공 데이터(history/
fail_history/evidence/schedule/status)는 그대로 둔다(backfill 은 flat 을 복제만 하고 삭제/
재작성하지 않으며, 시공 완료의 직접 COMPLETED 추론은 금지된다). attempt 를 읽는 전이/명령의
활성화는 하류 STATE-CONST-CS 소관이므로 이 단계는 runtime 의미 변경이 0 이다. DDL 은
``models.OrderConstructionAttempt`` (create_all 테스트 lane)과 SSOT 를 공유한다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'construction_backfill_00'
down_revision: Union[str, None] = 'order_import_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """order_construction_attempts 생성 + order_id 인덱스 + current/legacy partial-unique."""
    op.create_table(
        'order_construction_attempts',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column('order_id', sa.Integer(),
                  sa.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),  # IN_PROGRESS|READY|COMPLETED|REWORKED
        # 발급 시점 시공 시작 ordinal(provenance·backfill 멱등 키).
        sa.Column('legacy_seq', sa.Integer(), nullable=True),
        # schedule 스냅샷 — 시공 예정일(legacy 문자열 원문 보존).
        sa.Column('scheduled_date', sa.String(length=32), nullable=True),
        # transition(시작) 스냅샷 — workflow.history "시공 시작" entry.
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('started_by', sa.String(length=120), nullable=True),
        # completion 스냅샷 — 완료 시각/담당/메모.
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('completed_by', sa.String(length=120), nullable=True),
        sa.Column('completion_note', sa.Text(), nullable=True),
        # classification 스냅샷 — REWORKED attempt 의 시공 불가 사유/상세.
        sa.Column('fail_reason', sa.String(length=40), nullable=True),
        sa.Column('fail_detail', sa.Text(), nullable=True),
        # evidence 스냅샷 — construction.evidence(before/after/signature) 참조.
        sa.Column('evidence', postgresql.JSONB(), nullable=True),
        sa.Column('is_current', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_order_construction_attempts_order_id',
                    'order_construction_attempts', ['order_id'])
    # 한 주문의 current(열린) attempt 는 최대 1개("current attempt 0/1" 불변식의 DB 표현).
    # 종결된 attempt(is_current=false)은 여러 개 이력으로 남을 수 있다.
    op.create_index(
        'uq_construction_attempt_current', 'order_construction_attempts',
        ['order_id'], unique=True, postgresql_where=sa.text('is_current'),
    )
    # 한 주문의 한 legacy 시공 시작 ordinal 에 attempt 는 최대 1개(중복 발급 방지·backfill 멱등).
    op.create_index(
        'uq_construction_attempt_legacy', 'order_construction_attempts',
        ['order_id', 'legacy_seq'], unique=True,
        postgresql_where=sa.text('legacy_seq IS NOT NULL'),
    )


def downgrade() -> None:
    """생성 역순으로 인덱스/테이블 제거."""
    op.drop_index('uq_construction_attempt_legacy',
                  table_name='order_construction_attempts')
    op.drop_index('uq_construction_attempt_current',
                  table_name='order_construction_attempts')
    op.drop_index('ix_order_construction_attempts_order_id',
                  table_name='order_construction_attempts')
    op.drop_table('order_construction_attempts')
