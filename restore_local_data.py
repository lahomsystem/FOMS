import re
import sqlite3
import sys
import datetime
import os
import json
import sqlalchemy

# Configuration
SQL_DUMP_PATH = r"backups\tier1_primary\database_backup_20260203_153139.sql"
SQLITE_DB_PATH = "migration_ready.db"

# Tables to restore
# Tables to restore
TARGET_TABLES = [
    'public.users', 
    'public.orders',
    'public.chat_rooms', 
    'public.chat_messages',
    'public.chat_attachments',
    'public.chat_room_members',
    'public.order_events',
    'public.order_tasks', 
    'public.order_attachments',
    'public.access_logs',
    'public.security_logs',
    'wdcalculator.estimates',
    'wdcalculator.estimate_histories',
    'wdcalculator.estimate_order_matches'
]

def parse_postgres_value(val):
    if val == r'\N':
        return None
    # Boolean conversion
    if val == 't':
        return 1
    if val == 'f':
        return 0
    # Unescape common Postgres escapes
    val = val.replace(r'\n', '\n').replace(r'\t', '\t').replace(r'\\', '\\')
    return val

def restore_data():
    # 0. Clean start
    if os.path.exists(SQLITE_DB_PATH):
        os.remove(SQLITE_DB_PATH)
        print("Removed conflicting migration_ready.db")

    # 1. Setup Schema
    print("Initializing SQLite Schema...")
    from sqlalchemy import create_engine
    from sqlalchemy.dialects import postgresql
    
    # Monkeypatch JSONB for SQLite
    class MockJSONB(sqlalchemy.types.TypeDecorator):
        impl = sqlalchemy.Text
        def process_bind_param(self, value, dialect):
            return json.dumps(value) if value is not None else None
        def process_result_value(self, value, dialect):
            return json.loads(value) if value is not None else None
            
    postgresql.JSONB = MockJSONB
    
    # Import models (now using MockJSONB)
    from db import Base
    import models 
    from wdcalculator_db import WDCalculatorBase
    import wdcalculator_models

    sqlite_engine = create_engine(f"sqlite:///{SQLITE_DB_PATH}")
    
    # Create Tables
    Base.metadata.create_all(sqlite_engine)
    WDCalculatorBase.metadata.create_all(sqlite_engine)
    print("Schema created successfully.")

    conn = sqlite3.connect(SQLITE_DB_PATH)
    cursor = conn.cursor()
    
    print(f"Reading dump file: {SQL_DUMP_PATH}")
    try:
        with open(SQL_DUMP_PATH, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except FileNotFoundError:
        print("Error: Dump file not found.")
        return

    current_table = None
    columns = []
    
    for i, line in enumerate(lines):
        line = line.strip()
        
        # Check for COPY start
        # Format: COPY public.orders (id, ...) FROM stdin;
        if line.startswith("COPY ") and " FROM stdin;" in line:
            # Extract table name and keys
            match = re.match(r"COPY ([\w\.]+) \((.*)\) FROM stdin;", line)
            if match:
                full_table_name = match.group(1)
                cols_str = match.group(2)
                
                if full_table_name in TARGET_TABLES:
                    current_table = full_table_name.split('.')[-1] # remove 'public.'
                    columns = [c.strip().replace('"', '') for c in cols_str.split(',')]
                    print(f"Found data for table: {current_table} ({len(columns)} cols)")
                else:
                    current_table = None
            continue
            
        # Check for End of COPY
        if line == r'\.':
            if current_table:
                print(f"Finished table: {current_table}")
            current_table = None
            continue
            
        # Process Data Lines
        if current_table:
            # Postgres COPY is tab-separated
            # Should read original line to preserve tabs (strip() removes them if at ends?? No, strip() removes whitespace at ends)
            # Use raw line from file iterator would be safer but readlines() is ok if we are careful.
            # Reread the line from list without strip?
            raw_line = lines[i].rstrip('\n') # Remove only newline
            
            parts = raw_line.split('\t')
            
            # Safety check
            if len(parts) != len(columns):
                # Sometimes split error or mismatch?
                # print(f"Warning: Column mismatch line {i}: expected {len(columns)}, got {len(parts)}")
                pass
            
            values = [parse_postgres_value(p) for p in parts]
            
            # Construct INSERT
            placeholders = ','.join(['?'] * len(columns))
            cols_quoted = ','.join([f'"{c}"' for c in columns])
            sql = f'INSERT OR IGNORE INTO "{current_table}" ({cols_quoted}) VALUES ({placeholders})'
            
            try:
                cursor.execute(sql, values)
            except Exception as e:
                print(f"Error inserting row into {current_table}: {e}")
                
    conn.commit()
    conn.close()
    print("Restore completed.")

if __name__ == "__main__":
    restore_data()
