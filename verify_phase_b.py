import datetime
from app import app
from db import get_db
from models import Order
from services.erp_display import _normalize_date_to_yyyymmdd, _erp_alerts
from sqlalchemy import cast, String

def verify_backfill(db):
    orders = db.query(Order).filter(Order.active_filter(), Order.is_erp_beta.is_(True)).all()
    mismatches = []
    for o in orders:
        sd = o.structured_data or {}
        expected_meas = _normalize_date_to_yyyymmdd(((sd.get('schedule') or {}).get('measurement') or {}).get('date'))
        expected_cons = _normalize_date_to_yyyymmdd(((sd.get('schedule') or {}).get('construction') or {}).get('date'))
        if o.erp_measurement_date != expected_meas or o.erp_construction_date != expected_cons:
            mismatches.append(o.id)
    assert len(mismatches) == 0, f"동기화 불일치 {len(mismatches)}건: {mismatches[:10]}"
    print("Backfill verification passed.")

def verify_filters(db):
    today_date = datetime.date.today()
    stage_col = cast(Order.structured_data['workflow']['stage'], String)
    
    # measurement_d4
    cutoff_meas = (today_date + datetime.timedelta(days=12)).isoformat()
    sql_candidates_meas = db.query(Order).filter(
        Order.active_filter(), Order.is_erp_beta.is_(True),
        Order.erp_measurement_date.isnot(None),
        Order.erp_measurement_date >= today_date.isoformat(),
        Order.erp_measurement_date <= cutoff_meas
    ).all()
    
    # memory
    all_orders = db.query(Order).filter(Order.active_filter(), Order.is_erp_beta.is_(True)).all()
    memory_meas = [o for o in all_orders if _erp_alerts(o, o.structured_data or {}, 0).get('measurement_d4')]
    
    # check that all memory_meas are in sql_candidates_meas
    candidate_ids_meas = {o.id for o in sql_candidates_meas}
    missing_meas = [o.id for o in memory_meas if o.id not in candidate_ids_meas]
    assert len(missing_meas) == 0, f"measurement_d4 SQL 누락: {missing_meas}"
    
    # construction_d3
    cutoff_cons = (today_date + datetime.timedelta(days=10)).isoformat()
    sql_candidates_cons = db.query(Order).filter(
        Order.active_filter(), Order.is_erp_beta.is_(True),
        Order.erp_construction_date.isnot(None),
        Order.erp_construction_date >= today_date.isoformat(),
        Order.erp_construction_date <= cutoff_cons
    ).all()
    
    memory_cons = [o for o in all_orders if _erp_alerts(o, o.structured_data or {}, 0).get('construction_d3')]
    candidate_ids_cons = {o.id for o in sql_candidates_cons}
    missing_cons = [o.id for o in memory_cons if o.id not in candidate_ids_cons]
    assert len(missing_cons) == 0, f"construction_d3 SQL 누락: {missing_cons}"

    # production_d2
    cutoff_prod = (today_date + datetime.timedelta(days=8)).isoformat()
    sql_candidates_prod = db.query(Order).filter(
        Order.active_filter(), Order.is_erp_beta.is_(True),
        Order.erp_construction_date.isnot(None),
        Order.erp_construction_date >= today_date.isoformat(),
        Order.erp_construction_date <= cutoff_prod,
        stage_col.notin_(['"CONSTRUCTION"'])
    ).all()
    
    memory_prod = [o for o in all_orders if _erp_alerts(o, o.structured_data or {}, 0).get('production_d2')]
    candidate_ids_prod = {o.id for o in sql_candidates_prod}
    missing_prod = [o.id for o in memory_prod if o.id not in candidate_ids_prod]
    assert len(missing_prod) == 0, f"production_d2 SQL 누락: {missing_prod}"

    print(f"Filter verification passed. (meas_d4: {len(memory_meas)} in {len(sql_candidates_meas)} candidates, cons_d3: {len(memory_cons)} in {len(sql_candidates_cons)} candidates, prod_d2: {len(memory_prod)} in {len(sql_candidates_prod)} candidates)")

with app.app_context():
    db = get_db()
    verify_backfill(db)
    verify_filters(db)