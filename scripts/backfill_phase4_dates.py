import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from db import get_db
from models import Order, OrderScheduleDate
from services.order_date_sync import sync_order_dates

def backfill_phase4_dates():
    with app.app_context():
        db = get_db()
        
        try:
            print("Starting backfill for OrderScheduleDate...")
            # Delete all existing data
            db.query(OrderScheduleDate).delete()
            db.commit()
            
            # Fetch orders in chunks to avoid cursor invalidation on commit
            orders = db.query(Order).all()
            
            count = 0
            for order in orders:
                sync_order_dates(order, db)
                count += 1
                if count % 100 == 0:
                    db.commit()
                    print(f"Processed {count} orders...")
            
            db.commit()
            print(f"Finished backfilling. Total {count} orders processed.")
            
            # Verify records
            m_count = db.query(OrderScheduleDate).filter_by(kind='measurement').count()
            c_count = db.query(OrderScheduleDate).filter_by(kind='construction').count()
            print(f"Total measurement dates added: {m_count}")
            print(f"Total construction dates added: {c_count}")
            
        except Exception as e:
            db.rollback()
            print(f"Backfill error: {e}")

if __name__ == '__main__':
    backfill_phase4_dates()
