"""
Read-only snapshot of orders.is_erp_* columns and ERP-related indexes.

Preferred (avoids Windows os.environ mojibake for DATABASE_URL)::

    railway variables --json | python tools/harness/railway_db_gate_snapshot.py --from-stdin

Railway Linux container::

    cd /app && python tools/harness/railway_db_gate_snapshot.py

Fallback when DATABASE_URL is clean in the environment::

    railway run python tools/harness/railway_db_gate_snapshot.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.pool import NullPool


def _engine_from_database_url(url: str):
    """Prefer psycopg3; avoid raw psycopg2 DSN on Win11; fall back to host/user/pass kwargs."""
    try:
        import psycopg

        def _creator_psycopg():
            return psycopg.connect(url, connect_timeout=15)

        return create_engine("postgresql+psycopg://", creator=_creator_psycopg, poolclass=NullPool)
    except ImportError:
        pass

    import psycopg2

    mu = make_url(url)
    if mu.drivername not in ("postgresql", "postgresql+psycopg2"):
        return create_engine(url)

    def _creator_psycopg2():
        return psycopg2.connect(
            host=mu.host,
            port=mu.port or 5432,
            user=mu.username,
            password=mu.password,
            dbname=mu.database,
            connect_timeout=15,
        )

    return create_engine("postgresql+psycopg2://", creator=_creator_psycopg2, poolclass=NullPool)


def _load_database_url_from_stdin() -> str:
    raw = sys.stdin.read()
    if not raw.strip():
        raise SystemExit("stdin empty; pipe: railway variables --json | python ... --from-stdin")
    data = json.loads(raw)
    url = data.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL missing in JSON")
    return url


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--from-stdin",
        action="store_true",
        help="Read DATABASE_URL from railway variables JSON on stdin (recommended on Win11).",
    )
    args = parser.parse_args()

    if args.from_stdin:
        url = _load_database_url_from_stdin()
    else:
        url = os.environ.get("DATABASE_URL")
    if not url:
        print(json.dumps({"error": "no DATABASE_URL"}))
        sys.exit(1)

    eng = _engine_from_database_url(url)
    out: dict = {"columns": [], "indexes_erp": []}
    try:
        conn_ctx = eng.connect()
    except Exception as exc:
        print(
            json.dumps(
                {
                    "error": "connect_failed",
                    "detail": str(exc),
                    "hint": "Railway Postgres is usually reachable only inside the VPC. After deploy, run: railway ssh -- bash -lc \"cd /app && python3 tools/harness/railway_db_gate_snapshot_ssh.py\"",
                },
                ensure_ascii=False,
            )
        )
        sys.exit(1)
    with conn_ctx as conn:
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
