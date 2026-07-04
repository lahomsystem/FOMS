"""Backfill notification_user_states from legacy Notification rows (Phase 0A).

공유 `Notification` row 를 사용자별 `notification_user_states` 로 물질화한다. chunked +
resume cursor + dry-run 지원. 두 번 실행해도 중복 state / 중복 ambiguous event 가 없다
(idempotent). 코어 로직은 `foms.services.notifications.backfill` 참조.

사용 예 (PowerShell 5.x)::

    python scripts/maintenance/backfill_notification_user_states.py --dry-run
    python scripts/maintenance/backfill_notification_user_states.py --execute --chunk-size 500
    python scripts/maintenance/backfill_notification_user_states.py --execute --cursor-file .backfill_notif.cursor
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime


_START_TIME = time.monotonic()


def _log(msg: str) -> None:
    elapsed = time.monotonic() - _START_TIME
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] (+{elapsed:6.1f}s) {msg}", file=sys.stderr, flush=True)


sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
)

from app import app  # noqa: E402
from db import get_db  # noqa: E402
from foms.services.notifications.backfill import run_backfill  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill notification_user_states from legacy Notification rows."
    )
    parser.add_argument("--execute", action="store_true", help="Apply changes. Default is dry-run.")
    parser.add_argument("--dry-run", action="store_true", help="Force dry-run (default when --execute absent).")
    parser.add_argument("--chunk-size", type=int, default=500, help="Rows per chunk / commit unit.")
    parser.add_argument("--start-id", type=int, default=None, help="Process notification.id > START_ID.")
    parser.add_argument(
        "--cursor-file", default=None, help="Resume cursor file (last processed id, rewritten each chunk)."
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON summary.")
    return parser.parse_args()


def _resolve_start_id(args: argparse.Namespace) -> int:
    """--start-id 우선, 없으면 cursor-file 값, 둘 다 없으면 0."""
    if args.start_id is not None:
        return args.start_id
    if args.cursor_file and os.path.exists(args.cursor_file):
        try:
            with open(args.cursor_file, "r", encoding="utf-8") as handle:
                return int((handle.read() or "0").strip() or "0")
        except (ValueError, OSError) as exc:
            _log(f"cursor-file read failed ({exc}); starting from 0")
    return 0


def _make_progress(args: argparse.Namespace):
    dry_run = not args.execute

    def _progress(last_id: int, totals: dict) -> None:
        _log(
            "chunk done: last_id={last} scanned={scanned} states_created={sc} "
            "ambiguous_events={amb}".format(
                last=last_id,
                scanned=totals["scanned"],
                sc=totals["states_created"],
                amb=totals["ambiguous_events"],
            )
        )
        if args.cursor_file and not dry_run:
            with open(args.cursor_file, "w", encoding="utf-8") as handle:
                handle.write(str(last_id))

    return _progress


def run() -> int:
    args = _parse_args()
    dry_run = not args.execute
    start_id = _resolve_start_id(args)
    _log(f"mode={'dry-run' if dry_run else 'execute'} chunk_size={args.chunk_size} start_id={start_id}")

    with app.app_context():
        db = get_db()
        totals = run_backfill(
            db,
            chunk_size=args.chunk_size,
            dry_run=dry_run,
            start_id=start_id,
            progress=_make_progress(args),
        )

    summary = {"mode": "dry-run" if dry_run else "execute", **totals}
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _log(
            "Summary: scanned={scanned} states_created={states_created} "
            "ambiguous_events={ambiguous_events} last_id={last_id}".format(**summary)
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
