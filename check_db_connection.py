import os
import sys
import psycopg2
from sqlalchemy import create_engine, text

def check_connection():
    print("="*60)
    print("DATA BASE CONNECTION CHECK")
    print("="*60)

    # 1. Environment Variable Check
    db_url = os.getenv("DATABASE_URL")
    print(f"[ENV] DATABASE_URL: {'SET' if db_url else 'NOT SET'}")
    
    if not db_url:
        print("[ERROR] DATABASE_URL environment variable is missing.")
        sys.exit(1)

    # Normalize URL if needed (handle postgres:// -> postgresql://)
    if db_url.startswith("postgres://"):
        db_url = "postgresql://" + db_url[len("postgres://"):]
        print("[INFO] Normalized 'postgres://' to 'postgresql://'")

    # 2. SQLAlchemy Connection Check
    print(f"[INFO] Attempting SQLAlchemy connection...")
    try:
        engine = create_engine(db_url, connect_args={"client_encoding": "utf8"}, pool_pre_ping=True)
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1"))
            print(f"[SUCCESS] SQLAlchemy Connection Successful! Result: {result.fetchone()}")
            
            # Check if tables exist
            result = connection.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'"))
            tables = [row[0] for row in result.fetchall()]
            print(f"[INFO] Found Tables ({len(tables)}): {', '.join(tables)}")
            
            if 'users' not in tables:
                print("[WARNING] 'users' table NOT found. Database might be empty. Please run migration.")
                with open("status.txt", "w", encoding="utf-8") as f:
                    f.write("MISSING: Users table not found")
            else:
                print("[INFO] 'users' table found.")
                with open("status.txt", "w", encoding="utf-8") as f:
                    f.write("OK: Users table found")
                
    except Exception as e:
        print(f"[ERROR] SQLAlchemy Connection Failed: {e}")
        with open("status.txt", "w", encoding="utf-8") as f:
            f.write(f"ERROR: {e}")


    print("="*60)
    print("CHECK COMPLETE")
    print("="*60)

if __name__ == "__main__":
    check_connection()
