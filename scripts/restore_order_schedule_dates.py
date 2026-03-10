import argparse
import json
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.db_url_resolver import prepare_database_url_env

prepare_database_url_env()

from app import app
from db import get_db
from models import OrderScheduleDate


def _parse_args():
    parser = argparse.ArgumentParser(
        description="Restore order_schedule_dates from a backup JSON file."
    )
    parser.add_argument("--input", required=True, help="Backup JSON path.")
    parser.add_argument("--dry-run", action="store_true", help="Preview only. No writes.")
    parser.add_argument(
        "--confirm-replace",
        default="",
        help="Required to apply. Pass RESTORE to replace current order_schedule_dates rows.",
    )
    return parser.parse_args()


def main():
    args = _parse_args()
    input_path = os.path.abspath(args.input)
    if not os.path.exists(input_path):
        raise SystemExit(f"Backup file not found: {input_path}")

    with open(input_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    rows = payload.get("rows") or []

    with app.app_context():
        db = get_db()
        current_count = db.query(OrderScheduleDate).count()
        print(
            {
                "mode": "dry-run" if args.dry_run else "apply",
                "input": input_path,
                "backup_row_count": len(rows),
                "current_row_count": current_count,
            }
        )

        if args.dry_run:
            return

        if args.confirm_replace != "RESTORE":
            raise SystemExit("Refusing to apply without --confirm-replace RESTORE")

        try:
            db.query(OrderScheduleDate).delete(synchronize_session=False)
            db.bulk_insert_mappings(
                OrderScheduleDate,
                [
                    {
                        "order_id": row["order_id"],
                        "kind": row["kind"],
                        "date": row["date"],
                        "source": row["source"],
                        "item_index": row.get("item_index"),
                    }
                    for row in rows
                ],
            )
            db.commit()
        except Exception:
            db.rollback()
            raise

        print({"restored_row_count": len(rows)})


if __name__ == "__main__":
    main()
