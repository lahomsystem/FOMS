import logging
import re
from sqlalchemy import text
from db import get_db

_log = logging.getLogger(__name__)

def apply_phase2_indexes() -> None:
    """Phase 2~4 partial/trigram 인덱스를 안전하게 적용한다. app_init에서 호출.

    주의: orders 테이블의 partial index (is_regional, is_self_measurement, is_erp_beta)는
    models.py __table_args__에서 Alembic으로 관리하므로 여기서 중복 생성하지 않는다.
    이 함수는 models.py에서 선언할 수 없는 DB 전용 인덱스(trigram, OrderScheduleDate)만 담당한다.
    """
    db = get_db()

    try:
        db.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm;"))
        db.commit()
        _log.info("[AUTO-INIT] pg_trgm extension verified.")
        
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_order_measure_date_trgm ON orders USING gin (measurement_date gin_trgm_ops);"))
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_order_schedule_date_trgm ON orders USING gin (scheduled_date gin_trgm_ops);"))
        db.commit()
        _log.info("[AUTO-INIT] Phase 2: Trigram Indexes verified/created successfully.")
    except Exception as e:
        db.rollback()
        _log.warning("[AUTO-INIT] Warning: Could not create trigram indexes (or pg_trgm not supported): %s", e, exc_info=True)

    try:
        # OrderScheduleDate Partial Index (날짜 기반 대시보드 JOIN 속도 향상)
        # models.py의 idx_order_schedule_dates_composite (kind, date, order_id)와 달리
        # 특정 kind 값으로 필터링한 부분 인덱스로 더 작고 빠름
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_osd_measurement_date
            ON order_schedule_dates (date, order_id)
            WHERE kind = 'measurement';
        """))
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_osd_construction_date
            ON order_schedule_dates (date, order_id)
            WHERE kind = 'construction';
        """))
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_osd_as_visit_date
            ON order_schedule_dates (date, order_id)
            WHERE kind = 'as_visit';
        """))
        db.commit()
        _log.info("[AUTO-INIT] Phase 4: OrderScheduleDate Partial Indexes verified/created successfully.")
    except Exception as e:
        db.rollback()
        _log.warning("[AUTO-INIT] Warning: Could not create OrderScheduleDate partial indexes: %s", e, exc_info=True)

def ensure_erp_date_columns():
    """Phase B & D: 대용량 데이터 필터/페이징을 위한 정규화 컬럼 추가."""
    db = get_db()
    try:
        # Phase B columns
        db.execute(text('ALTER TABLE orders ADD COLUMN IF NOT EXISTS erp_measurement_date VARCHAR(10)'))
        db.execute(text('ALTER TABLE orders ADD COLUMN IF NOT EXISTS erp_construction_date VARCHAR(10)'))
        db.execute(text('CREATE INDEX IF NOT EXISTS ix_orders_erp_measurement_date ON orders (erp_measurement_date)'))
        db.execute(text('CREATE INDEX IF NOT EXISTS ix_orders_erp_construction_date ON orders (erp_construction_date)'))
        
        # Phase D flat columns
        db.execute(text('ALTER TABLE orders ADD COLUMN IF NOT EXISTS erp_stage_code VARCHAR(30)'))
        db.execute(text('ALTER TABLE orders ADD COLUMN IF NOT EXISTS erp_urgent BOOLEAN DEFAULT FALSE NOT NULL'))
        db.execute(text('ALTER TABLE orders ADD COLUMN IF NOT EXISTS erp_drawing_updated_at TIMESTAMP'))
        db.execute(text('ALTER TABLE orders ADD COLUMN IF NOT EXISTS erp_owner_team_code VARCHAR(20)'))
        
        db.execute(text('CREATE INDEX IF NOT EXISTS ix_orders_erp_stage_code ON orders (erp_stage_code)'))
        db.execute(text('CREATE INDEX IF NOT EXISTS ix_orders_erp_urgent ON orders (erp_urgent)'))
        db.execute(text('CREATE INDEX IF NOT EXISTS ix_orders_erp_owner_team_code ON orders (erp_owner_team_code)'))
        
        db.commit()
        _log.info("[AUTO-INIT] Phase B & D flat columns verified.")
    except Exception as e:
        db.rollback()
        _log.warning("[AUTO-INIT] Failed to add erp_date/flat columns: %s", e)
