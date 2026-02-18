"""WSGI 기동 시 DB 자동 초기화 (app.py에서 분리)."""
from db import init_db, get_db
from wdcalculator_db import init_wdcalculator_db
from models import User
from werkzeug.security import generate_password_hash


def run_auto_init(app):
    """DB 테이블 및 admin 사용자 확인/생성. WSGI 서버(gunicorn 등)에서 app import 시 호출."""
    try:
        with app.app_context():
            print("[AUTO-INIT] Checking database tables...")
            init_db()
            from apps.api.attachments import (
                ensure_order_attachments_category_column,
                ensure_order_attachments_item_index_column,
            )
            ensure_order_attachments_category_column()
            ensure_order_attachments_item_index_column()
            init_wdcalculator_db()
            print("[AUTO-INIT] Tables checked/created successfully.")

            db_session = get_db()
            try:
                admin = db_session.query(User).filter_by(username='admin').first()
                if not admin:
                    print("[AUTO-INIT] Creating default admin user (admin/admin1234)...")
                    new_admin = User(
                        username='admin',
                        password=generate_password_hash('admin1234'),
                        name='관리자',
                        role='ADMIN',
                        is_active=True
                    )
                    db_session.add(new_admin)
                    db_session.commit()
                else:
                    print("[AUTO-INIT] Admin user exists.")
            except Exception as e:
                print(f"[AUTO-INIT] Failed to create admin user: {e}")
                db_session.rollback()
    except Exception as e:
        print(f"[AUTO-INIT] Database initialization failed: {e}")
