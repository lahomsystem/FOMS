"""List active users (Railway SSH: python tools/ops/list_active_users.py)."""
from __future__ import annotations

import os

from sqlalchemy import create_engine, text


def main() -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL not set")
    engine = create_engine(url)
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
