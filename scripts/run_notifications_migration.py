#!/usr/bin/env python3
"""
notifications 테이블 마이그레이션 1회 실행.
사용: python scripts/run_notifications_migration.py
     또는 DATABASE_URL=... python scripts/run_notifications_migration.py
"""
import os
import sys

def _normalize_url(url: str) -> str:
    if not url:
        return url
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://") and "+psycopg2" not in url:
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url

MIGRATION_SQL = """
ALTER TABLE notifications ALTER COLUMN order_id DROP NOT NULL;
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS target_type VARCHAR(20) NOT NULL DEFAULT 'ORDER';
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS target_user_id INTEGER REFERENCES users(id) NULL;
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS is_urgent BOOLEAN NOT NULL DEFAULT FALSE;
CREATE INDEX IF NOT EXISTS ix_notifications_target_type ON notifications(target_type);
CREATE INDEX IF NOT EXISTS ix_notifications_target_user_id ON notifications(target_user_id);
CREATE INDEX IF NOT EXISTS ix_notifications_is_urgent ON notifications(is_urgent);
"""

def main():
    url = os.environ.get("DATABASE_URL") or (sys.argv[1] if len(sys.argv) > 1 else None)
    if not url:
        print("Usage: DATABASE_URL=... python scripts/run_notifications_migration.py", file=sys.stderr)
        sys.exit(1)
    url = _normalize_url(url)
    from sqlalchemy import create_engine, text
    engine = create_engine(url, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        for stmt in MIGRATION_SQL.strip().split(";"):
            stmt = stmt.strip()
            if not stmt:
                continue
            conn.execute(text(stmt))
            print("OK:", stmt[:60] + "..." if len(stmt) > 60 else stmt)
    print("Migration completed.")
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("Error:", e, file=sys.stderr)
        sys.exit(1)
