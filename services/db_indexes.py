from sqlalchemy import text
from db import get_db

def apply_phase2_indexes():
    """Apply Phase 2 partial and trigram indexes safely. To be called in app_init."""
    db = get_db()
    try:
        # 1. 지방 대시보드용
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_order_regional ON orders(id DESC) WHERE status <> 'DELETED' AND deleted_at IS NULL AND is_regional = true;"))
        # 2. 자가실측 대시보드용
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_order_self_measurement ON orders(id DESC) WHERE status <> 'DELETED' AND deleted_at IS NULL AND is_self_measurement = true;"))
        # 3. ERP Beta 활성 주문용
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_order_erp_beta ON orders(id DESC) WHERE status <> 'DELETED' AND deleted_at IS NULL AND is_erp_beta = true;"))
        db.commit()
        print("[AUTO-INIT] Phase 2: Partial Indexes verified/created successfully.")
    except Exception as e:
        db.rollback()
        print(f"[AUTO-INIT] Warning: Could not create partial indexes: {e}")

    try:
        db.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm;"))
        db.commit()
        print("[AUTO-INIT] pg_trgm extension verified.")
        
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_order_measure_date_trgm ON orders USING gin (measurement_date gin_trgm_ops);"))
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_order_schedule_date_trgm ON orders USING gin (scheduled_date gin_trgm_ops);"))
        db.commit()
        print("[AUTO-INIT] Phase 2: Trigram Indexes verified/created successfully.")
    except Exception as e:
        db.rollback()
        print(f"[AUTO-INIT] Warning: Could not create trigram indexes (or pg_trgm not supported): {e}")
