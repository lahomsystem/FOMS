"""
WDCalculator 별도 DB → 통합 DB(wdcalculator 스키마) 마이그레이션 스크립트

요약:
- source(OLD): 예전 WDCalculator 별도 Postgres DB
- dest(NEW): 현재 FOMS DATABASE_URL Postgres의 wdcalculator 스키마
- idempotent: meta를 건드리지 않고, PK(id) 기준 UPSERT로 재실행 가능

사용 예시(PowerShell):
  $env:WD_SRC_DATABASE_URL = "postgresql://user:pass@host:5432/wdcalculator_estimates"
  $env:DATABASE_URL = "postgresql://user:pass@host:5432/foms_main"
  python tools/migrate_wdcalculator_from_separate_db.py
"""

from __future__ import annotations

import os
import json
from typing import Optional, Tuple

from sqlalchemy import create_engine, text


def _normalize_postgres_url(url: str) -> str:
    if not url:
        return url
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://") :]
    return url


def _find_table_schema(conn, table_name: str) -> Optional[str]:
    row = conn.execute(
        text(
            """
            SELECT table_schema
            FROM information_schema.tables
            WHERE table_name=:t
            ORDER BY CASE WHEN table_schema='public' THEN 0 ELSE 1 END, table_schema
            LIMIT 1
            """
        ),
        {"t": table_name},
    ).fetchone()
    return str(row.table_schema) if row else None


def _ensure_dest_schema_and_tables(conn, schema: str):
    conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))

    # estimates
    conn.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS "{schema}".estimates (
                id INTEGER PRIMARY KEY,
                customer_name VARCHAR(100) NOT NULL,
                estimate_data JSONB NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
            """
        )
    )
    conn.execute(text(f'CREATE INDEX IF NOT EXISTS ix_{schema}_estimates_customer_name ON "{schema}".estimates(customer_name)'))

    # estimate_histories
    conn.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS "{schema}".estimate_histories (
                id INTEGER PRIMARY KEY,
                estimate_id INTEGER NOT NULL,
                estimate_data JSONB NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
            """
        )
    )
    conn.execute(text(f'CREATE INDEX IF NOT EXISTS ix_{schema}_estimate_histories_estimate_id ON "{schema}".estimate_histories(estimate_id)'))

    # estimate_order_matches
    conn.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS "{schema}".estimate_order_matches (
                id INTEGER PRIMARY KEY,
                estimate_id INTEGER NOT NULL,
                order_id INTEGER NOT NULL,
                matched_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
            """
        )
    )
    conn.execute(text(f'CREATE INDEX IF NOT EXISTS ix_{schema}_estimate_order_matches_estimate_id ON "{schema}".estimate_order_matches(estimate_id)'))
    conn.execute(text(f'CREATE INDEX IF NOT EXISTS ix_{schema}_estimate_order_matches_order_id ON "{schema}".estimate_order_matches(order_id)'))


def _upsert_rows(conn, dest_schema: str, table: str, rows, columns):
    if not rows:
        return 0
    cols = ", ".join(columns)
    params = ", ".join([f":{c}" for c in columns])
    updates = ", ".join([f"{c}=EXCLUDED.{c}" for c in columns if c != "id"])
    sql = f"""
        INSERT INTO "{dest_schema}".{table} ({cols})
        VALUES ({params})
        ON CONFLICT (id) DO UPDATE SET {updates};
    """
    for r in rows:
        payload = {}
        for c in columns:
            v = getattr(r, c)
            if isinstance(v, (dict, list)):
                payload[c] = json.dumps(v, ensure_ascii=False)
            else:
                payload[c] = v
        conn.execute(text(sql), payload)
    return len(rows)


def _copy_table(src_conn, dst_conn, src_schema: str, dst_schema: str, table: str, columns: Tuple[str, ...], chunk_size: int = 2000):
    last_id = 0
    total = 0
    while True:
        q = text(
            f"""
            SELECT {", ".join(columns)}
            FROM "{src_schema}".{table}
            WHERE id > :last_id
            ORDER BY id
            LIMIT :lim
            """
        )
        batch = src_conn.execute(q, {"last_id": last_id, "lim": chunk_size}).fetchall()
        if not batch:
            break
        total += _upsert_rows(dst_conn, dst_schema, table, batch, columns)
        last_id = int(getattr(batch[-1], "id"))
    return total


def _sync_sequence(conn, schema: str, table: str):
    # id가 SERIAL일 때의 시퀀스 자동 탐지/동기화 (없으면 skip)
    row = conn.execute(text("SELECT pg_get_serial_sequence(:t, 'id') AS seq"), {"t": f'{schema}.{table}'}).fetchone()
    seq = row.seq if row else None
    if not seq:
        return
    conn.execute(text(f"SELECT setval('{seq}', COALESCE((SELECT MAX(id) FROM \"{schema}\".{table}), 0) + 1, false)"))


def main():
    src_url = _normalize_postgres_url(os.getenv("WD_SRC_DATABASE_URL") or "")
    dst_url = _normalize_postgres_url(os.getenv("DATABASE_URL") or "")
    dest_schema = os.getenv("WD_CALCULATOR_SCHEMA") or "wdcalculator"

    if not src_url:
        raise SystemExit("WD_SRC_DATABASE_URL 환경변수가 필요합니다(예: 예전 WDCalculator 별도 DB URL).")
    if not dst_url:
        raise SystemExit("DATABASE_URL 환경변수가 필요합니다(현재 통합 Postgres DB URL).")

    src_engine = create_engine(src_url, pool_pre_ping=True)
    dst_engine = create_engine(dst_url, pool_pre_ping=True)

    with src_engine.begin() as src_conn, dst_engine.begin() as dst_conn:
        src_schema = _find_table_schema(src_conn, "estimates") or "public"
        print("[INFO] source schema:", src_schema)
        _ensure_dest_schema_and_tables(dst_conn, dest_schema)

        n1 = _copy_table(
            src_conn, dst_conn, src_schema, dest_schema,
            "estimates",
            ("id", "customer_name", "estimate_data", "created_at", "updated_at"),
        )
        n2 = _copy_table(
            src_conn, dst_conn, src_schema, dest_schema,
            "estimate_histories",
            ("id", "estimate_id", "estimate_data", "created_at"),
        )
        n3 = _copy_table(
            src_conn, dst_conn, src_schema, dest_schema,
            "estimate_order_matches",
            ("id", "estimate_id", "order_id", "matched_at"),
        )

        _sync_sequence(dst_conn, dest_schema, "estimates")
        _sync_sequence(dst_conn, dest_schema, "estimate_histories")
        _sync_sequence(dst_conn, dest_schema, "estimate_order_matches")

        print("[OK] migrated rows:",
              "estimates=", n1,
              "estimate_histories=", n2,
              "estimate_order_matches=", n3)


if __name__ == "__main__":
    main()

