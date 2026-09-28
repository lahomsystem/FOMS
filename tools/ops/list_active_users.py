"""List active users (Railway SSH: python tools/ops/list_active_users.py)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

# 저장소 루트를 import 경로에 넣는다 — `python tools/ops/...` 로 직접 부르면 tools/ops 만 들어간다.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from foms.services.db_url_resolver import sqlalchemy_url  # noqa: E402


def main() -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL not set")
    engine = create_engine(sqlalchemy_url(url))
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, username, name, role FROM users "
                "WHERE is_active = true ORDER BY id"
            )
        ).fetchall()
        for row in rows:
            print(f"{row.id}\t{row.username}\t{row.name}\t{row.role}")


if __name__ == "__main__":
    main()
