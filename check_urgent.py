from app import app
from db import get_db
from sqlalchemy import text

with app.app_context():
    db = get_db()
    res = db.execute(text("SELECT DISTINCT structured_data->'flags'->>'urgent' FROM orders WHERE is_erp_beta = TRUE")).fetchall()
    print("Urgent values:", [r[0] for r in res])
