"""OPS-APPROVAL-00: principal versions + ops approval requests + cross-DB audit

Revision ID: ops_approval_00
Revises: phase_0a_notif_user_states
Create Date: 2026-07-24

고위험 ops 승인 인프라의 선행 스키마(§2.1 line 189/205/207):

* ``security_principal_versions`` + PostgreSQL trigger(``password|role|team|
  is_active`` 변경 tx 에서 정확히 1 증가, 기존 User 는 version 1 seed).
* ``ops_approval_requests`` 정본(전 컬럼).
* ``ops_approval_target_audits`` (cross-DB TARGET_RESERVED consume 의 target 측
  unique idempotency/audit).

trigger DDL 은 models.py 와 SSOT 를 공유한다(create_all 테스트 lane 과 동일 SQL).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from models import (
    OPS_PRINCIPAL_VERSION_TRIGGER_SQL,
    OPS_PRINCIPAL_VERSION_TRIGGER_DROP_SQL,
)

revision: str = 'ops_approval_00'
down_revision: Union[str, None] = 'phase_0a_notif_user_states'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """principal-version / approval-request / target-audit 스키마 + trigger 생성."""
    op.create_table(
        'security_principal_versions',
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), primary_key=True),
        sa.Column('version', sa.Integer(), nullable=False, server_default=sa.text('1')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
    )

    op.create_table(
        'ops_approval_requests',
        sa.Column('id', sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column('operation_type', sa.String(80), nullable=False),
        sa.Column('scope_sha256', sa.String(64), nullable=False),
        sa.Column('artifact_sha256', sa.String(64), nullable=True),
        sa.Column('expected_version', sa.Integer(), nullable=True),
        sa.Column('expected_generation', sa.Integer(), nullable=True),
        sa.Column('nonce_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('state', sa.String(20), nullable=False, server_default='PENDING'),
        sa.Column('approved_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('approved_principal_version', sa.Integer(), nullable=True),
        sa.Column('approved_at', sa.DateTime(), nullable=True),
        sa.Column('reservation_id', sa.dialects.postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column('reserved_at', sa.DateTime(), nullable=True),
        sa.Column('reservation_expires_at', sa.DateTime(), nullable=True),
        sa.Column('consumed_at', sa.DateTime(), nullable=True),
        sa.Column('operator_identity_hash', sa.String(64), nullable=False),
        sa.Column('result_sha256', sa.String(64), nullable=True),
        sa.Column('row_version', sa.Integer(), nullable=False, server_default=sa.text('1')),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.CheckConstraint(
            "state IN ('PENDING','APPROVED','RESERVED','CONSUMED','EXPIRED','REVOKED')",
            name='ck_ops_approval_state',
        ),
    )
    op.create_index(
        'ix_ops_approval_state_expires', 'ops_approval_requests', ['state', 'expires_at']
    )

    op.create_table(
        'ops_approval_target_audits',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('approval_id', sa.dialects.postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('reservation_id', sa.dialects.postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('operation_scope_sha256', sa.String(64), nullable=False),
        sa.Column('operation_id', sa.String(80), nullable=False),
        sa.Column('result_sha256', sa.String(64), nullable=True),
        sa.Column('committed_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint(
            'approval_id', 'reservation_id', 'operation_scope_sha256',
            name='uq_ops_approval_target_audit',
        ),
    )

    # principal-version trigger + 기존 User version 1 seed (application increment 금지).
    op.execute(OPS_PRINCIPAL_VERSION_TRIGGER_SQL)
    op.execute(
        "INSERT INTO security_principal_versions (user_id, version, updated_at) "
        "SELECT id, 1, now() FROM users ON CONFLICT (user_id) DO NOTHING"
    )


def downgrade() -> None:
    """생성 역순으로 trigger/함수/테이블 제거."""
    op.execute(OPS_PRINCIPAL_VERSION_TRIGGER_DROP_SQL)
    op.drop_table('ops_approval_target_audits')
    op.drop_index('ix_ops_approval_state_expires', table_name='ops_approval_requests')
    op.drop_table('ops_approval_requests')
    op.drop_table('security_principal_versions')
