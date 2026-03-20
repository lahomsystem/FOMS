from app import app
from db import get_db
from models import Order
from sqlalchemy import cast, String

with app.app_context():
    db = get_db()
    
    # 1. SQL 필터 결과
    sql_result = db.query(Order).filter(
        Order.active_filter(),
        Order.is_erp_beta.is_(True),
        cast(Order.structured_data['workflow']['stage'], String).in_(['"실측"', '"MEASURE"'])
    ).count()

    # 2. Memory 필터 결과 (기존 방식)
    from services.erp_display import _erp_get_stage
    all_orders = db.query(Order).filter(Order.active_filter(), Order.is_erp_beta.is_(True)).all()
    memory_result = sum(1 for o in all_orders if _erp_get_stage(o, o.structured_data or {}) in ('실측', 'MEASURE'))
    
    print(f"SQL result: {sql_result}")
    print(f"Memory result: {memory_result}")
    
    assert sql_result == memory_result, f"불일치: SQL={sql_result}, Memory={memory_result}"
    print("Phase A validation passed.")
