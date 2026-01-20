import argparse
import datetime
import json
from sqlalchemy import text
from flask import Flask

# app.py의 Flask app과 db 헬퍼를 재사용
from app import app  # noqa
from db import get_db


STEP_SCHEMA = "ERP_BETA_STEP_1_SCHEMA"


def _ensure_build_steps_table(db):
    db.execute(text("""
    CREATE TABLE IF NOT EXISTS system_build_steps (
        step_key VARCHAR(100) PRIMARY KEY,
        status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
        started_at TIMESTAMP NULL,
        completed_at TIMESTAMP NULL,
        message TEXT NULL,
        meta JSONB NULL
    );
    """))
    db.commit()


def _upsert_step(db, step_key, status, message=None, meta=None, started_at=None, completed_at=None):
    meta_json = json.dumps(meta, ensure_ascii=False) if isinstance(meta, (dict, list)) else None
    db.execute(
        text("""
        INSERT INTO system_build_steps (step_key, status, started_at, completed_at, message, meta)
        VALUES (:step_key, :status, :started_at, :completed_at, :message, CAST(:meta AS JSONB))
        ON CONFLICT (step_key)
        DO UPDATE SET
            status = EXCLUDED.status,
            started_at = COALESCE(system_build_steps.started_at, EXCLUDED.started_at),
            completed_at = EXCLUDED.completed_at,
            message = EXCLUDED.message,
            meta = COALESCE(EXCLUDED.meta, system_build_steps.meta);
        """),
        {
            "step_key": step_key,
            "status": status,
            "started_at": started_at,
            "completed_at": completed_at,
            "message": message,
            "meta": meta_json,
        }
    )
    db.commit()


def _get_step_status(db, step_key):
    row = db.execute(
        text("SELECT step_key, status, started_at, completed_at, message FROM system_build_steps WHERE step_key=:k"),
        {"k": step_key},
    ).fetchone()
    return dict(row._mapping) if row else None


def step_1_schema(db):
    """
    Step 1: orders 테이블에 ERP Beta 컬럼 추가 + 진행상태 기록
    - 재실행 가능(idempotent)
    """
    _ensure_build_steps_table(db)

    existing = _get_step_status(db, STEP_SCHEMA)
    if existing and existing.get("status") == "COMPLETED":
        print(f"[SKIP] {STEP_SCHEMA} already completed")
        return

    started_at = datetime.datetime.now()
    _upsert_step(db, STEP_SCHEMA, "RUNNING", message="Applying ERP Beta schema to orders table", started_at=started_at)

    try:
        # orders 컬럼 추가 (Postgres: ADD COLUMN IF NOT EXISTS)
        db.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS raw_order_text TEXT"))
        db.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS structured_data JSONB"))
        db.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS structured_schema_version INTEGER NOT NULL DEFAULT 1"))
        db.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS structured_confidence VARCHAR(20)"))
        db.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS structured_updated_at TIMESTAMP"))
        db.commit()

        completed_at = datetime.datetime.now()
        _upsert_step(
            db,
            STEP_SCHEMA,
            "COMPLETED",
            message="ERP Beta schema applied successfully",
            completed_at=completed_at,
            meta={"orders_columns_added": ["raw_order_text", "structured_data", "structured_schema_version", "structured_confidence", "structured_updated_at"]},
        )
        print(f"[OK] {STEP_SCHEMA} completed")
    except Exception as e:
        db.rollback()
        completed_at = datetime.datetime.now()
        _upsert_step(
            db,
            STEP_SCHEMA,
            "FAILED",
            message=f"Failed: {str(e)}",
            completed_at=completed_at,
        )
        raise


def main():
    parser = argparse.ArgumentParser(description="ERP Beta step-by-step builder (resumable via DB checkpoints)")
    parser.add_argument("--step", choices=["1"], help="Run a single step")
    parser.add_argument("--resume", action="store_true", help="Resume from the next incomplete step")
    args = parser.parse_args()

    with app.app_context():
        db = get_db()
        _ensure_build_steps_table(db)

        if args.step == "1":
            step_1_schema(db)
            return

        if args.resume:
            # 현재는 Step1만 있으므로 Step1부터 실행
            step_1_schema(db)
            return

        print("Usage: python erp_build_step_runner.py --step 1  (or --resume)")


if __name__ == "__main__":
    main()

