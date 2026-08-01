"""BACKFILL-ARTIFACT-00: encrypted backfill run/checkpoint/append-only approval schema

Revision ID: backfill_artifact_00
Revises: feature_cutover_00
Create Date: 2026-07-24

§7.3 line 1255-1259 의 공용 backfill run 정본 스키마. 모든 remediation audit/backfill
도구가 공유하는 resume run state machine 만 만든다(실제 domain business write 는 각
consumer packet 몫).

* ``maintenance_backfill_runs`` — run_id PK, lease/heartbeat, state machine, row_version CAS.
* ``maintenance_backfill_checkpoints`` — batch 진행 원장((run_id,batch_seq) unique).
* ``maintenance_backfill_approvals`` — approval seq append-only((run_id,seq) unique) +
  BEFORE UPDATE/DELETE RAISE trigger.

trigger DDL 은 models.py 와 SSOT 를 공유한다(create_all 테스트 lane 과 동일 SQL).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from models import (
    MAINTENANCE_BACKFILL_APPROVAL_APPEND_ONLY_SQL,
    MAINTENANCE_BACKFILL_APPROVAL_APPEND_ONLY_DROP_SQL,
)

revision: str = 'backfill_artifact_00'
down_revision: Union[str, None] = 'feature_cutover_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """run/checkpoint/approval 테이블 + approval append-only trigger 생성."""
    op.create_table(
        'maintenance_backfill_runs',
        sa.Column('run_id', sa.String(64), primary_key=True),
        sa.Column('packet_id', sa.String(80), nullable=False),
        sa.Column('phase', sa.String(80), nullable=False),
        sa.Column('db_instance_id', sa.String(120), nullable=False),
        sa.Column('manifest_sha256', sa.String(64), nullable=False),
        sa.Column('mapping_sha256', sa.String(64), nullable=False),
        sa.Column('current_approval_seq', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('state', sa.String(20), nullable=False, server_default='PENDING'),
        sa.Column('lease_owner_hash', sa.String(64), nullable=True),
        sa.Column('lease_token_hash', sa.String(64), nullable=True),
        sa.Column('lease_expires_at', sa.DateTime(), nullable=True),
        sa.Column('heartbeat_at', sa.DateTime(), nullable=True),
        sa.Column('total_rows', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('completed_rows', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('last_error_code', sa.String(40), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('row_version', sa.Integer(), nullable=False, server_default=sa.text('1')),
        sa.CheckConstraint(
            "state IN ('PENDING','RUNNING','PAUSED_APPROVAL','STOPPED_DRIFT','VERIFYING','DONE')",
            name='ck_maintenance_backfill_run_state',
        ),
    )

    op.create_table(
        'maintenance_backfill_checkpoints',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('run_id', sa.String(64), sa.ForeignKey('maintenance_backfill_runs.run_id'),
                  nullable=False),
        sa.Column('batch_seq', sa.Integer(), nullable=False),
        sa.Column('completed_rows', sa.Integer(), nullable=False),
        sa.Column('checkpoint_sha256', sa.String(64), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('run_id', 'batch_seq', name='uq_maintenance_backfill_checkpoint_seq'),
    )

    op.create_table(
        'maintenance_backfill_approvals',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('run_id', sa.String(64), sa.ForeignKey('maintenance_backfill_runs.run_id'),
                  nullable=False),
        sa.Column('seq', sa.Integer(), nullable=False),
        sa.Column('approval_id', sa.dialects.postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('kind', sa.String(20), nullable=False),
        sa.Column('admin_principal_version', sa.Integer(), nullable=False),
        sa.Column('composite_sha256', sa.String(64), nullable=False),
        sa.Column('reason_code', sa.String(40), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('run_id', 'seq', name='uq_maintenance_backfill_approval_seq'),
        sa.CheckConstraint(
            "kind IN ('APPLY','REAUTHORIZE')",
            name='ck_maintenance_backfill_approval_kind',
        ),
    )

    # approval append-only (BEFORE UPDATE/DELETE RAISE).
    op.execute(MAINTENANCE_BACKFILL_APPROVAL_APPEND_ONLY_SQL)


def downgrade() -> None:
    """생성 역순으로 trigger/함수/테이블 제거."""
    op.execute(MAINTENANCE_BACKFILL_APPROVAL_APPEND_ONLY_DROP_SQL)
    op.drop_table('maintenance_backfill_approvals')
    op.drop_table('maintenance_backfill_checkpoints')
    op.drop_table('maintenance_backfill_runs')
