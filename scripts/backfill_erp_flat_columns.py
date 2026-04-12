import sys
import os

sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), '..')))

from app import app
from db import get_db
from models import Order
from foms.services.erp_sync_columns import sync_erp_flat_columns

def run_backfill():
    with app.app_context():
        db = get_db()
        # ERP Beta 활성 주문들만 가져와서 백필 수행
        orders = db.query(Order).filter(Order.active_filter(), Order.is_erp_beta.is_(True)).all()
        
        count = 0
        for order in orders:
            if order.structured_data:
                sync_erp_flat_columns(order, order.structured_data)
                count += 1
        
        db.commit()
        print(f"Backfill completed for {count} orders.")

if __name__ == '__main__':
    run_backfill()