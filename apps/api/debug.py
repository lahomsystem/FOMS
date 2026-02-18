"""디버그용 API (DB 연결 확인 등)."""
import os
from flask import Blueprint, jsonify
from db import get_db
from models import User

debug_bp = Blueprint('debug', __name__)


@debug_bp.route('/debug-db')
def debug_db():
    """Database Connection Check Route (Temporary)."""
    try:
        from sqlalchemy import text
        db = get_db()
        result = db.execute(text("SELECT 1")).fetchone()
        tables_query = text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
        tables = [row[0] for row in db.execute(tables_query).fetchall()]
        status = "SUCCESS"
        message = f"Connected! Result: {result}, Tables: {tables}"
        if 'users' in tables:
            message += f" | Users count: {db.query(User).count()}"
        else:
            status = "WARNING"
            message += " | 'users' table MISSING"
        return jsonify({"status": status, "message": message, "env_db_url_set": bool(os.environ.get('DATABASE_URL'))})
    except Exception as e:
        import traceback
        return jsonify({"status": "ERROR", "error": str(e), "traceback": traceback.format_exc()}), 500
