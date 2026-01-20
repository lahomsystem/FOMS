from app import app
from db import get_db
from sqlalchemy import text
from pprint import pprint

with app.app_context():
    db = get_db()
    pprint(db.execute(text("SELECT step_key, status, started_at, completed_at FROM system_build_steps ORDER BY step_key")).fetchall())

