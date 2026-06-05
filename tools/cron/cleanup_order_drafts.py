"""Delete expired OrderDraft rows (P0-00C).

Default is dry-run. Pass --execute to delete rows where expires_at < now().

Flask app은 import하지 않는다. 전체 app 초기화(gevent patch, DB auto-init,
auto-migrate 등)는 Railway Heartbeat timeout의 원인이 되므로 DATABASE_URL로
직접 SQLAlchemy 엔진을 생성해 작업한다.
"""

from __future__ import annotations

import argparse
import logging
import os
import time
from datetime import datetime

logger = logging.getLogger("cleanup_order_drafts")


def _parse_args() -> argparse.Namespace:
    """Parse CLI flags for dry-run vs execute."""
    parser = argparse.ArgumentParser(
        description="Cleanup expired OrderDraft rows (default: dry-run)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Explicit dry-run alias (default behavior; no deletes).",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Delete expired drafts. Without this flag, only counts.",
    )
    return parser.parse_args()


def _setup_logging() -> None:
    """Configure root logging for cron stdout."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")


def _make_session():
    """Create a bare SQLAlchemy session from DATABASE_URL (no Flask app)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    # Railway Postgres URL은 postgres:// → postgresql:// 변환 필요
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    engine = create_engine(url, connect_args={"connect_timeout": 10}, pool_pre_ping=True)
    Session = sessionmaker(bind=engine)
    return Session(), engine


def run(*, execute: bool = False) -> tuple[int, int]:
    """Count and optionally delete expired OrderDraft rows.

    Args:
        execute: When True, delete rows with expires_at < now().

    Returns:
        Tuple of (scanned_count, deleted_count).
    """
    from sqlalchemy import text

    session, engine = _make_session()
    now = datetime.utcnow()
    try:
        scanned_row = session.execute(
            text("SELECT COUNT(*) FROM order_drafts WHERE expires_at < :now"),
            {"now": now},
        ).fetchone()
        scanned = scanned_row[0] if scanned_row else 0

        deleted = 0
        if execute and scanned > 0:
            result = session.execute(
                text("DELETE FROM order_drafts WHERE expires_at < :now"),
                {"now": now},
            )
            deleted = result.rowcount
            session.commit()
        return scanned, deleted
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()


def main() -> int:
    """CLI entrypoint. Exit 0 on success, 1 on error."""
    _setup_logging()
    args = _parse_args()
    if args.dry_run and args.execute:
        logger.error("[cleanup_order_drafts] --dry-run and --execute are mutually exclusive")
        return 1

    execute = args.execute
    mode = "execute" if execute else "dry-run"
    started = time.monotonic()
    try:
        scanned, deleted = run(execute=execute)
        elapsed = time.monotonic() - started
        logger.info(
            "[cleanup_order_drafts] mode=%s scanned=%d deleted=%d elapsed=%.1fs",
            mode,
            scanned,
            deleted,
            elapsed,
        )
        return 0
    except Exception:
        logger.exception("[cleanup_order_drafts] failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
