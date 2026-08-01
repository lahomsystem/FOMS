"""AUTH-ACCOUNT-01: auth anti-abuse rate-limit key state machine

Revision ID: auth_account_00
Revises: startup_schema_00
Create Date: 2026-07-26

anti-abuse rate limiter 의 서명 key bootstrap/rotation 을 관리하는 ``auth_rate_key_state``
singleton(id=1)을 **additive expand** 로 배포한다. SESSION-SIGNING-STATE-00 의
``security_signing_state`` 와 동형인 prepare/activate 상태기계이며, key material 은
AES-256-GCM envelope(``*_key_ciphertext``)로 at-rest 암호화 저장한다(plaintext 키 금지).

기존 runtime 은 이 table 도 새 env(``FOMS_AUTH_RATE_KEY_ENGAGED``)도 읽지 않으므로 rate
bucket 의미는 변하지 않는다(seed 외 의미 변경 0·기존 rate 강제 무효화 0). 실제 runtime
bridge(bucket 서명)는 operator 가 env 로 engage + BOOTSTRAP_ACTIVATE 로 키를 활성화한 뒤에만
동작한다.

singleton EMPTY seed SQL 은 ``models.AUTH_RATE_KEY_STATE_SEED_SQL`` 을 공유해 ORM
(create_all 테스트 lane)과 DDL drift 를 막는다(SecuritySigningState 와 같은 이중 SSOT 패턴).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from models import AUTH_RATE_KEY_STATE_SEED_SQL

revision: str = 'auth_account_00'
down_revision: Union[str, None] = 'startup_schema_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """auth-rate key state singleton 테이블 생성 + id=1 EMPTY/version1/gen0 seed."""
    op.create_table(
        'auth_rate_key_state',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('mode', sa.String(20), nullable=False, server_default='EMPTY'),
        sa.Column('version', sa.Integer(), nullable=False, server_default=sa.text('1')),
        sa.Column('generation', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('active_key_id', sa.String(64), nullable=True),
        sa.Column('previous_key_id', sa.String(64), nullable=True),
        sa.Column('pending_key_id', sa.String(64), nullable=True),
        sa.Column('active_key_ciphertext', sa.Text(), nullable=True),
        sa.Column('previous_key_ciphertext', sa.Text(), nullable=True),
        sa.Column('pending_key_ciphertext', sa.Text(), nullable=True),
        sa.Column('previous_not_after', sa.DateTime(), nullable=True),
        sa.Column('prepared_key_artifact_sha256', sa.String(64), nullable=True),
        sa.Column('prepared_rollout_artifact_sha256', sa.String(64), nullable=True),
        sa.Column('prepared_at', sa.DateTime(), nullable=True),
        sa.Column('activated_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_by_admin_user_id', sa.Integer(),
                  sa.ForeignKey('users.id'), nullable=True),
        # singleton — id 는 1 만 허용.
        sa.CheckConstraint('id = 1', name='ck_auth_rate_key_singleton'),
        sa.CheckConstraint(
            "mode IN ('EMPTY','READY','ACTIVE','ROTATION_READY','ROTATING')",
            name='ck_auth_rate_key_mode',
        ),
    )

    # singleton EMPTY/version1/gen0 seed (models 와 SSOT 공유).
    op.execute(AUTH_RATE_KEY_STATE_SEED_SQL)


def downgrade() -> None:
    """테이블 제거(seed 행은 테이블과 함께 사라진다)."""
    op.drop_table('auth_rate_key_state')
