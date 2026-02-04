import sqlite3
import os

DB_PATH = 'migration_ready.db'

if not os.path.exists(DB_PATH):
    print("migration_ready.db NOT FOUND")
    exit()

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Check Tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = [r[0] for r in cursor.fetchall()]
print(f"Tables in SQLite: {tables}")

# Check Orders (Booleans)
if 'orders' in tables:
    print("\n--- Orders Sample (is_regional, is_self_measurement, is_erp_beta) ---")
    # Get column names
    cursor.execute("PRAGMA table_info(orders)")
    cols = [r[1] for r in cursor.fetchall()]
    
    target_cols = ['id', 'is_regional', 'is_self_measurement', 'is_erp_beta']
    existing_targets = [c for c in target_cols if c in cols]
    
    if existing_targets:
        sql = f"SELECT {', '.join(existing_targets)} FROM orders LIMIT 10"
        cursor.execute(sql)
        for row in cursor.fetchall():
            print(row)
    else:
        print("Boolean columns NOT FOUND in orders table!")

# Check Estimates
if 'estimates' in tables:
    cursor.execute("SELECT count(*) FROM estimates")
    print(f"\nestimates count: {cursor.fetchone()[0]}")
else:
    print("\n'estimates' table NOT FOUND in SQLite")

conn.close()
