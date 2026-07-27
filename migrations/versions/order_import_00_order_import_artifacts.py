"""ORDER-IMPORT-01: order_import_artifacts + outbox order_import_artifact_id FK

Revision ID: order_import_00
Revises: upload_02_00
Create Date: 2026-07-27

admin Excel import receipt/artifact 의 유일 스키마 변경이다. 단일 additive 마이그레이션 —
새 부모 테이블 ``order_import_artifacts`` 하나를 만들고, SIDEFX-00 이 남겨둔 8번째 도메인
(``source_domain=ORDER_IMPORT_ARTIFACT``)에 실 FK 를 부착한다(UPLOAD-02 upload_ticket_id
패턴 미러).

* ``order_import_artifacts`` — import receipt 행. ``id``·``uploaded_by``(users FK, SET
  NULL)·``file_hash``(재import 멱등의 정본)·``filename``·``row_count``·``state``(COMPLETED|
  FAILED|EXPIRED)·``source_object_key``/``error_object_key``(server-derived private key)·
  ``resource_order_ids``(JSONB resources[])·``created_at``·``expires_at``(created_at+24h).
  ``uq_order_import_artifact_hash`` 는 만료 전(state<>EXPIRED) 같은 hash 를 유일화하고
  ``ix_order_import_artifact_expiry`` 가 bounded cleanup provider 의 만료 claim hot path 다.
* ``domain_side_effect_outbox.order_import_artifact_id`` **컬럼 추가 + FK 부착** — SIDEFX-00
  계약이 예고한 8번째 도메인의 부모 테이블이 생겼으므로 실 FK 로 orphan 을 DB 가 거부한다.
  one-of matrix(``ck_dseo_source_one_of``)와 도메인 enum(``ck_dseo_source_domain``)을 8도메인
  버전으로 재작성한다(ORM ``models.DOMAIN_SIDE_EFFECT_ONE_OF_CHECK_SQL`` 과 SSOT 공유).

**경계(ORDER-IMPORT-01)**: 별도 scheduler/cleanup loop 를 만들지 않는다(만료 scan 은 SIDEFX
worker 300s expiry scan provider 가 호출). DDL 은 models.py ORM 정의와 SSOT 를 공유한다
(create_all 테스트 lane 동일 스키마).

``downgrade()`` 는 CHECK 를 7도메인으로 되돌리고 FK → 컬럼 → 인덱스 → 테이블을 생성 역순으로
제거한다(receipt 는 이력 행이라 무손실 역변환).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from models import DOMAIN_SIDE_EFFECT_FK_BY_DOMAIN, DOMAIN_SIDE_EFFECT_ONE_OF_CHECK_SQL

revision: str = 'order_import_00'
down_revision: Union[str, None] = 'upload_02_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _domain_in_sql(fk_by_domain: dict) -> str:
    """``source_domain IN (...)`` CHECK 식을 도메인 dict 로부터 만든다."""
    return "source_domain IN (" + ", ".join("'%s'" % d for d in fk_by_domain) + ")"


def _one_of_sql(fk_by_domain: dict) -> str:
    """exact one-of FK 매트릭스 CHECK 식을 도메인 dict 로부터 만든다(models 생성기와 동일 규칙)."""
    cols = list(fk_by_domain.values())
    clauses = []
    for domain, own in fk_by_domain.items():
        parts = ["source_domain = '%s'" % domain, "%s IS NOT NULL" % own]
        parts += ["%s IS NULL" % c for c in cols if c != own]
        clauses.append("(" + " AND ".join(parts) + ")")
    return " OR ".join(clauses)


#: ORDER_IMPORT_ARTIFACT 제거한 이전(7도메인) matrix — downgrade 복원용.
_PRIOR_FK_BY_DOMAIN = {
    k: v for k, v in DOMAIN_SIDE_EFFECT_FK_BY_DOMAIN.items()
    if k != 'ORDER_IMPORT_ARTIFACT'
}


def upgrade() -> None:
    """order_import_artifacts 생성 + outbox order_import_artifact_id 컬럼/FK/CHECK(8도메인)."""
    op.create_table(
        'order_import_artifacts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('uploaded_by', sa.Integer(),
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('file_hash', sa.String(64), nullable=False),
        sa.Column('filename', sa.String(255), nullable=True),
        sa.Column('row_count', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('state', sa.String(20), nullable=False, server_default='COMPLETED'),
        sa.Column('source_object_key', sa.String(500), nullable=True),
        sa.Column('error_object_key', sa.String(500), nullable=True),
        sa.Column('resource_order_ids', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "state IN ('COMPLETED','FAILED','EXPIRED')",
            name='ck_order_import_artifact_state'),
    )
    # file-hash receipt: 만료 전 같은 hash 유일화(재import 멱등의 DB backstop).
    op.create_index('uq_order_import_artifact_hash', 'order_import_artifacts',
                    ['file_hash'], unique=True,
                    postgresql_where=sa.text("state <> 'EXPIRED'"))
    # bounded cleanup provider 의 만료 claim hot path.
    op.create_index('ix_order_import_artifact_expiry', 'order_import_artifacts',
                    ['state', 'expires_at'])

    # 8번째 도메인 컬럼 추가 + 실 FK(부모 생성 후 orphan 거부).
    op.add_column('domain_side_effect_outbox',
                  sa.Column('order_import_artifact_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_dseo_order_import_artifact', 'domain_side_effect_outbox',
        'order_import_artifacts', ['order_import_artifact_id'], ['id'],
        ondelete='CASCADE',
    )
    # 도메인 enum·one-of matrix 를 8도메인으로 재작성(ORM 과 SSOT 공유).
    op.drop_constraint('ck_dseo_source_domain', 'domain_side_effect_outbox',
                       type_='check')
    op.create_check_constraint(
        'ck_dseo_source_domain', 'domain_side_effect_outbox',
        _domain_in_sql(DOMAIN_SIDE_EFFECT_FK_BY_DOMAIN))
    op.drop_constraint('ck_dseo_source_one_of', 'domain_side_effect_outbox',
                       type_='check')
    op.create_check_constraint(
        'ck_dseo_source_one_of', 'domain_side_effect_outbox',
        DOMAIN_SIDE_EFFECT_ONE_OF_CHECK_SQL)


def downgrade() -> None:
    """CHECK 를 7도메인으로 복원하고 FK → 컬럼 → 인덱스 → 테이블 제거."""
    op.drop_constraint('ck_dseo_source_one_of', 'domain_side_effect_outbox',
                       type_='check')
    op.create_check_constraint(
        'ck_dseo_source_one_of', 'domain_side_effect_outbox',
        _one_of_sql(_PRIOR_FK_BY_DOMAIN))
    op.drop_constraint('ck_dseo_source_domain', 'domain_side_effect_outbox',
                       type_='check')
    op.create_check_constraint(
        'ck_dseo_source_domain', 'domain_side_effect_outbox',
        _domain_in_sql(_PRIOR_FK_BY_DOMAIN))
    op.drop_constraint('fk_dseo_order_import_artifact', 'domain_side_effect_outbox',
                       type_='foreignkey')
    op.drop_column('domain_side_effect_outbox', 'order_import_artifact_id')
    op.drop_index('ix_order_import_artifact_expiry',
                  table_name='order_import_artifacts')
    op.drop_index('uq_order_import_artifact_hash',
                  table_name='order_import_artifacts')
    op.drop_table('order_import_artifacts')
