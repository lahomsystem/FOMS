"""TASK-BACKFILL-00: order_tasks UUID identity + version + provenance expand

Revision ID: task_backfill_00
Revises: channel_webhook_00
Create Date: 2026-07-25

§5.2 TASK-BACKFILL-00 의 flat task 정본화를 위해 ``order_tasks`` 에 nullable
``task_uuid``(DB-global 안정 identity)·``version``(optimistic mutation version)·
``provenance``(backfill 표식, ``'LEGACY'``) 3개 컬럼을 **expand** 로 추가한다.

Task 는 오늘 auto-increment ``id`` 로만 식별되고 mutation version·출처(runtime/legacy)
구분이 없어, 낙관적 동시성·전이(TASK-01)·auto_key 중복 정리의 기준점이 없다. 이
registry-less identity 확장은 task 마다 안정 UUID 를 발급할 자리를 마련한다.

이 마이그레이션은 **expand 단계** 다: 컬럼을 nullable 로만 추가하고, backfill(safe 만
UUID/version seed·LEGACY 표식·자동 매핑 0) 이후 ambiguous(orphan/status/date/team/
user/auto_key collision) 0건이 확인되기 전에는 NOT NULL·auto_key collision unique
enforcement 를 걸지 않는다(``backfill_order_tasks.can_enforce`` 게이트). DDL 은
``models.OrderTask`` (create_all 테스트 lane)과 SSOT 를 공유한다. 순수 스키마 추가라
기존 runtime 의미 변경은 0 이다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'task_backfill_00'
down_revision: Union[str, None] = 'channel_webhook_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """order_tasks 에 nullable task_uuid/version/provenance 추가 + task_uuid partial-unique."""
    op.add_column('order_tasks', sa.Column(
        'task_uuid', postgresql.UUID(as_uuid=False), nullable=True,
    ))
    op.add_column('order_tasks', sa.Column('version', sa.Integer(), nullable=True))
    op.add_column('order_tasks', sa.Column('provenance', sa.String(length=20), nullable=True))
    # 발급된 UUID 는 전 DB 유일(partial — 아직 미발급/ambiguous NULL 행은 제외).
    op.create_index(
        'uq_order_task_uuid', 'order_tasks', ['task_uuid'],
        unique=True, postgresql_where=sa.text('task_uuid IS NOT NULL'),
    )


def downgrade() -> None:
    """생성 역순으로 인덱스/컬럼 제거."""
    op.drop_index('uq_order_task_uuid', table_name='order_tasks')
    op.drop_column('order_tasks', 'provenance')
    op.drop_column('order_tasks', 'version')
    op.drop_column('order_tasks', 'task_uuid')
