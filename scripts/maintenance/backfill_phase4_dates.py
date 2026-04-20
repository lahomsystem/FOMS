import argparse
import os
import sys

sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
)

from app import app
from db import get_db
from models import Order
from foms.services.order_date_sync import collect_order_schedule_date_specs, sync_order_dates
from sqlalchemy.orm import selectinload


def _row_key(row):
    return (
        str(row.kind or '').strip(),
        str(row.date or '').strip(),
        str(row.source or '').strip(),
        row.item_index,
    )


def _spec_key(spec):
    return (
        str(spec.get('kind') or '').strip(),
        str(spec.get('date') or '').strip(),
        str(spec.get('source') or '').strip(),
        spec.get('item_index'),
    )


def _parse_args():
    parser = argparse.ArgumentParser(
        description="Safe backfill for order_schedule_dates. No global delete."
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview only. No writes.")
    parser.add_argument("--only-missing", action="store_true", help="Only process orders with no schedule_dates rows.")
    parser.add_argument("--limit", type=int, default=None, help="Process only the first N orders.")
    parser.add_argument("--order-id", type=int, default=None, help="Process a single order only.")
    parser.add_argument("--verbose", action="store_true", help="Print per-order diff summary.")
    return parser.parse_args()


def _target_order_ids(db, order_id=None, only_missing=False, limit=None):
    query = db.query(Order.id).order_by(Order.id.asc())
    if order_id is not None:
        query = query.filter(Order.id == order_id)
    elif only_missing:
        query = query.filter(~Order.schedule_dates.any())

    if limit is not None and limit > 0:
        query = query.limit(limit)

    return [row[0] for row in query.all()]


def backfill_phase4_dates():
    args = _parse_args()

    with app.app_context():
        db = get_db()
        order_ids = _target_order_ids(
            db,
            order_id=args.order_id,
            only_missing=args.only_missing,
            limit=args.limit,
        )

        print(
            {
                "mode": "dry-run" if args.dry_run else "apply",
                "only_missing": args.only_missing,
                "target_orders": len(order_ids),
            }
        )

        processed = 0
        updated = 0
        skipped = 0
        failed = []

        for oid in order_ids:
            processed += 1
            try:
                order = (
                    db.query(Order)
                    .options(selectinload(Order.schedule_dates))
                    .filter(Order.id == oid)
                    .one()
                )

                existing = sorted(_row_key(row) for row in (order.schedule_dates or []))
                desired_specs = collect_order_schedule_date_specs(order)
                desired = sorted(_spec_key(spec) for spec in desired_specs)

                if existing == desired:
                    skipped += 1
                    if args.verbose:
                        print(f"[SKIP] order_id={oid} rows={len(existing)}")
                    continue

                if args.verbose or args.dry_run:
                    print(
                        f"[DIFF] order_id={oid} "
                        f"existing={len(existing)} desired={len(desired)}"
                    )

                if not args.dry_run:
                    sync_order_dates(order, db)
                    db.commit()
                    updated += 1
                else:
                    db.rollback()

            except Exception as exc:
                db.rollback()
                failed.append((oid, str(exc)))
                print(f"[FAIL] order_id={oid} error={exc}")

        print(
            {
                "processed": processed,
                "updated": updated,
                "skipped": skipped,
                "failed": len(failed),
            }
        )

        if failed:
            print("Failed orders:")
            for oid, msg in failed[:20]:
                print(f" - order_id={oid}: {msg}")
            if len(failed) > 20:
                print(f" ... and {len(failed) - 20} more")
            raise SystemExit(1)


if __name__ == "__main__":
    backfill_phase4_dates()
