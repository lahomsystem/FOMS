"""SHIPMENT-REFERENCE-01: SystemSetting revision + reference collection normalize

Revision ID: shipment_reference_00
Revises: auth_account_00
Create Date: 2026-07-26

출고 reference 설정(``erp_shipment_settings``)을 optimistic-lock revision + collection
receipt 로 승격한다. 세 부분의 additive 마이그레이션이다.

1. ``system_settings.version`` 컬럼(Integer, NOT NULL, server_default 1) — 모든 setting
   row 의 낙관 잠금 version. 기존 row 는 default 1 로 채운다.
2. ``system_setting_receipts`` 테이블 — collection mutation 의 idempotency + audit receipt
   (REV-00 order receipt 과 분리; setting_key 단위 revision).
3. ``erp_shipment_settings`` row 의 old drawing 필드(``drawing_manager`` list +
   ``drawing_manager_en`` dict)를 한 canonical object array(``drawing_managers``
   ``[{name, english_name}]``)로 **무손실 safe backfill**하고, ``measurement_manager`` →
   ``measurement_managers`` 로 rename 한다. ``construction_time``/``site_extra``/
   ``construction_workers`` 값은 보존한다(worker master 는 CREW-00 소관이나 read 소비처를
   위해 유실하지 않는다).

정규화 로직은 ``foms.services.shipment_reference`` 와 공유해 DDL/런타임 drift 를 막는다.
migration 은 PostgreSQL(alembic)에서만 실행되므로 setting_value(JSONB) 갱신은 ``::jsonb``
캐스트로 원자 갱신한다(테스트 lane 은 create_all 사용). ``downgrade()`` 는 canonical →
legacy 로 되돌린다(무손실 역변환).
"""
import json
from typing import Optional, Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'shipment_reference_00'
down_revision: Union[str, None] = 'auth_account_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SETTING_KEY = 'erp_shipment_settings'


def _load_setting_value(bind) -> Optional[dict]:
    """``erp_shipment_settings`` row 의 setting_value(dict)를 읽는다(없으면 None)."""
    row = bind.execute(
        sa.text("SELECT setting_value FROM system_settings WHERE setting_key = :k"),
        {"k": _SETTING_KEY},
    ).fetchone()
    if row is None or not isinstance(row[0], dict):
        return None
    return row[0]


def _store_setting_value(bind, value: dict) -> None:
    """setting_value(JSONB)를 ``::jsonb`` 캐스트로 원자 갱신한다."""
    bind.execute(
        sa.text(
            "UPDATE system_settings SET setting_value = CAST(:v AS jsonb) "
            "WHERE setting_key = :k"
        ),
        {"v": json.dumps(value, ensure_ascii=False), "k": _SETTING_KEY},
    )


def upgrade() -> None:
    """version 컬럼·receipt 테이블 추가 + reference collection canonical normalize."""
    op.add_column(
        'system_settings',
        sa.Column('version', sa.Integer(), nullable=False, server_default=sa.text('1')),
    )
    op.create_table(
        'system_setting_receipts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('read_receipt_id', sa.String(36), nullable=False),
        sa.Column('actor_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('setting_key', sa.String(100), nullable=False),
        sa.Column('policy_id', sa.String(80), nullable=False),
        sa.Column('idempotency_key', sa.String(64), nullable=True),
        sa.Column('request_hash', sa.String(64), nullable=False),
        sa.Column('response_status', sa.Integer(), nullable=False),
        sa.Column('response_body', sa.JSON(), nullable=False),
        sa.Column('resulting_version', sa.Integer(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('read_receipt_id', name='uq_system_setting_receipt_read_id'),
        sa.UniqueConstraint('actor_user_id', 'policy_id', 'idempotency_key',
                            name='uq_system_setting_receipt_idem'),
    )
    op.create_index('ix_ssr_setting_key', 'system_setting_receipts', ['setting_key'])
    op.create_index('ix_ssr_expires_id', 'system_setting_receipts', ['expires_at', 'id'])

    # reference collection 무손실 normalize (old drawing 필드 → drawing_managers object array).
    from foms.services.shipment_reference import backfill_drawing_managers_from_legacy

    bind = op.get_bind()
    value = _load_setting_value(bind)
    if value is not None:
        new_value = dict(value)
        new_value['drawing_managers'] = backfill_drawing_managers_from_legacy(
            value.get('drawing_manager'), value.get('drawing_manager_en')
        )
        new_value.pop('drawing_manager', None)
        new_value.pop('drawing_manager_en', None)
        if 'measurement_manager' in new_value and 'measurement_managers' not in new_value:
            new_value['measurement_managers'] = new_value.pop('measurement_manager')
        _store_setting_value(bind, new_value)


def downgrade() -> None:
    """canonical → legacy 역변환 후 receipt 테이블·version 컬럼 제거(무손실)."""
    bind = op.get_bind()
    value = _load_setting_value(bind)
    if value is not None and isinstance(value.get('drawing_managers'), list):
        managers = value['drawing_managers']
        new_value = dict(value)
        new_value['drawing_manager'] = [
            str(m.get('name') or '').strip()
            for m in managers
            if isinstance(m, dict) and str(m.get('name') or '').strip()
        ]
        new_value['drawing_manager_en'] = {
            str(m.get('name') or '').strip(): str(m.get('english_name') or '').strip()
            for m in managers
            if isinstance(m, dict) and str(m.get('name') or '').strip()
            and str(m.get('english_name') or '').strip()
        }
        new_value.pop('drawing_managers', None)
        if 'measurement_managers' in new_value and 'measurement_manager' not in new_value:
            new_value['measurement_manager'] = new_value.pop('measurement_managers')
        _store_setting_value(bind, new_value)

    op.drop_index('ix_ssr_expires_id', table_name='system_setting_receipts')
    op.drop_index('ix_ssr_setting_key', table_name='system_setting_receipts')
    op.drop_table('system_setting_receipts')
    op.drop_column('system_settings', 'version')
