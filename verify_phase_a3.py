from app import app
from db import get_db
from models import Order
from sqlalchemy import cast, String

with app.app_context():
    db = get_db()
    
    # Check construction page SQL
    q = db.query(Order).filter(Order.active_filter(), Order.is_erp_beta.is_(True))
    stage_col = cast(Order.structured_data['workflow']['stage'], String)
    q = q.filter(stage_col.in_(['"CONSTRUCTION"', '"시공"', '"CONSTRUCTING"']))
    
    print(f"Construction sql_result: {q.count()}")
    
    # Check KPI row loading
    kpi_rows = db.query(Order).filter(Order.active_filter(), Order.is_erp_beta.is_(True)).order_by(None).with_entities(Order.id, Order.is_self_measurement).limit(5).all()
    print("KPI rows test:", kpi_rows)
