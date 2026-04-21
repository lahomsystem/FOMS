import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime


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
from foms.services.orders.estimate_defaults import (
    ERP_DRAFT_PLACEHOLDER_CUSTOMER,
    ERP_DRAFT_PLACEHOLDER_PHONE,
    ERP_DRAFT_PLACEHOLDER_PRODUCT,
)


LEGACY_PLACEHOLDER_TEXTS = {
    "",
    ERP_DRAFT_PLACEHOLDER_CUSTOMER.upper(),
    ERP_DRAFT_PLACEHOLDER_PRODUCT.upper(),
    "ERP BETA",
    "ERP_BETA",
}
PHONE_PLACEHOLDER = ERP_DRAFT_PLACEHOLDER_PHONE
CONSULTING_FALLBACK = "상담"


@dataclass
class BackfillPlan:
    order: Order
    suggested_customer_name: str
    suggested_phone: str
    suggested_product: str
    suggested_address: str
    needs_customer_backfill: bool
    needs_phone_backfill: bool
    needs_product_backfill: bool
    needs_address_backfill: bool

    @property
    def needs_any_backfill(self) -> bool:
        return (
            self.needs_customer_backfill
            or self.needs_phone_backfill
            or self.needs_product_backfill
            or self.needs_address_backfill
        )

    @property
    def unresolved_placeholder_product(self) -> bool:
        return _is_placeholder_text(self.order.product) and not self.needs_product_backfill


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ERP_BETA placeholder backfill runner for active ERP orders."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Apply the backfill. Default is dry-run.",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Skip planning/apply and print post-state verification only.",
    )
    parser.add_argument(
        "--order-id",
        type=int,
        default=None,
        help="Process a single order only.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Inspect/process only the first N active ERP orders.",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=20,
        help="How many sample rows to print in dry-run / verify output.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=100,
        help="Commit size for --execute (default: 100).",
    )
    return parser.parse_args()


def _trim(value) -> str:
    return str(value or "").strip()


def _normalized_upper(value) -> str:
    return _trim(value).upper()


def _is_placeholder_text(value) -> bool:
    return _normalized_upper(value) in LEGACY_PLACEHOLDER_TEXTS


def _is_placeholder_phone(value) -> bool:
    return _trim(value) in {"", PHONE_PLACEHOLDER}


def _first_real_product_name(structured_data: dict) -> str:
    items = structured_data.get("items") or []
    if not isinstance(items, list):
        return ""

    for item in items:
        if not isinstance(item, dict):
            continue
        for key in ("product_name", "name"):
            value = _trim(item.get(key))
            if value and not _is_placeholder_text(value):
                return value
    return ""


def _consulting_fallback(structured_data: dict) -> str:
    items = structured_data.get("items") or []
    if not isinstance(items, list) or not items:
        return ""
    first_item = items[0]
    if not isinstance(first_item, dict):
        return ""

    for key in ("option_detail", "handle", "misc", "internal"):
        value = _trim(first_item.get(key))
        if value == CONSULTING_FALLBACK:
            return CONSULTING_FALLBACK
    return ""


def _suggestions(order: Order) -> tuple[str, str, str, str]:
    structured_data = order.structured_data if isinstance(order.structured_data, dict) else {}
    parties = structured_data.get("parties") or {}
    customer = (parties.get("customer") or {}) if isinstance(parties, dict) else {}
    site = structured_data.get("site") or {}

    suggested_customer_name = _trim(customer.get("name"))
    if _is_placeholder_text(suggested_customer_name):
        suggested_customer_name = ""

    suggested_phone = _trim(customer.get("phone"))
    if _is_placeholder_phone(suggested_phone):
        suggested_phone = ""

    suggested_address = _trim(
        (site.get("address_full") if isinstance(site, dict) else "")
        or (site.get("address_main") if isinstance(site, dict) else "")
    )
    if suggested_address == "-":
        suggested_address = ""

    suggested_product = _first_real_product_name(structured_data)
    if not suggested_product:
        suggested_product = _consulting_fallback(structured_data)

    return (
        suggested_customer_name,
        suggested_phone,
        suggested_product,
        suggested_address,
    )


def _build_plan(order: Order) -> BackfillPlan:
    (
        suggested_customer_name,
        suggested_phone,
        suggested_product,
        suggested_address,
    ) = _suggestions(order)

    needs_customer_backfill = _is_placeholder_text(order.customer_name) and bool(
        suggested_customer_name
    )
    needs_phone_backfill = _is_placeholder_phone(order.phone) and bool(suggested_phone)
    needs_product_backfill = _is_placeholder_text(order.product) and bool(suggested_product)
    needs_address_backfill = (_trim(order.address) in {"", "-"}) and bool(suggested_address)

    return BackfillPlan(
        order=order,
        suggested_customer_name=suggested_customer_name,
        suggested_phone=suggested_phone,
        suggested_product=suggested_product,
        suggested_address=suggested_address,
        needs_customer_backfill=needs_customer_backfill,
        needs_phone_backfill=needs_phone_backfill,
        needs_product_backfill=needs_product_backfill,
        needs_address_backfill=needs_address_backfill,
    )


def _load_orders(db, *, order_id: int | None, limit: int | None) -> list[Order]:
    _log(f"Loading active ERP orders (order_id={order_id}, limit={limit}) ...")
    query = (
        db.query(Order)
        .filter(Order.active_filter(), Order.is_erp_order.is_(True))
        .order_by(Order.id.asc())
    )
    if order_id is not None:
        query = query.filter(Order.id == order_id)
    if limit is not None and limit > 0:
        query = query.limit(limit)
    rows = query.all()
    _log(f"Loaded {len(rows)} ERP orders.")
    return rows


def _summarize_plans(plans: list[BackfillPlan]) -> dict[str, int]:
    return {
        "active_erp_orders": len(plans),
        "customer_backfill_candidates": sum(1 for plan in plans if plan.needs_customer_backfill),
        "phone_backfill_candidates": sum(1 for plan in plans if plan.needs_phone_backfill),
        "product_backfill_candidates": sum(1 for plan in plans if plan.needs_product_backfill),
        "address_backfill_candidates": sum(1 for plan in plans if plan.needs_address_backfill),
        "any_backfill_candidates": sum(1 for plan in plans if plan.needs_any_backfill),
        "unresolved_placeholder_product_rows": sum(
            1 for plan in plans if plan.unresolved_placeholder_product
        ),
    }


def _sample_rows(plans: list[BackfillPlan], sample_limit: int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    interesting = [
        plan
        for plan in plans
        if plan.needs_any_backfill or plan.unresolved_placeholder_product
    ]
    for plan in interesting[:sample_limit]:
        order = plan.order
        rows.append(
            {
                "id": order.id,
                "status": order.status,
                "current_customer_name": order.customer_name,
                "suggested_customer_name": plan.suggested_customer_name,
                "current_phone": order.phone,
                "suggested_phone": plan.suggested_phone,
                "current_product": order.product,
                "suggested_product": plan.suggested_product,
                "current_address": order.address,
                "suggested_address": plan.suggested_address,
                "needs_customer_backfill": plan.needs_customer_backfill,
                "needs_phone_backfill": plan.needs_phone_backfill,
                "needs_product_backfill": plan.needs_product_backfill,
                "needs_address_backfill": plan.needs_address_backfill,
                "unresolved_placeholder_product": plan.unresolved_placeholder_product,
            }
        )
    return rows


def _verification_summary(db, sample_limit: int) -> dict[str, object]:
    _log("Running verification summary ...")
    orders = _load_orders(db, order_id=None, limit=None)
    residual_rows = []
    for order in orders:
        current_customer_name = _trim(order.customer_name)
        current_phone = _trim(order.phone)
        current_product = _trim(order.product)
        if (
            current_customer_name.upper() == "ERP BETA"
            or current_product.upper() == "ERP BETA"
            or current_phone == PHONE_PLACEHOLDER
        ):
            residual_rows.append(
                {
                    "id": order.id,
                    "status": order.status,
                    "customer_name": order.customer_name,
                    "phone": order.phone,
                    "product": order.product,
                }
            )

    summary = {
        "active_orders": db.query(Order).filter(Order.active_filter()).count(),
        "active_customer_name_erp_beta": sum(
            1 for order in orders if _trim(order.customer_name).upper() == "ERP BETA"
        ),
        "active_product_erp_beta": sum(
            1 for order in orders if _trim(order.product).upper() == "ERP BETA"
        ),
        "active_phone_placeholder_rows": sum(
            1 for order in orders if _trim(order.phone) == PHONE_PLACEHOLDER
        ),
        "residual_rows": residual_rows[:sample_limit],
        "residual_row_count": len(residual_rows),
    }
    _log(
        f"Verification done. residual={summary['residual_row_count']}, "
        f"erp_beta(name)={summary['active_customer_name_erp_beta']}, "
        f"erp_beta(product)={summary['active_product_erp_beta']}, "
        f"phone_placeholder={summary['active_phone_placeholder_rows']}"
    )
    return summary


def _print_output(payload: dict[str, object], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> None:
    args = _parse_args()

    with app.app_context():
        db = get_db()
        try:
            if args.verify_only:
                payload = {
                    "mode": "verify-only",
                    "verification": _verification_summary(db, args.sample_limit),
                }
                _print_output(payload, as_json=args.json)
                return

            orders = _load_orders(db, order_id=args.order_id, limit=args.limit)
            _log(f"Building backfill plans for {len(orders)} orders ...")
            plans = []
            for idx, order in enumerate(orders, start=1):
                plans.append(_build_plan(order))
                if idx % 200 == 0:
                    _log(f"  planned {idx}/{len(orders)}")
            _log(f"Plans built: {len(plans)}.")
            summary = _summarize_plans(plans)
            _log(
                f"Summary: any_backfill={summary['any_backfill_candidates']}, "
                f"customer={summary['customer_backfill_candidates']}, "
                f"phone={summary['phone_backfill_candidates']}, "
                f"product={summary['product_backfill_candidates']}, "
                f"address={summary['address_backfill_candidates']}"
            )
            payload: dict[str, object] = {
                "mode": "execute" if args.execute else "dry-run",
                "scope": {
                    "order_id": args.order_id,
                    "limit": args.limit,
                },
                "summary": summary,
                "sample_rows": _sample_rows(plans, args.sample_limit),
            }

            if not args.execute:
                _print_output(payload, as_json=args.json)
                db.rollback()
                return

            candidates = [p for p in plans if p.needs_any_backfill]
            total_candidates = len(candidates)
            chunk_size = max(1, args.chunk_size)
            _log(
                f"Applying + committing {total_candidates} updates in chunks of {chunk_size} ..."
            )
            updated_rows: list[dict[str, object]] = []
            pending_in_chunk = 0
            for idx, plan in enumerate(candidates, start=1):
                order = plan.order
                if plan.needs_customer_backfill:
                    order.customer_name = plan.suggested_customer_name
                if plan.needs_phone_backfill:
                    order.phone = plan.suggested_phone
                if plan.needs_product_backfill:
                    order.product = plan.suggested_product
                if plan.needs_address_backfill:
                    order.address = plan.suggested_address

                updated_rows.append(
                    {
                        "id": order.id,
                        "customer_name": order.customer_name,
                        "phone": order.phone,
                        "product": order.product,
                        "address": order.address,
                    }
                )
                pending_in_chunk += 1

                if pending_in_chunk >= chunk_size:
                    chunk_start = time.monotonic()
                    db.commit()
                    _log(
                        f"  committed {idx}/{total_candidates} "
                        f"(chunk took {time.monotonic() - chunk_start:.1f}s)"
                    )
                    pending_in_chunk = 0

            if pending_in_chunk > 0:
                chunk_start = time.monotonic()
                db.commit()
                _log(
                    f"  committed {total_candidates}/{total_candidates} "
                    f"(final chunk took {time.monotonic() - chunk_start:.1f}s)"
                )
            elif not updated_rows:
                db.rollback()
                _log("No rows needed updates. Rolled back.")

            payload["updated_rows"] = len(updated_rows)
            payload["updated_row_ids"] = [row["id"] for row in updated_rows[: args.sample_limit]]
            payload["verification"] = _verification_summary(db, args.sample_limit)
            _print_output(payload, as_json=args.json)

        except Exception:
            db.rollback()
            raise


if __name__ == "__main__":
    main()
