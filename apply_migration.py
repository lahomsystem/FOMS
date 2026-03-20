from app import app
from db import get_db
from sqlalchemy import text

with app.app_context():
    db = get_db()
    db.execute(text('ALTER TABLE orders ADD COLUMN IF NOT EXISTS erp_measurement_date VARCHAR(10)'))
    db.execute(text('ALTER TABLE orders ADD COLUMN IF NOT EXISTS erp_construction_date VARCHAR(10)'))
    db.execute(text('CREATE INDEX IF NOT EXISTS ix_orders_erp_measurement_date ON orders (erp_measurement_date)'))
    db.execute(text('CREATE INDEX IF NOT EXISTS ix_orders_erp_construction_date ON orders (erp_construction_date)'))
    db.commit()
    print("Columns and indexes added successfully.")