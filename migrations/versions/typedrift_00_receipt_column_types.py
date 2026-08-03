"""TYPEDRIFT-00: receipt/heartbeat 컬럼 타입을 models.py 선언과 일치시킨다

Revision ID: typedrift_00
Revises: wiz_pending_00
Create Date: 2026-08-03

MIGCHAIN-01(``tests/postgres/test_migration_chain.py``)이 신설되면서 처음으로
"create_all 이 만드는 스키마"와 "마이그레이션이 만드는 스키마"를 컬럼 단위로 대조했고,
세 컬럼이 어긋나 있었다. 원인은 데이터가 아니라 **마이그레이션 작성 실수**다:

* ``system_setting_receipts.read_receipt_id`` — models.py 는 ``UUIDColumn``
  (= ``postgresql.UUID``)인데 ``shipment_reference_00`` 이 ``sa.String(36)`` 으로 만들었다.
* ``system_setting_receipts.response_body`` — models.py 는 ``JSONColumn``
  (= PostgreSQL 에서 ``JSONB``)인데 같은 마이그레이션이 ``sa.JSON()`` 으로 만들었다.
* ``channel_inbound_worker_heartbeats.metadata_json`` — 같은 이유로 ``channel_inbound_00``
  이 ``sa.JSON()`` 으로 만들었다.

같은 역할의 형제 테이블 ``order_mutation_receipts`` 는 ``rev_00_order_mutation`` 에서
``postgresql.UUID`` / ``postgresql.JSONB`` 로 **정확히** 만들어져 있다(운영 실측 확인:
uuid / jsonb). 즉 의도는 처음부터 uuid·jsonb 였고 위 두 마이그레이션만 빠뜨렸다.

기존 레인이 못 잡은 이유: SQLite 레인은 타입 구분이 없고, PG 레인은 ``create_all``
(= ORM 타입)로 부트스트랩하므로 **양쪽 다 jsonb 만 본다**. 마이그레이션을 실제로 돌리는
경로는 predeploy 와 MIGCHAIN-01 뿐이다.

영향 범위: 두 컬럼 모두 whole-row read/write 만 하고 JSONB 전용 연산자(``@>``·``?``·
GIN 인덱스)를 쓰는 코드는 0건이라 현재 기능 결함은 없다. 위험은 앞으로다 — models.py 가
jsonb 라고 선언하므로 누군가 jsonb 연산자를 쓰면 두 테스트 레인은 모두 통과하고 운영에서만
깨진다. 그 함정을 없애는 것이 이 마이그레이션의 목적이다.

비용: 운영 실측 결과 두 테이블 모두 **0행**(48kB / 16kB)이라 ``ALTER TYPE`` 재작성 비용이
사실상 없다. ``read_receipt_id`` 는 ``str(uuid.uuid4())`` 로만 채워지므로 ``::uuid`` 캐스트가
항상 성립한다.

UNIQUE 제약 이름도 함께 맞춘다. 기능은 같지만 ``shipment_reference_00`` 이
``uq_system_setting_receipt_read_id`` 로 명명해 create_all 의 기본 이름
(``system_setting_receipts_read_receipt_id_key``)과 달랐고, MIGCHAIN-01 이 이것도 알려진
드리프트로 고정하고 있었다.

``downgrade()`` 는 세 컬럼을 원래 타입으로 되돌리고 제약 이름도 되돌린다(무손실 역변환 —
json/varchar 는 jsonb/uuid 의 상위 집합 표현이다).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "typedrift_00"
down_revision: Union[str, None] = "wiz_pending_00"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """세 컬럼을 uuid/jsonb 로 올리고 UNIQUE 제약 이름을 create_all 기본값에 맞춘다."""
    op.alter_column(
        "system_setting_receipts",
        "read_receipt_id",
        type_=postgresql.UUID(as_uuid=False),
        postgresql_using="read_receipt_id::uuid",
        existing_type=sa.String(36),
        existing_nullable=False,
    )
    op.alter_column(
        "system_setting_receipts",
        "response_body",
        type_=postgresql.JSONB(),
        postgresql_using="response_body::jsonb",
        existing_type=sa.JSON(),
        existing_nullable=False,
    )
    op.alter_column(
        "channel_inbound_worker_heartbeats",
        "metadata_json",
        type_=postgresql.JSONB(),
        postgresql_using="metadata_json::jsonb",
        existing_type=sa.JSON(),
        existing_nullable=True,
    )
    op.execute(
        "ALTER TABLE system_setting_receipts "
        "RENAME CONSTRAINT uq_system_setting_receipt_read_id "
        "TO system_setting_receipts_read_receipt_id_key"
    )


def downgrade() -> None:
    """제약 이름과 세 컬럼 타입을 마이그레이션 원본 상태로 되돌린다."""
    op.execute(
        "ALTER TABLE system_setting_receipts "
        "RENAME CONSTRAINT system_setting_receipts_read_receipt_id_key "
        "TO uq_system_setting_receipt_read_id"
    )
    op.alter_column(
        "channel_inbound_worker_heartbeats",
        "metadata_json",
        type_=sa.JSON(),
        postgresql_using="metadata_json::json",
        existing_type=postgresql.JSONB(),
        existing_nullable=True,
    )
    op.alter_column(
        "system_setting_receipts",
        "response_body",
        type_=sa.JSON(),
        postgresql_using="response_body::json",
        existing_type=postgresql.JSONB(),
        existing_nullable=False,
    )
    op.alter_column(
        "system_setting_receipts",
        "read_receipt_id",
        type_=sa.String(36),
        postgresql_using="read_receipt_id::text",
        existing_type=postgresql.UUID(as_uuid=False),
        existing_nullable=False,
    )
