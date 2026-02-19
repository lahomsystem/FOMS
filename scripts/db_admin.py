"""FOMS DB 관리 스크립트. 비밀번호는 환경변수 FOMS_ADMIN_DEFAULT_PASSWORD 사용 (미설정 시 기본값)."""
import sys
import os
import argparse
from sqlalchemy import text

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# 프로덕션에서는 반드시 FOMS_ADMIN_DEFAULT_PASSWORD 설정 권장 (NEXT-004)
def _default_admin_password():
    return os.environ.get('FOMS_ADMIN_DEFAULT_PASSWORD', 'admin1234')

from db import db_session, engine, init_db
try:
    from wdcalculator_db import init_wdcalculator_db, get_wdcalculator_db
except ImportError:
    init_wdcalculator_db = None
    get_wdcalculator_db = None

def fix_sequences():
    if engine.dialect.name != 'postgresql':
        print(f"Skipping sequence fix: Database is {engine.dialect.name}, not postgresql.")
        return

    print("Fixing DB sequences...")
    try:
        session = db_session()
        tables = [
            'users', 'orders', 'access_logs', 'security_logs', 
            'chat_rooms', 'chat_messages', 'chat_room_members', 'chat_attachments',
            'order_events', 'order_tasks', 'order_attachments'
        ]
        results = []
        for table in tables:
            try:
                sql = text(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), coalesce(max(id), 1), true) FROM {table}")
                session.execute(sql)
                print(f"Fixed {table}")
            except Exception as e:
                print(f"Error {table}: {e}")
        
        # WDCalculator tables
        if get_wdcalculator_db:
            try:
                wd_tables = ['estimates', 'estimate_histories', 'estimate_order_matches']
                wd_db = get_wdcalculator_db()
                for table in wd_tables:
                    try:
                        sql = text(f"SELECT setval(pg_get_serial_sequence('wdcalculator.{table}', 'id'), coalesce(max(id), 1), true) FROM wdcalculator.{table}")
                        wd_db.execute(sql)
                        print(f"Fixed wdcalculator.{table}")
                    except Exception as e:
                        print(f"Error wd.{table}: {e}")
                wd_db.commit()
            except Exception as e:
                 print(f"WD DB Error: {e}")
        
        session.commit()
        print("Sequence fix completed.")
    except Exception as e:
        print(f"Fatal Error: {e}")
    finally:
        session.close()

def optimize_db():
    print("Optimizing DB (creating indexes)...")
    try:
        session = db_session()
        indexes = [
            # (Index Name, Table, Column)
            ('ix_orders_customer_name', 'orders', 'customer_name'),
            ('ix_orders_phone', 'orders', 'phone'),
            ('ix_orders_status', 'orders', 'status'),
            ('ix_order_attachments_order_id', 'order_attachments', 'order_id')
        ]
        
        for idx_name, table, col in indexes:
            # PostgreSQL specific syntax for safe index creation
            if engine.dialect.name == 'postgresql':
                sql = f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table} ({col});"
            else:
                # SQLite doesn't support IF NOT EXISTS in all versions, but Standard SQL:
                sql = f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table} ({col});"
            
            try:
                session.execute(text(sql))
                print(f"Checked/Created index: {idx_name}")
            except Exception as e:
                print(f"Skipped index {idx_name}: {e}")
            
        session.commit()
        print("Optimization completed.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        session.close()

def init_tables():
    print("Initializing tables...")
    try:
        init_db()
        if init_wdcalculator_db:
            print("Initializing WDCalculator DB...")
            init_wdcalculator_db()
            
        # Create Default Admin
        from models import User
        from werkzeug.security import generate_password_hash
        session = db_session()
        try:
            admin = session.query(User).filter_by(username='admin').first()
            if not admin:
                pwd = _default_admin_password()
                print("Creating default admin user (admin/***)...")
                new_admin = User(
                    username='admin',
                    password=generate_password_hash(pwd),
                    name='관리자',
                    role='ADMIN',
                    is_active=True
                )
                session.add(new_admin)
                session.commit()
                print("Default admin created.")
            else:
                print("Admin user already exists.")
        except Exception as e:
            print(f"Admin creation error: {e}")
            session.rollback()
        finally:
            session.close()
            
        print("Tables initialization completed.")
    except Exception as e:
        print(f"Initialization Error: {e}")


def reset_admin_password(password=None):
    """
    admin 계정 비밀번호를 Werkzeug pbkdf2 해시로 갱신.
    DB에 bcrypt($2b$) 등 다른 형식으로 저장된 경우 로그인이 되지 않을 수 있어 이 스크립트로 복구.
    password 미지정 시 FOMS_ADMIN_DEFAULT_PASSWORD 환경변수 또는 기본값 사용.
    """
    if password is None:
        password = _default_admin_password()
    from models import User
    from werkzeug.security import generate_password_hash
    session = db_session()
    try:
        admin = session.query(User).filter_by(username='admin').first()
        if not admin:
            print("Admin user not found. Creating admin (admin/{})...".format(password))
            admin = User(
                username='admin',
                password=generate_password_hash(password),
                name='관리자',
                role='ADMIN',
                is_active=True
            )
            session.add(admin)
        else:
            admin.password = generate_password_hash(password)
            print("Admin password updated (username=admin, password={}).".format(password))
        session.commit()
        print("Done. You can log in with admin / {}.".format(password))
    except Exception as e:
        print(f"Error: {e}")
        session.rollback()
    finally:
        session.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="FOMS Database Administration Tool")
    parser.add_argument('action', choices=['fix-sequences', 'optimize', 'init', 'reset-admin'], help="Action to perform")
    parser.add_argument('--password', default=None, help="New password for reset-admin (default: FOMS_ADMIN_DEFAULT_PASSWORD env or fallback)")
    args = parser.parse_args()
    
    if args.action == 'fix-sequences':
        fix_sequences()
    elif args.action == 'optimize':
        optimize_db()
    elif args.action == 'init':
        init_tables()
    elif args.action == 'reset-admin':
        reset_admin_password(password=args.password)