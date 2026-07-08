"""Minimal snapshot for `railway ssh`: reads DATABASE_URL from env only (container)."""
from __future__ import annotations

import json
import os
import sys

import psycopg2
from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.pool import NullPool


def main() -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print(json.dumps({"error": "no DATABASE_URL"}))
        sys.exit(1)
    mu = make_url(url)

    def _creator() -> psycopg2.extensions.connection:
        return psycopg2.connect(
            host=mu.host,
            port=mu.port or 5432,
            user=mu.username,
            password=mu.password,
            dbname=mu.database,
            connect_timeout=15,
        )

    eng = create_engine("postgresql+psycopg2://", creator=_creator, poolclass=NullPool)
    out: dict = {"columns": [], "indexes_erp": []}
    with eng.connect() as conn:
        q1 = text(
            """
            SELECT column_name, is_nullable, data_type
            FROM information_schema.columns
            WHERE table_schema = :s AND table_name = :t
              AND column_name IN ('is_erp_order', 'is_erp_beta')
            ORDER BY column_name
            """
        )
        out["columns"] = [dict(r._mapping) for r in conn.execute(q1, {"s": "public", "t": "orders"})]
        q2 = text(
            """
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE schemaname = :s AND tablename = :t
              AND (indexdef ILIKE :p OR indexname ILIKE :p2)
            """
        )
        out["indexes_erp"] = [
            dict(r._mapping) for r in conn.execute(q2, {"s": "public", "t": "orders", "p": "%erp%", "p2": "%erp%"})
        ]
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
