"""Delete expired OrderDraft rows (P0-00C).

Default is dry-run. Pass --execute to delete rows where expires_at < now().
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import datetime

logger = logging.getLogger("cleanup_order_drafts")

sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
)


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


def run(*, execute: bool = False) -> tuple[int, int]:
    """Count and optionally delete expired OrderDraft rows.

    Args:
        execute: When True, delete rows with expires_at < now().

    Returns:
        Tuple of (scanned_count, deleted_count).
    """
    from app import app
    from db import get_db
    from models import OrderDraft

    now = datetime.now()
    with app.app_context():
        db = get_db()
        expired_filter = OrderDraft.expires_at < now
        scanned = db.query(OrderDraft).filter(expired_filter).count()
        if execute:
            deleted = (
                db.query(OrderDraft)
                .filter(expired_filter)
                .delete(synchronize_session=False)
            )
            db.commit()
        else:
            deleted = 0
    return scanned, deleted


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
