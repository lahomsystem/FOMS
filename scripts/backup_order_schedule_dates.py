import argparse
import datetime
import json
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from foms.services.db_url_resolver import prepare_database_url_env

prepare_database_url_env()

from app import app
from db import get_db
from models import OrderScheduleDate


def _default_output_path():
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    return os.path.join("backups", f"order_schedule_dates-{ts}.json")


def _parse_args():
    parser = argparse.ArgumentParser(
        description="Backup order_schedule_dates to a local JSON file."
    )
    parser.add_argument(
        "--output",
        default=_default_output_path(),
        help="Output JSON path. Default: backups/order_schedule_dates-YYYYMMDD-HHMMSS.json",
    )
    return parser.parse_args()


def main():
    args = _parse_args()
    output_path = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with app.app_context():
        db = get_db()
        rows = (
            db.query(OrderScheduleDate)
            .order_by(
                OrderScheduleDate.order_id.asc(),
                OrderScheduleDate.kind.asc(),
                OrderScheduleDate.date.asc(),
                OrderScheduleDate.id.asc(),
            )
            .all()
        )

        payload = {
            "generated_at": datetime.datetime.now().isoformat(),
            "row_count": len(rows),
            "rows": [row.to_dict() for row in rows],
        }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(
        {
            "output": output_path,
            "row_count": payload["row_count"],
        }
    )


if __name__ == "__main__":
    main()
