"""STARTUP-SCHEMA-01: ensure ERP flat columns / attachment columns / hot indexes

Revision ID: startup_schema_00
Revises: wdc_link_backfill_00
Create Date: 2026-07-26

§5.2 STARTUP-SCHEMA-01. 과거 web replica 는 부팅마다 runtime ensure-schema helper
(``ensure_order_attachments_*`` / ``ensure_erp_date_columns`` / ``apply_phase2_indexes``)를
호출해 ``ALTER TABLE ... ADD COLUMN`` 과 ``CREATE INDEX`` 를 실행했다. 다중 replica 가
같은 DDL 을 동시에 돌리며 락을 다투었고(비 CONCURRENTLY 인덱스는 ACCESS EXCLUSIVE),
스키마가 없어도 조용히 self-heal 하여 드리프트를 가렸다.

이 마이그레이션은 그 ensure-repair DDL 을 Alembic 로 이관한다: predeploy.sh 의
``alembic upgrade head`` 가 replica 부팅 **전에** 한 번 스키마를 확정하고, web startup 은
DDL 을 전혀 실행하지 않는다(fail-closed — 스키마가 없으면 앱이 조용히 만들지 않고 실패).

**순수 additive**: 컬럼/인덱스만 더한다. 모든 DDL 은 ``IF NOT EXISTS`` 로 멱등이며,
이미 존재하는 컬럼/인덱스(create_all 또는 phase_b/phase_d 등 선행 마이그레이션이 만든 것)에는
no-op 이다. 인덱스는 성능 가드(다중 replica·hot ``orders`` 테이블)에 따라 ``CONCURRENTLY``
로 만든다(migrations/env.py 의 세션 advisory lock 이 replica 간 동시 빌드를 직렬화).

DDL 은 기존 startup helper(``foms/api/files/legacy.py``·``foms/services/db_indexes.py``)와
1:1 로 대응한다 — 이관이지 스키마 신설이 아니다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'startup_schema_00'
down_revision: Union[str, None] = 'wdc_link_backfill_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 트랜잭션 내에서 실행되는 additive 컬럼 DDL (ADD COLUMN IF NOT EXISTS = 멱등).
# ``foms/api/files/legacy.py``(order_attachments) + ``foms/services/db_indexes.py``
# (orders erp flat columns)의 startup ensure DDL 과 1:1 대응.
_COLUMN_DDL: tuple[str, ...] = (
    "ALTER TABLE order_attachments ADD COLUMN IF NOT EXISTS "
    "category VARCHAR(50) NOT NULL DEFAULT 'measurement'",
    "ALTER TABLE order_attachments ADD COLUMN IF NOT EXISTS item_index INTEGER",
    "ALTER TABLE order_attachments ADD COLUMN IF NOT EXISTS "
    "user_id INTEGER REFERENCES users(id) ON DELETE SET NULL",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS erp_measurement_date VARCHAR(10)",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS erp_construction_date VARCHAR(10)",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS erp_stage_code VARCHAR(30)",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS erp_urgent BOOLEAN DEFAULT FALSE NOT NULL",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS erp_drawing_updated_at TIMESTAMP",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS erp_stage_updated_at TIMESTAMP",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS erp_owner_team_code VARCHAR(20)",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS erp_phone_digits VARCHAR(20)",
)

# CONCURRENTLY 로 만드는 인덱스 DDL (+ pg_trgm 확장). 각 문은 트랜잭션 밖에서 실행돼야 하며
# (``_run_concurrently`` 가 COMMIT 후 실행), IF NOT EXISTS 로 멱등. ``apply_phase2_indexes``
# / ``ensure_erp_date_columns`` 의 startup 인덱스 DDL 과 대응(비 CONCURRENTLY → CONCURRENTLY 승격).
_INDEX_DDL: tuple[str, ...] = (
    "CREATE EXTENSION IF NOT EXISTS pg_trgm",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_orders_erp_measurement_date "
    "ON orders (erp_measurement_date)",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_orders_erp_construction_date "
    "ON orders (erp_construction_date)",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_orders_erp_stage_code "
    "ON orders (erp_stage_code)",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_orders_erp_urgent "
    "ON orders (erp_urgent)",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_orders_erp_stage_updated_at "
    "ON orders (erp_stage_updated_at)",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_orders_erp_owner_team_code "
    "ON orders (erp_owner_team_code)",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_orders_erp_phone_digits "
    "ON orders (erp_phone_digits)",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_order_measure_date_trgm "
    "ON orders USING gin (measurement_date gin_trgm_ops)",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_order_schedule_date_trgm "
    "ON orders USING gin (scheduled_date gin_trgm_ops)",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_osd_measurement_date "
    "ON order_schedule_dates (date, order_id) WHERE kind = 'measurement'",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_osd_construction_date "
    "ON order_schedule_dates (date, order_id) WHERE kind = 'construction'",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_osd_as_visit_date "
    "ON order_schedule_dates (date, order_id) WHERE kind = 'as_visit'",
)


def _run_concurrently(conn, sql: str) -> None:
    """CONCURRENTLY DDL 은 트랜잭션 밖에서 실행 — 열린 트랜잭션을 COMMIT 후 실행.

    phase_c/phase_d 마이그레이션과 동일 패턴. env.py 의 세션 레벨 advisory lock 이
    내부 COMMIT 을 넘어 유지되므로 다중 replica 동시 인덱스 빌드가 직렬화된다.
    """
    conn.execute(sa.text("COMMIT"))
    conn.execute(sa.text(sql))


def upgrade() -> None:
    """ensure-repair 컬럼/인덱스를 멱등 additive 로 확정(존재하면 no-op)."""
    conn = op.get_bind()
    for statement in _COLUMN_DDL:
        conn.execute(sa.text(statement))
    for statement in _INDEX_DDL:
        _run_concurrently(conn, statement)


def downgrade() -> None:
    """no-op(의도적).

    additive expand 마이그레이션이다: 이 컬럼들에는 비정규화된 ERP 데이터가,
    인덱스에는 hot-path 조회가 의존한다. downgrade 에서 drop 하면 데이터 유실과
    값비싼 인덱스 재빌드를 유발하고, 애초에 이 객체 다수는 create_all/선행
    마이그레이션이 만든 것이라 이 마이그레이션의 소유가 아니다. 따라서 파괴적
    downgrade 를 명시적으로 거부한다(STARTUP-SCHEMA-01: additive downgrade destructive 금지).
    """
    pass
