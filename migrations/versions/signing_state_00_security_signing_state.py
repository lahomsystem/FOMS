"""SESSION-SIGNING-STATE-00: signing-key state machine + WAM entry nonces

Revision ID: signing_state_00
Revises: sidefx_00
Create Date: 2026-07-24

§2.1 line 225-227 의 signing-key 상태기계·nonce 스키마를 **additive expand** 로 먼저
배포한다. ``security_signing_state`` singleton(id=1) 과 ``wam_entry_nonces`` 만 만들고
singleton 을 ``mode=EMPTY, maintenance_mode=OFF, generation=0`` 으로 seed 한다.

기존 runtime 은 이 두 table 도 새 env 도 읽지 않으므로 cookie/token 의미는 변하지 않는다
(seed 외 의미 변경 0). 실제 runtime 서명 전환·activation(EMPTY→READY 이후의 active=pending·
deadline 기록·READY→ACTIVE)은 SESSION-SIGNING-SECRET-01 몫이다.

singleton EMPTY seed SQL 은 ``models.SECURITY_SIGNING_STATE_SEED_SQL`` 을 공유해 ORM
(create_all 테스트 lane)과 DDL drift 를 막는다(fence/principal 과 같은 이중 SSOT 패턴).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from models import SECURITY_SIGNING_STATE_SEED_SQL

revision: str = 'signing_state_00'
down_revision: Union[str, None] = 'sidefx_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """signing state singleton + WAM nonce 테이블 생성 + id=1 EMPTY/OFF/gen0 seed."""
    op.create_table(
        'security_signing_state',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('mode', sa.String(20), nullable=False, server_default='EMPTY'),
        sa.Column('maintenance_mode', sa.String(20), nullable=False, server_default='OFF'),
        sa.Column('maintenance_started_at', sa.DateTime(), nullable=True),
        sa.Column('generation', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('session_epoch', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('wam_not_before', sa.DateTime(), nullable=True),
        sa.Column('active_key_id', sa.String(64), nullable=True),
        sa.Column('previous_key_id', sa.String(64), nullable=True),
        sa.Column('pending_key_id', sa.String(64), nullable=True),
        sa.Column('previous_not_after', sa.DateTime(), nullable=True),
        sa.Column('legacy_cutover_mode', sa.String(20), nullable=True),
        sa.Column('legacy_flask_not_after', sa.DateTime(), nullable=True),
        sa.Column('legacy_wam_not_after', sa.DateTime(), nullable=True),
        sa.Column('grace_seconds', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('row_version', sa.Integer(), nullable=False, server_default=sa.text('1')),
        sa.Column('prepared_consumer_sha', sa.String(64), nullable=True),
        sa.Column('prepared_key_artifact_sha256', sa.String(64), nullable=True),
        sa.Column('prepared_rollout_artifact_sha256', sa.String(64), nullable=True),
        sa.Column('rescue_deployment_sha', sa.String(64), nullable=True),
        sa.Column('prepared_at', sa.DateTime(), nullable=True),
        sa.Column('activated_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_by_admin_user_id', sa.Integer(),
                  sa.ForeignKey('users.id'), nullable=True),
        # singleton — id 는 1 만 허용.
        sa.CheckConstraint('id = 1', name='ck_signing_state_singleton'),
        sa.CheckConstraint(
            "mode IN ('EMPTY','READY','ACTIVE','CURRENT_ONLY','ROTATION_READY','ROTATING')",
            name='ck_signing_state_mode',
        ),
        sa.CheckConstraint(
            "maintenance_mode IN ('OFF','AUTH_ONLY')",
            name='ck_signing_state_maintenance_mode',
        ),
        sa.CheckConstraint(
            "legacy_cutover_mode IS NULL OR legacy_cutover_mode IN ('BRIDGE','FORCE_REAUTH')",
            name='ck_signing_state_legacy_cutover_mode',
        ),
    )

    op.create_table(
        'wam_entry_nonces',
        sa.Column('nonce_hash', sa.String(64), primary_key=True),
        sa.Column('subject_hash', sa.String(64), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('consumed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
    )

    # singleton EMPTY/OFF/gen0 seed (models 와 SSOT 공유).
    op.execute(SECURITY_SIGNING_STATE_SEED_SQL)


def downgrade() -> None:
    """생성 역순으로 테이블 제거(seed 행은 테이블과 함께 사라진다)."""
    op.drop_table('wam_entry_nonces')
    op.drop_table('security_signing_state')
