import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone


_START_TIME = time.monotonic()


def _log(msg: str) -> None:
    elapsed = time.monotonic() - _START_TIME
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] (+{elapsed:6.1f}s) {msg}", file=sys.stderr, flush=True)


sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
)

from app import app
from db import get_db
from models import Order
from foms.services.erp_sync_columns import _parse_stage_updated_at, sync_erp_flat_columns


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill orders.erp_stage_updated_at from structured_data.workflow.stage_updated_at."
    )
    parser.add_argument("--execute", action="store_true", help="Apply updates. Default is dry-run.")
    parser.add_argument("--order-id", type=int, default=None, help="Process one order only.")
    parser.add_argument("--limit", type=int, default=None, help="Inspect/process first N matching orders.")
    parser.add_argument("--sample-limit", type=int, default=20, help="How many sample rows to print.")
    parser.add_argument("--chunk-size", type=int, default=100, help="Commit size for --execute.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    return parser.parse_args()


def _workflow_stage_updated_at(order: Order):
    structured_data = order.structured_data if isinstance(order.structured_data, dict) else {}
    workflow = structured_data.get("workflow") if isinstance(structured_data.get("workflow"), dict) else {}
    return workflow.get("stage_updated_at")


def _dt_key(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value.isoformat(timespec="seconds")
    return str(value)


def _needs_update(order: Order, parsed) -> bool:
    return _dt_key(order.erp_stage_updated_at) != _dt_key(parsed)


def _query_orders(db, args: argparse.Namespace):
    query = (
        db.query(Order)
        .filter(Order.not_deleted_filter(), Order.is_erp_order.is_(True), Order.structured_data.isnot(None))
        .order_by(Order.id.asc())
    )
    if args.order_id is not None:
        query = query.filter(Order.id == args.order_id)
    if args.limit is not None:
        query = query.limit(args.limit)
    return query.all()


def run() -> int:
    args = _parse_args()
    summary = {
        "mode": "execute" if args.execute else "dry-run",
        "scanned": 0,
        "candidates": 0,
        "parse_failures": 0,
        "updated": 0,
        "samples": [],
        "parse_failure_samples": [],
    }

    with app.app_context():
        db = get_db()
        orders = _query_orders(db, args)
        _log(f"Inspecting {len(orders)} ERP orders with structured_data ...")

        pending_commit = 0
        for order in orders:
            summary["scanned"] += 1
            raw = _workflow_stage_updated_at(order)
            parsed = _parse_stage_updated_at(raw)
            if raw and parsed is None:
                summary["parse_failures"] += 1
                if len(summary["parse_failure_samples"]) < args.sample_limit:
                    summary["parse_failure_samples"].append({"id": order.id, "stage_updated_at": raw})
                continue
            if parsed is None or not _needs_update(order, parsed):
                continue

            summary["candidates"] += 1
            if len(summary["samples"]) < args.sample_limit:
                summary["samples"].append(
                    {
                        "id": order.id,
                        "current": _dt_key(order.erp_stage_updated_at),
                        "target": _dt_key(parsed),
                    }
                )

            if args.execute:
                sync_erp_flat_columns(order, order.structured_data)
                summary["updated"] += 1
                pending_commit += 1
                if pending_commit >= args.chunk_size:
                    db.commit()
                    pending_commit = 0

        if args.execute and pending_commit:
            db.commit()
        elif not args.execute:
            db.rollback()

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _log(
            "Summary: scanned={scanned}, candidates={candidates}, "
            "parse_failures={parse_failures}, updated={updated}".format(**summary)
        )
        if summary["samples"]:
            _log("Candidate samples:")
            for sample in summary["samples"]:
                _log(f"  #{sample['id']}: {sample['current']} -> {sample['target']}")
        if summary["parse_failure_samples"]:
            _log("Parse failure samples:")
            for sample in summary["parse_failure_samples"]:
                _log(f"  #{sample['id']}: {sample['stage_updated_at']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
