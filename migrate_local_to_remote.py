import os
import sys
import io
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
import datetime

# Ensure clean UTF-8 output for Windows console
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 1. Local Database Connection (SQLite)
LOCAL_DB_URL = 'sqlite:///furniture_orders.db'
local_engine = create_engine(LOCAL_DB_URL, echo=False)
LocalSession = sessionmaker(bind=local_engine)

# 2. Remote Database Connection (Postgres)
REMOTE_DB_URL = os.environ.get('DATABASE_URL')

if not REMOTE_DB_URL:
    print("[ERROR] DATABASE_URL environment variable is missing.")
    print("Please run this script using: railway run python migrate_local_to_remote.py")
    sys.exit(1)

# Normalize Postgres URL
if REMOTE_DB_URL.startswith("postgres://"):
    REMOTE_DB_URL = REMOTE_DB_URL.replace("postgres://", "postgresql://", 1)

remote_engine = create_engine(REMOTE_DB_URL, echo=False)
RemoteSession = sessionmaker(bind=remote_engine)

def migrate_users():
    local_session = LocalSession()
    remote_session = RemoteSession()
    
    try:
        from models import User
        print("[MIGRATION] Migrating Users...")
        
        # Adjust table name matching if needed. 
        # Assuming identical model structure since code is same.
        
        users = local_session.query(User).all()
        count = 0
        for local_user in users:
            # Check if exists
            existing = remote_session.query(User).filter_by(username=local_user.username).first()
            if existing:
                print(f"  - Skipping existing user: {local_user.username}")
                continue
                
            # Create new remote user
            # We need to detach the object from local session or create a new instance
            new_user = User(
                username=local_user.username,
                password=local_user.password, # Password hash is already a string
                name=local_user.name,
                role=local_user.role,
                is_active=local_user.is_active,
                created_at=local_user.created_at,
                last_login=local_user.last_login
            )
            remote_session.add(new_user)
            count += 1
            
        remote_session.commit()
        print(f"[SUCCESS] Migrated {count} users.")
        
    except Exception as e:
        print(f"[ERROR] User migration failed: {e}")
        remote_session.rollback()
    finally:
        local_session.close()
        remote_session.close()

def migrate_orders():
    local_session = LocalSession()
    remote_session = RemoteSession()
    
    try:
        from models import Order
        print("[MIGRATION] Migrating Orders...")
        
        orders = local_session.query(Order).all()
        count = 0
        for local_order in orders:
            # Simple check by ID might conflict if sequences differ, 
            # but for restoration, preserving ID is ideal if remote is empty.
            # If remote already has data, IDs might clash.
            
            existing = remote_session.query(Order).get(local_order.id)
            if existing:
                print(f"  - Skipping existing order ID: {local_order.id}")
                continue
                
            remote_session.merge(local_order) # Merge handles copying attributes
            count += 1
            
        remote_session.commit()
        print(f"[SUCCESS] Migrated {count} orders.")
        
    except Exception as e:
        print(f"[ERROR] Order migration failed: {e}")
        remote_session.rollback()
    finally:
        local_session.close()
        remote_session.close()

def main():
    print("="*60)
    print(" FOMS Data Migration: Local (SQLite) -> Remote (Postgres)")
    print("="*60)
    print(f"Local DB: {LOCAL_DB_URL}")
    print(f"Remote DB: (from env)")
    
    # Verify connection
    try:
        with remote_engine.connect() as conn:
            pass
        print("[INFO] Remote connection successful.")
    except Exception as e:
        print(f"[ERROR] Could not connect to remote DB: {e}")
        return

    migrate_users()
    migrate_orders()
    
    print("\n[DONE] Migration completed.")

if __name__ == "__main__":
    main()
